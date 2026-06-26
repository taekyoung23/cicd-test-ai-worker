# Worker 배포 운영 Runbook

## 1. 문서 개요

이 문서는 `ai-worker-cicd` Jenkins Pipeline 실패 시 운영자가 Free/Paid Worker 배포 장애를 빠르게 분리하고 복구하기 위한 운영 Runbook이다.

적용 범위:

- 대상 Jenkins Job: `ai-worker-cicd`
- 대상 ECS Service: Free Worker Service, Paid Worker Service
- 대상 Queue: Free Worker Queue, Paid Worker Queue
- 대상 DLQ: Free Worker DLQ, Paid Worker DLQ
- 주요 점검 대상: Jenkins, ECR Image/Digest, ECS Free/Paid Worker Service, ECS Task Definition Revision, SQS Free/Paid Queue, SQS Free/Paid DLQ, CloudWatch Logs, Worker stopped reason, Deployment Summary Artifact, Slack 알림

이 Runbook이 다루는 장애 범위:

- Jenkins 실행 및 GitHub Webhook 장애
- Worker build/test 실패
- Docker image build 및 smoke test 실패
- Trivy scan 결과 확인
- ECR login/push 실패
- Free/Paid baseline capture 실패
- Free/Paid deploy/verify 실패
- Free/Paid rollback 및 Free compensating rollback 실패
- Worker task RUNNING 실패
- SQS Queue 적체 및 DLQ 유입
- CloudWatch Logs의 inference/runtime 오류
- Slack 알림 및 Deployment Summary artifact 누락

이 Runbook이 다루지 않는 범위:

- API ALB Target Health 장애
- `/api/health` 장애
- CloudFront/S3 frontend 장애
- RDS schema 변경
- Terraform apply 장애

Worker는 ALB로 외부 요청을 받는 서비스가 아니라 SQS 메시지를 처리하는 비동기 ECS Fargate Worker이다.

## 2. Worker 배포 아키텍처 및 배포 흐름

배포 흐름:

```text
GitHub push
→ Jenkins Worker Pipeline
→ Source Checkout
→ Worker Build & Test
→ Docker Image Build
→ Docker Image Smoke Test
→ Trivy Image Scan - Warning Mode
→ ECR Push
→ Free Worker baseline capture
→ Paid Worker baseline capture
→ Free Worker deploy/verify
→ Paid Worker deploy/verify
→ Rollback or Compensation Rollback if needed
→ Slack Notification
```

운영 관점의 흐름:

```text
GitHub
→ Jenkins Worker Pipeline
→ ECR
→ ECS Free Worker Service
→ ECS Paid Worker Service
→ SQS Free/Paid Queue
→ S3 Audio/Model Bucket
→ RDS result update
→ CloudWatch Logs
→ Slack Notification
```

Worker 역할:

- SQS polling
- S3 Audio 파일 다운로드
- S3 Model 파일 사용
- AI inference 수행
- `result.json` S3 업로드
- RDS status/result 업데이트
- SQS message delete

Free Worker와 Paid Worker는 별도 ECS Service, 별도 SQS Queue, 별도 DLQ를 사용하지만 동일 Worker image를 기반으로 순차 배포된다.

## 3. 정상 배포 기준

아래 조건을 모두 만족하면 Worker 배포가 정상 완료된 것으로 판단한다.

- Jenkins build result가 `SUCCESS`
- Worker build/test 통과
- Docker image smoke test 통과
- Trivy scan이 `WARNING` mode로 실행됨
- ECR push 성공
- Image digest 확인
- Free Worker baseline revision 저장
- Paid Worker baseline revision 저장
- Free Worker 새 revision 배포 성공
- Free Worker RUNNING task가 새 revision 사용
- Paid Worker 새 revision 배포 성공
- Paid Worker RUNNING task가 새 revision 사용
- Free/Paid ECS service stable
- Deployment Summary Artifact 생성
- Slack 성공 알림 수신

주의:

