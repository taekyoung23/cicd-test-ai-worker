# Worker 배포 운영 Runbook

## 1. 목적

이 문서는 Worker 배포 실패, Worker rollback 결과, Worker AI Failure Summary Slack 알림 이후 운영자가 Free Worker와 Paid Worker를 어떤 순서로 확인해야 하는지 정리한 운영 Runbook입니다.

AI Worker는 SQS 메시지를 처리하는 비동기 Worker 서비스입니다. Free Worker와 Paid Worker는 각각 별도 ECS Service, 별도 SQS Queue, 별도 DLQ를 사용합니다.

Worker Runbook의 핵심 점검 대상은 Jenkins, ECS Free/Paid Worker Service, SQS Queue, DLQ, CloudWatch Logs입니다. API처럼 ALB Target Group이나 `/api/health` 중심으로 점검하지 않습니다.

## 2. 연결되는 Slack 알림

| 우선순위 | Runbook 필요한 부분 | Slack 알림 | 왜 필요한지 |
| --- | --- | --- | --- |
| 1 | Worker 배포 실패 | `Worker deployment failed` | Free/Paid 중 어디서 실패했는지 확인하고 ECS task, stopped reason, CloudWatch Logs를 점검해야 합니다. |
| 2 | Worker 롤백 결과 | `Worker rollback result` | Free rollback, Paid rollback, Free 보상 rollback 결과를 실제 ECS Service 상태와 대조해야 합니다. |
| 3 | Worker AI Failure Summary | `Worker AI Failure Summary` | AI 요약 이후 Free/Paid Worker별 점검 절차로 연결해야 합니다. |

## 3. Worker 배포 흐름

1. 공통 Worker 이미지를 빌드하고 ECR에 push합니다.
2. Free Worker와 Paid Worker의 rollback baseline revision을 저장합니다.
3. Free Worker를 먼저 배포합니다.
4. Free Worker revision 및 RUNNING 상태를 검증합니다.
5. Free Worker 검증 성공 후 Paid Worker를 배포합니다.
6. Paid Worker revision 및 RUNNING 상태를 검증합니다.
7. 실패 시 시나리오에 따라 rollback을 수행합니다.

## 4. 실패 시나리오

| 시나리오 | 기대 동작 |
| --- | --- |
| Free Worker 검증 실패 | Free Worker를 baseline revision으로 rollback하고 Paid Worker 배포는 시작하지 않습니다. |
| Paid Worker 검증 실패 | Paid Worker를 baseline revision으로 rollback하고, 이미 배포된 Free Worker도 baseline revision으로 보상 rollback합니다. |
| ECS Service Update 이전 실패 | ECS Service가 변경되지 않았으므로 rollback이 필요하지 않습니다. |
| Worker task RUNNING 실패 | ECS stopped reason과 CloudWatch Logs를 확인합니다. |
| SQS 처리 지연 | Queue 적체와 Oldest Message Age를 확인합니다. |
| DLQ 유입 | 메시지 실패 원인과 Worker 로그를 확인합니다. |

## 5. 빠른 점검 순서

1. Slack 알림의 Jenkins Build URL을 확인합니다.
2. Jenkins Build 결과를 확인합니다.
3. `Deploy Phase`와 `Scenario`를 확인합니다.
4. `Free Update Requested`, `Paid Update Requested`를 확인합니다.
5. `Rollback Needed` 값을 확인합니다.
6. Worker rollback result Slack 알림을 확인합니다.
7. Free/Paid의 `Baseline Revision`과 `Final Revision`을 비교합니다.
8. Free 실패 케이스이면 `Paid Deployment Started=false`인지 확인합니다.
9. Paid 실패 케이스이면 `Free Compensating Rollback=true`인지 확인합니다.
10. ECS Free/Paid Worker Service의 현재 Task Definition을 확인합니다.
11. ECS Free/Paid Worker Task가 RUNNING인지 확인합니다.
12. SQS Free/Paid Queue 적체를 확인합니다.
13. Free/Paid DLQ 유입 여부를 확인합니다.
14. CloudWatch Logs에서 Worker boot/error/inference 로그를 확인합니다.
15. 필요 시 ECS Service Events를 확인합니다.