- 현재 자동 검증은 Worker task RUNNING/revision 일치 중심이다.
- SQS → Worker → S3 → RDS E2E Smoke Test는 별도 수동 Runbook 또는 후속 고도화 항목이다.

## 4. Worker 장애 대응 우선순위

### 4.1 Jenkins 실행 자체가 안 됨

#### 증상

- Jenkins UI 접속 불가
- `ai-worker-cicd` Job이 실행되지 않음
- 수동 `Build Now`가 시작되지 않음

#### 주요 원인

- Jenkins 서비스 또는 executor 장애
- Jenkins EC2/컨테이너 문제
- Jenkins UI 접근 경로 문제

#### 확인 방법

- Jenkins UI 접속 가능 여부 확인
- Jenkins queue 및 executor 상태 확인
- Jenkins node 상태 확인

#### 조치 방법

- executor 부족이면 대기 후 재시도
- Jenkins 자체 장애면 Jenkins 운영 담당자에게 에스컬레이션
- Terraform apply로 즉시 해결하려 하지 않는다.

#### 재시도 기준

- Jenkins UI와 executor가 정상
- `ai-worker-cicd` 수동 실행 가능

### 4.2 GitHub Webhook이 Jenkins를 트리거하지 못함

#### 증상

- GitHub push 후 Jenkins build가 자동 시작되지 않음
- build 원인에 `Started by GitHub push`가 없음

#### 주요 원인

- GitHub Webhook 비활성화
- Payload URL 또는 shared secret mismatch
- Jenkins `/github-webhook/` endpoint 접근 실패

#### 확인 방법

- GitHub Recent Deliveries에서 `ping`/`push` 이벤트 200 확인
- Jenkins Job trigger 설정 확인
- Jenkins build cause 확인

#### 조치 방법

- Webhook 설정값 확인
- 기존 Jenkins/GitHub shared secret으로 재설정
- 긴급 시 `Build Now`로 수동 배포

#### 재시도 기준

- Recent Deliveries 200
- 작은 commit push로 자동 build 시작

### 4.3 Source Checkout 실패

#### 증상

- Git checkout 실패
- Jenkinsfile을 가져오지 못함

#### 주요 원인

- GitHub credential 문제
- Repository URL, Branch Specifier, Script Path 오류
- GitHub token 권한 부족

#### 확인 방법

- Jenkins Job SCM 설정 확인
- GitHub token credential 연결 확인
- Console Log의 Git 오류 확인

#### 조치 방법

- Jenkins Job SCM 설정 수정
- token 권한 확인

#### 재시도 기준

- 대상 branch의 Jenkinsfile checkout 성공

### 4.4 Worker Build & Test 실패

#### 증상

- Python dependency 설치 실패
- fairseq 관련 설치 오류
- import 실패
- pytest 실패

#### 주요 원인

- dependency version 충돌
- fairseq source 또는 editable install 문제
- 테스트 코드 실패
- runtime 의존성 누락

#### 확인 방법

- Console Log의 pip/pytest 오류 확인
- fairseq 관련 설치 실패 위치 확인
- 모델 파일을 이미지에 포함하지 않는 구조인지 확인

#### 조치 방법

- dependency 또는 import 경로 수정
- 실패 테스트 원인 수정
- 모델 파일을 build/test 단계에 무리하게 포함하지 않음

#### 재시도 기준

- dependency 설치, import, test 모두 통과

### 4.5 Docker Image Build 실패

#### 증상

- Worker image build 실패
- PyTorch/fairseq/ffmpeg/git 설치 실패
- image size 급증 또는 build timeout

#### 주요 원인

- Dockerfile base image 문제
- CPU 기반 PyTorch 설치 실패
- fairseq_src editable install 실패
- Docker daemon/socket 문제
- 모델 파일을 image에 복사하려는 변경

#### 확인 방법

- Dockerfile base image 확인
- PyTorch 설치 로그 확인
- ffmpeg/git 설치 로그 확인
- fairseq_src install 로그 확인
- 모델 파일이 image에 복사되는지 확인

#### 조치 방법

- Dockerfile 또는 dependency 수정
- 모델 파일은 runtime 다운로드/사용 구조로 유지
- Docker daemon 문제는 Jenkins 인프라 담당자와 분리 검토

#### 재시도 기준

- Worker image build 성공
- image tag와 digest 확인 가능

### 4.6 Docker Image Smoke Test 실패

#### 증상

- 컨테이너 기동 실패
- 기본 import 또는 healthcheck 실패
- smoke test cleanup 실패

#### 주요 원인

- entrypoint 오류
- Python module import 실패
- healthcheck.py 실행 실패
- smoke test에서 모델 다운로드를 강제함

#### 확인 방법

- 컨테이너 로그 확인
- Worker process 기본 import 가능 여부 확인
- healthcheck 가능 여부 확인
- 모델 다운로드를 smoke test에서 강제하지 않는지 확인

#### 조치 방법

- entrypoint/import/healthcheck 오류 수정
- smoke test는 기동 sanity check 수준으로 유지

#### 재시도 기준

- 컨테이너가 정상 기동되고 healthcheck/import 검증 통과

### 4.7 Trivy Scan 실패 또는 finding 존재

#### 증상

- Trivy 실행 실패
- HIGH/CRITICAL finding 존재

#### 주요 원인

- Trivy DB 다운로드 실패
- base image 또는 dependency 취약점
- 네트워크 일시 장애

#### 확인 방법

- Trivy summary와 artifact 확인
- `Trivy Mode=WARNING`
- `Trivy Gate=NOT_APPLIED`

#### 조치 방법

- Trivy 실행 실패면 도구/네트워크 상태 확인 후 재시도
- finding은 별도 보안 조치 항목으로 관리
- 현재는 finding 자체를 배포 차단 또는 rollback 원인으로 보지 않음

#### 재시도 기준

- Trivy scan 완료 및 artifact 생성

### 4.8 ECR Login/Push 실패

#### 증상

- ECR login 실패
- Worker image push 실패
- digest 조회 실패

#### 주요 원인

- Jenkins Role 권한 부족
- ECR repository 이름 오류
- AWS CLI 인증 문제
- ECR 일시 장애

#### 확인 방법

- ECR login 로그 확인
- repository name 확인
- image tag와 digest 확인
- common worker image가 Free/Paid 모두에 사용되는지 확인

#### 조치 방법

- ECR repository/region 확인
- Jenkins Role 권한 확인
- push 실패 시 tag 충돌 여부 확인

#### 재시도 기준

- ECR push 성공
- digest 조회 성공

### 4.9 Free Worker baseline capture 실패

#### 증상

- Free baseline revision 저장 실패
- 기존 Free task definition 조회 실패

#### 주요 원인

- ECS Free Service 조회 실패
- IAM 권한 부족
- service name/cluster name 오류

#### 확인 방법

- Free ECS Service 존재 여부 확인
- current task definition 조회 로그 확인
- Jenkins Console Log의 baseline capture 오류 확인

#### 조치 방법

- service/cluster 이름 확인
- 권한 문제 확인
- baseline 없이 배포를 진행하지 않음

#### 재시도 기준

- Free baseline revision 저장 성공

### 4.10 Paid Worker baseline capture 실패

#### 증상

- Paid baseline revision 저장 실패
- 기존 Paid task definition 조회 실패

#### 주요 원인

- ECS Paid Service 조회 실패
- IAM 권한 부족
- service name/cluster name 오류

#### 확인 방법

- Paid ECS Service 존재 여부 확인
- current task definition 조회 로그 확인
- Jenkins Console Log의 baseline capture 오류 확인

#### 조치 방법

- service/cluster 이름 확인
- 권한 문제 확인
- baseline 없이 배포를 진행하지 않음

#### 재시도 기준

- Paid baseline revision 저장 성공

### 4.11 Free Worker deploy/verify 실패

#### 증상

- Free Service Update 실패
- Free task가 RUNNING 되지 않음
- Free running task revision 불일치

#### 주요 원인

- 새 revision 기동 실패
- 환경 변수/secret/runtime 오류
- image 문제
- ECS Circuit Breaker rollback