## 6. Jenkins 확인 항목

| 확인 항목 | 기대 값 / 확인 의미 |
| --- | --- |
| Build 결과 | 정상 배포는 `SUCCESS`, 실패 테스트는 `FAILED` 가능 |
| Scenario | Free 실패인지 Paid 실패인지 구분 |
| Deploy Phase | 실패 단계 확인 |
| Free Update Requested | Free Worker ECS Update 요청 여부 |
| Paid Update Requested | Paid Worker ECS Update 요청 여부 |
| Paid Deployment Started | Free 실패 시 `false` 기대 |
| Rollback Needed | rollback 필요 여부 |
| Rollback Attempted | rollback 시도 여부 |
| Free Rollback Result | Free rollback 필요 시 baseline 복구 여부 |
| Paid Rollback Result | Paid rollback 필요 시 baseline 복구 여부 |
| Free Compensating Rollback | Paid 실패 후 Free 보상 rollback 필요 시 `true` |
| Rollback Result | 전체 복구 검증 완료 시 `RECOVERY_VERIFIED` |
| Free Baseline Revision | Free rollback 기준 revision |
| Free Final Revision | Free rollback 후 최종 revision |
| Paid Baseline Revision | Paid rollback 기준 revision |
| Paid Final Revision | Paid rollback 후 최종 revision |
| Deployment Summary Artifact | image, digest, revision, rollback 결과 확인 |
| Trivy Artifact | 상세 보안 스캔 JSON |
| Trivy Mode | `WARNING` |
| Trivy Gate | `NOT_APPLIED` |

## 7. ECS 확인 항목

| 서비스 | 확인 위치 | 기대 값 |
| --- | --- | --- |
| Free Worker | ECS Service Overview | Slack의 Free `Final Revision`과 일치 |
| Paid Worker | ECS Service Overview | Slack의 Paid `Final Revision`과 일치 |
| Free Worker task | ECS Service Tasks 탭 | RUNNING task가 Free `Final Revision` 사용 |
| Paid Worker task | ECS Service Tasks 탭 | RUNNING task가 Paid `Final Revision` 사용 |
| ECS Service Events | Events 탭 | deployment completed, steady state, stopped reason 확인 |
| Deployment circuit breaker | ECS Service Configuration | enable true, rollback true |

## 8. SQS / DLQ 확인 항목

| 확인 항목 | 확인 위치 | 기대 값 / 조치 |
| --- | --- | --- |
| Free Queue 적체 | SQS Free Queue | 메시지 수 급증 여부 확인 |
| Paid Queue 적체 | SQS Paid Queue | 메시지 수 급증 여부 확인 |
| Free DLQ 유입 | SQS Free DLQ | 신규 메시지 유입 여부 확인 |
| Paid DLQ 유입 | SQS Paid DLQ | 신규 메시지 유입 여부 확인 |
| Oldest Message Age | SQS / CloudWatch Metrics | 처리 지연 여부 확인 |
| Messages Received / Deleted | SQS / CloudWatch Metrics | Worker가 메시지를 소비하고 삭제하는지 확인 |

Queue URL 전체값, Account ID, 민감한 리소스 식별자는 문서나 캡처에 직접 노출하지 않습니다.

## 9. CloudWatch Logs 확인 항목

CloudWatch Logs에서는 Worker 컨테이너 기동과 메시지 처리 중 발생한 오류를 확인합니다.