#### 확인 방법

- Free baseline revision과 new revision 확인
- Free service update 요청 여부 확인
- Free running task revision 확인
- Free stopped reason 확인
- Free CloudWatch Logs 확인
- Free 실패 시 Paid 배포가 시작되지 않았는지 확인

#### 조치 방법

- Free rollback result 확인
- Paid가 미배포 상태인지 확인
- stopped reason과 CloudWatch Logs 기반 원인 수정

#### 재시도 기준

- Free ECS Service stable
- Free RUNNING task가 기대 revision 사용

### 4.12 Paid Worker deploy/verify 실패

#### 증상

- Paid Service Update 실패
- Paid task RUNNING 실패
- Paid running task revision 불일치
- Paid 실패 후 Free 보상 rollback 발생

#### 주요 원인

- Paid runtime 설정 오류
- Paid queue/secret/env 문제
- image 문제
- ECS Circuit Breaker rollback

#### 확인 방법

- Paid baseline revision과 new revision 확인
- Paid service update 요청 여부 확인
- Paid running task revision 확인
- Paid stopped reason 확인
- Paid CloudWatch Logs 확인
- Paid 실패 시 Paid rollback과 Free compensating rollback 수행 여부 확인

#### 조치 방법

- Paid rollback result 확인
- Free compensating rollback result 확인
- Free/Paid final revision이 baseline인지 확인

#### 재시도 기준

- Paid 또는 Free/Paid rollback 복구 검증 완료
- 원인 수정 후 재배포 가능

### 4.13 Free rollback 실패

#### 증상

- Free final revision이 baseline과 다름
- Free rollback result가 recovery 상태가 아님

#### 주요 원인

- Free ECS Service update 실패
- baseline revision 누락
- rollback 후 task 기동 실패

#### 확인 방법

- Free baseline/final revision 비교
- Free ECS Events 확인
- Free CloudWatch Logs 확인

#### 조치 방법

- 마지막 정상 Free task definition으로 ECS Service 수동 update
- service stable 확인

#### 재시도 기준

- Free final revision이 baseline으로 복구

### 4.14 Paid rollback 실패

#### 증상

- Paid final revision이 baseline과 다름
- Paid rollback result가 recovery 상태가 아님

#### 주요 원인

- Paid ECS Service update 실패
- baseline revision 누락
- rollback 후 task 기동 실패

#### 확인 방법

- Paid baseline/final revision 비교
- Paid ECS Events 확인
- Paid CloudWatch Logs 확인

#### 조치 방법

- 마지막 정상 Paid task definition으로 ECS Service 수동 update
- service stable 확인

#### 재시도 기준

- Paid final revision이 baseline으로 복구

### 4.15 Free compensating rollback 실패

#### 증상

- Paid 실패 후 Free가 새 revision으로 남아 있음
- Free/Paid release 일관성이 깨짐

#### 주요 원인

- Free 보상 rollback update 실패
- Free rollback 후 stable 실패
- 외부 배포 개입

#### 확인 방법

- Free compensating rollback result 확인
- Free baseline/final revision 비교
- Paid baseline/final revision 비교

#### 조치 방법

- Free를 baseline revision으로 수동 update
- Free/Paid final revision이 모두 baseline인지 확인

#### 재시도 기준

- Free/Paid release revision 일관성 복구

### 4.16 Worker task RUNNING 실패

#### 증상

- desired count 대비 running count 부족
- task가 STOPPED로 반복 이동
- healthStatus가 unhealthy

#### 주요 원인

- application runtime 예외
- DB/S3/SQS 접근 실패
- OOMKilled 또는 resource 부족
- healthcheck 실패

#### 확인 방법

- ECS stopped reason 확인
- container exitCode 확인
- CloudWatch Logs 확인
- desired/running count 확인

#### 조치 방법

- stopped reason 기준으로 dependency/env/resource 문제 해결
- 필요 시 baseline revision으로 수동 복구

#### 재시도 기준

- RUNNING task가 desired count와 일치
- task revision이 기대값과 일치

### 4.17 SQS Queue 적체

#### 증상

- Queue 메시지가 계속 증가
- 처리 지연 발생
- `ApproximateAgeOfOldestMessage` 증가

#### 주요 원인

- Worker task 미기동 또는 부족
- message processing 오류
- S3/RDS/inference 지연
- visibility timeout 또는 retry 증가

#### 확인 방법

- `ApproximateNumberOfMessagesVisible`
- `ApproximateNumberOfMessagesNotVisible`
- `ApproximateAgeOfOldestMessage`
- `MessagesReceived`
- `MessagesDeleted`
- Worker desired/running count
- Worker CloudWatch Logs

#### 조치 방법

- Worker RUNNING 상태 확인
- CloudWatch Logs에서 처리 오류 확인
- 필요 시 Worker scale 조정은 담당자 승인 후 진행

#### 재시도 기준

- MessagesDeleted가 증가
- OldestMessageAge가 감소
- Queue visible message가 안정화

### 4.18 DLQ 유입

#### 증상

- Free/Paid DLQ에 신규 메시지 발생
- 특정 request_id가 반복 실패

#### 주요 원인

- 메시지 payload 문제
- S3 object 접근 실패
- inference runtime 오류
- RDS update 실패
- max receive count 초과

#### 확인 방법

- Free DLQ 신규 메시지 수
- Paid DLQ 신규 메시지 수
- 원본 Queue
- 실패 메시지의 request_id
- Worker error log
- 재처리 가능 여부

#### 조치 방법

- 메시지 본문 캡처 시 민감정보 마스킹
- DLQ replay는 담당자 승인 후 수행
- 임의 삭제 금지

#### 재시도 기준

- 원인 수정 완료
- 재처리 승인 완료
- DLQ 신규 유입이 멈춤

### 4.19 CloudWatch Logs에서 inference/runtime 오류

#### 증상

- inference 예외
- 모델 파일 접근 실패
- DB/S3/SQS client 오류
- Python traceback 발생

#### 주요 원인

- 모델 다운로드/로드 실패
- 입력 오디오 문제
- RDS 인증/네트워크 문제
- S3 권한 또는 object 경로 문제

#### 확인 방법

- Worker CloudWatch Logs 확인
- request_id 기준 로그 추적
- stopped task reason과 함께 대조

#### 조치 방법

- 오류 유형별 담당자에게 에스컬레이션
- code/config 수정 후 재배포
- DLQ 메시지는 승인 없이 삭제하지 않음

#### 재시도 기준

- 동일 오류가 재발하지 않음
- test message 또는 수동 검증 통과

### 4.20 Slack Notification 실패

#### 증상

- 배포 결과는 나왔지만 Slack 알림이 오지 않음
- Console Log에 Slack 전송 실패 메시지 표시

#### 주요 원인

- Jenkins credential `slack-webhook-url` 문제
- Slack webhook 만료
- Slack API/네트워크 장애

#### 확인 방법

- Jenkins Console Log 확인
- credential ID 존재 여부 확인
- Slack Webhook URL 값은 출력하지 않음

#### 조치 방법

- Slack credential 상태 확인
- Slack 실패는 배포 실패와 동일한 의미가 아님

#### 재시도 기준

- Slack 알림 정상 수신

### 4.21 Deployment Summary Artifact 누락

#### 증상

- Jenkins Artifacts에 deployment summary가 없음
- image/digest/revision/rollback 결과 확인이 어려움

#### 주요 원인

- summary 생성 전 stage 실패
- archiveArtifacts 실패
- workspace 권한 문제

#### 확인 방법

- Jenkins artifact 목록 확인
- Console Log에서 summary 생성/archiving 로그 확인

#### 조치 방법

- 실패 stage 해결 후 재실행
- summary만 누락되면 Console Log와 Slack을 함께 확인

#### 재시도 기준

- Deployment Summary Artifact가 생성되고 archive됨

## 5. Worker Stage별 상세 장애 대응

### Worker Build & Test

확인 항목:

- Python dependency 설치 실패
- fairseq 관련 설치 문제
- import 실패
- pytest 실패
- 모델 파일을 이미지에 포함하지 않는 구조인지
- 테스트 실패가 배포 차단 사유인지

테스트 실패는 배포 차단 사유로 본다.

### Docker Image Build

확인 항목:

- CPU 기반 PyTorch 설치
- Dockerfile base image
- ffmpeg/git 설치
- fairseq_src editable install
- 모델 파일을 이미지에 복사하지 않는지
- Docker daemon/socket 문제
- 이미지 크기 증가 문제

모델 파일은 image에 직접 포함하지 않고 runtime에서 사용하는 구조를 유지한다.

### Docker Image Smoke Test

확인 항목:

- 컨테이너 기동 여부
- Worker process 기본 import 가능 여부
- healthcheck 가능 여부
- 모델 다운로드를 smoke test에서 강제하지 않는지
- smoke test container cleanup 여부

### Trivy Image Scan

현재 Trivy는 `WARNING` 모드이다.

- `HIGH/CRITICAL` finding이 있어도 현재는 배포 차단 Gate가 아니다.
- `Trivy Gate=NOT_APPLIED`
- finding은 별도 보안 조치 항목으로 관리한다.

### ECR Push

확인 항목:

- ECR login
- repository name
- image tag
- image digest
- common worker image가 Free/Paid 모두에 사용되는지

### Free Worker Deploy/Verify

확인 항목:

- Free baseline revision
- Free new revision
- Free service update 요청 여부
- Free running task revision
- Free stopped reason
- Free CloudWatch Logs
- Free 실패 시 Paid 배포가 시작되지 않는지

### Paid Worker Deploy/Verify

확인 항목:

- Paid baseline revision
- Paid new revision
- Paid service update 요청 여부
- Paid running task revision
- Paid stopped reason
- Paid CloudWatch Logs
- Paid 실패 시 Paid rollback과 Free compensating rollback이 수행되는지

### Rollback / Compensation Rollback

확인 항목:

- Free rollback result
- Paid rollback result
- Free compensating rollback result
- Baseline Revision
- Final Revision
- Rollback Result
- Recovery Verified 여부

## 6. SQS / DLQ 상세 장애 대응

### SQS Queue 적체

#### 증상

- Free/Paid Queue에 처리 대기 메시지가 증가한다.
- 처리 지연이 길어진다.
- Oldest message age가 증가한다.

#### 주요 원인

- Worker task가 RUNNING 상태가 아님
- Worker 처리 속도 부족
- inference 또는 RDS/S3 호출 지연
- 메시지 처리 중 예외 발생

#### 확인 방법

- `ApproximateNumberOfMessagesVisible`
- `ApproximateNumberOfMessagesNotVisible`
- `ApproximateAgeOfOldestMessage`
- `MessagesReceived`
- `MessagesDeleted`
- Worker desired/running count
- Worker CloudWatch Logs

#### 조치 방법

- Worker task 상태와 revision 확인
- CloudWatch Logs에서 처리 오류 확인
- scale 조정이나 재처리는 담당자 승인 후 수행

#### 재시도 기준

- MessagesDeleted 증가
- OldestMessageAge 감소
- Queue 적체가 안정화

### DLQ 유입

#### 증상

- Free DLQ 또는 Paid DLQ에 신규 메시지가 유입된다.
- 특정 request_id가 반복 실패한다.

#### 주요 원인

- 메시지 payload 오류
- S3 object 접근 실패
- 모델 inference 오류
- RDS status/result update 실패
- max receive count 초과

#### 확인 방법

- Free DLQ 신규 메시지 수
- Paid DLQ 신규 메시지 수
- 원본 Queue
- 실패 메시지의 request_id
- Worker error log
- 재처리 가능 여부

#### 조치 방법

- 메시지 본문과 request_id 캡처 시 민감정보 마스킹
- DLQ 메시지 삭제/재처리는 임의로 하지 않음
- DLQ replay는 담당자 승인 후 수행

#### 재시도 기준

- 실패 원인 수정
- replay 승인
- DLQ 신규 유입 중단