| 확인 항목 | 확인 의미 |
| --- | --- |
| Worker 컨테이너 기동 오류 | import 실패, 환경 변수 누락, 설정 오류 확인 |
| 모델 다운로드 실패 | 모델 파일 다운로드 또는 경로 문제 확인 |
| S3 Audio Bucket 접근 실패 | 입력 오디오 파일 접근 실패 여부 확인 |
| S3 Model Bucket 접근 실패 | 모델 저장소 접근 실패 여부 확인 |
| SQS 메시지 수신 오류 | queue polling, receive message 실패 여부 확인 |
| RDS 결과 저장 오류 | 처리 결과 저장 실패 여부 확인 |
| inference 실행 오류 | 모델 추론 중 예외 또는 입력 데이터 문제 확인 |
| healthcheck 실패 로그 | 컨테이너 healthcheck 실패 원인 확인 |
| OOMKilled 또는 메모리 부족 로그 | task memory 부족 또는 프로세스 종료 여부 확인 |

## 10. Rollback 검증 기준

아래 조건이 시나리오에 맞게 충족되면 Worker rollback이 정상 복구된 것으로 판단합니다.

- `Rollback Result=RECOVERY_VERIFIED`
- Free rollback이 필요한 경우 Free `Baseline Revision`과 Free `Final Revision`이 같습니다.
- Paid rollback이 필요한 경우 Paid `Baseline Revision`과 Paid `Final Revision`이 같습니다.
- Free 실패 시 `Paid Deployment Started=false`
- Paid 실패 시 `Free Compensating Rollback=true`
- ECS Free Worker task definition이 Slack의 Free `Final Revision`과 일치합니다.
- ECS Paid Worker task definition이 Slack의 Paid `Final Revision`과 일치합니다.
- Free/Paid Worker task가 RUNNING 상태입니다.
- SQS Queue 적체가 비정상적으로 증가하지 않습니다.
- DLQ 유입 여부를 확인하고 필요 시 원인을 기록합니다.

## 11. 다음 조치

| 상황 | 조치 |
| --- | --- |
| Free rollback 복구 완료 | Free Worker stopped task reason과 CloudWatch Logs를 확인합니다. |
| Paid rollback 복구 완료 | Paid Worker stopped task reason과 CloudWatch Logs를 확인합니다. |
| Free 보상 rollback 수행 | Free와 Paid가 모두 baseline revision으로 돌아왔는지 확인합니다. |
| Free rollback 실패 | Free Worker Service를 마지막 정상 Free task definition으로 수동 업데이트합니다. |
| Paid rollback 실패 | Paid Worker Service를 마지막 정상 Paid task definition으로 수동 업데이트합니다. |
| Free 보상 rollback 실패 | Free/Paid 모두 Slack의 Baseline Revision 기준으로 ECS Service revision을 대조한 뒤 수동 복구합니다. |
| SQS 적체 증가 | Worker task 수, CloudWatch Logs, queue age를 확인합니다. |
| DLQ 유입 | DLQ 메시지 원인, Worker 예외 로그, 재처리 가능 여부를 확인합니다. |
| Trivy finding 존재 | Trivy는 Warning Mode이므로 rollback 원인으로 판단하지 않고 별도 보안 조치 항목으로 관리합니다. |

## 12. 주의사항

- Trivy finding을 배포 실패 또는 rollback 원인으로 판단하지 않습니다.
- Trivy는 현재 `WARNING` 모드이고 `Gate=NOT_APPLIED`입니다.
- Trivy finding은 별도 보안 조치 항목으로 관리합니다.
- Worker 장애 확인은 ALB Target Group이나 `/api/health` 중심으로 하지 않습니다.
- Worker는 ECS/SQS/DLQ/CloudWatch 중심으로 확인합니다.
- API는 ALB/ECS/CloudWatch 중심으로 확인합니다.
- Free 실패 시 Paid는 배포되지 않는 것이 기대 동작입니다.
- Paid 실패 시 이미 배포된 Free는 보상 rollback 대상입니다.
- 민감정보, Account ID, Secret ARN, DB 정보, Queue URL 전체값은 문서나 캡처에 직접 노출하지 않습니다.