주의:

- Queue URL 전체값은 문서화하지 않는다.
- 메시지 본문에 민감한 데이터가 있을 수 있으므로 캡처 시 마스킹한다.
- DLQ 메시지 삭제/재처리는 임의로 하지 않는다.

## 7. Worker 수동 복구 절차

1. Slack 실패 알림에서 Jenkins Build URL 확인
2. Failed Scenario 확인
3. Free/Paid 중 실패 대상 확인
4. Jenkins Console Log 확인
5. ECS Free/Paid Service Events 확인
6. Running Task revision 확인
7. stopped reason 확인
8. CloudWatch Logs 확인
9. SQS Queue 적체 확인
10. DLQ 유입 확인
11. Rollback Result 확인
12. 필요 시 baseline revision으로 ECS Service 수동 업데이트
13. SQS/DLQ 장애는 메시지 재처리 전 담당자 승인

주의:

- Worker 장애를 ALB Target Health나 `/api/health`로 판단하지 않는다.
- API 장애와 Worker 장애를 분리해서 판단한다.
- 즉시 Terraform apply로 해결하지 않는다.

## 8. Worker Rollback 기준

자동 rollback 및 compensation rollback 기준:

- Free 실패 시 Paid 배포 미진행
- Free 실패 시 Free baseline rollback
- Paid 실패 시 Paid baseline rollback
- Paid 실패 시 Free compensating rollback
- baseline revision과 final revision 비교
- rollback 성공 조건은 final revision이 baseline과 일치하고 service가 stable인 상태

rollback 실패 시:

1. Free/Paid baseline revision 확인
2. 실패 service를 baseline task definition으로 수동 update
3. service stable 대기
4. RUNNING task revision 확인
5. rollback 성공 후 실패 revision 원인 분석
6. SQS 적체/DLQ 여부 후속 확인

Paid 실패 시 Free 보상 rollback은 Free 자체 장애 때문이 아니다. 동일 Worker image를 Free/Paid에 하나의 release 단위로 배포하기 때문에 partial deployment를 피하고 release 일관성을 유지하기 위한 정책이다.

## 9. Worker 보안 및 운영 주의사항

- AWS Access Key를 Jenkins Credential에 직접 저장하지 않는다.
- Jenkins는 EC2 IAM Role 기반으로 AWS 인증을 수행한다.
- Slack Webhook URL은 문서나 로그에 노출하지 않는다.
- GitHub token은 문서나 로그에 노출하지 않는다.
- Trivy Warning Mode와 Gate 미적용 상태를 구분한다.
- Docker socket mount 리스크는 후속 고도화 항목이다.
- Worker는 ALB health check 서비스가 아니다.
- Worker 자동 검증은 task RUNNING/revision 일치 중심이다.
- SQS→Worker→S3→RDS E2E 검증은 별도 수동 Runbook 또는 후속 고도화 대상이다.
- DLQ 메시지 임의 삭제 금지
- 메시지 본문/오디오 파일 경로/request_id 캡처 시 마스킹

## 10. Worker 보고서/발표용 요약

Worker CI/CD는 하나의 공통 Worker image를 Free/Paid ECS Service에 순차 배포하는 구조이다. Jenkins는 Free Worker 검증 성공 후 Paid Worker를 배포하며, Free 실패 시 Paid 배포를 시작하지 않고 Free만 baseline으로 복구한다. Paid 실패 시에는 Paid rollback과 함께 이미 새 revision으로 올라간 Free Worker도 baseline으로 보상 rollback하여 Free/Paid release 일관성을 유지한다.

Worker 검증은 ALB나 `/api/health`가 아니라 ECS task RUNNING 상태와 task definition revision 일치 여부를 중심으로 수행한다. 운영 장애 분석은 SQS/DLQ/CloudWatch Logs/stopped reason을 중심으로 진행하며, Trivy는 Warning Mode로 보안 스캔 증적을 확보한다. SQS→Worker→S3→RDS E2E inference 검증은 후속 고도화 또는 별도 수동 Runbook 대상으로 분리한다.
