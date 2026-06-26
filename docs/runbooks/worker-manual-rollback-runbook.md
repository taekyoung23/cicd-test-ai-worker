# Worker 수동 Rollback Runbook

## 1. 문서 목적

이 문서는 AI Worker Free/Paid Service를 이전 정상 Task Definition Revision으로 순차 수동 롤백하고, 정상 확인 후 최신 Revision으로 복구하는 CLI 기반 절차형 Runbook이다.

Worker는 바로 이전 Revision 번호가 항상 롤백 대상이라고 가정하면 안 된다. Free/Paid가 동일한 Worker image를 사용하는 Revision 조합인지 확인한 뒤 진행한다.

| 항목 | 값 |
|---|---|
| ECS Cluster | `securevoice-dev-cluster` |
| Free Worker Service | `securevoice-dev-free-worker-service` |
| Paid Worker Service | `securevoice-dev-paid-worker-service` |
| ECR Repository | `nes2net-ai-worker` |
| Free 현재 Revision | `<Free-현재-Revision>` |
| Paid 현재 Revision | `<Paid-현재-Revision>` |
| Free 이전 정상 Revision | `<Free-이전-정상-Revision>` |
| Paid 이전 정상 Revision | `<Paid-이전-정상-Revision>` |
| 현재 Worker 이미지 태그 | `<Worker-현재-이미지-태그>` |
| 이전 정상 Worker 이미지 태그 | `<Worker-이전-정상-이미지-태그>` |

## 2. 테스트 전 주의사항

- Free/Paid 현재 Revision을 확인하기 전에는 update-service를 실행하지 않는다.
- Free/Paid 이전 정상 Revision 조합이 동일 Worker image를 사용하는지 확인한다.
- 이전 정상 Worker image가 ECR에 존재하는지 확인한다.
- Jenkins Pipeline이 동시에 실행 중이면 수동 롤백과 충돌할 수 있으므로 중단 또는 대기한다.
- Terraform apply로 Worker rollback을 수행하지 않는다.
- SQS/DLQ 메시지 삭제나 replay는 담당자 승인 없이 수행하지 않는다.

## 3. API Service 롤백과 다른 점

API는 단일 ECS Service와 `/api/health` 중심으로 검증한다. Worker는 Free/Paid 두 ECS Service를 순차적으로 다루며, ALB Target Group이나 `/api/health`가 아니라 RUNNING task, task definition revision, stopped reason, SQS/DLQ, CloudWatch Logs를 중심으로 확인한다.

## 4. 이번 테스트로 검증하는 범위

- Free Worker를 이전 정상 Revision으로 수동 전환
- Free Worker stable 및 30초 RUNNING 유지 확인
- Free Worker를 최신 정상 Revision으로 복구
- Paid Worker를 이전 정상 Revision으로 수동 전환
- Paid Worker stable 및 30초 RUNNING 유지 확인
- Paid Worker를 최신 정상 Revision으로 복구
- 최종 Free/Paid 상태 확인

SQS→Worker→S3→RDS E2E inference 성공 여부는 이 문서의 자동 검증 범위가 아니다.

## 5. 현재 Free/Paid Worker 상태 조회

```powershell
aws ecs describe-services `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-free-worker-service securevoice-dev-paid-worker-service `
  --query "services[].{Service:serviceName,TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount}" `
  --output table
```

## 6. Free/Paid 현재 Revision 기록

조회 결과에서 Free/Paid의 현재 TaskDefinition 값을 각각 `<Free-현재-Revision>`, `<Paid-현재-Revision>`에 기록한다.

## 7. Free Worker 최근 Revision 목록 조회

```powershell
aws ecs list-task-definitions `
  --region ap-northeast-2 `
  --family-prefix securevoice-dev-free-worker `
  --status ACTIVE `
  --sort DESC `
  --query "taskDefinitionArns[0:5]" `
  --output table
```

## 8. Paid Worker 최근 Revision 목록 조회

```powershell
aws ecs list-task-definitions `
  --region ap-northeast-2 `
  --family-prefix securevoice-dev-paid-worker `
  --status ACTIVE `
  --sort DESC `
  --query "taskDefinitionArns[0:5]" `
  --output table
```

## 9. Free/Paid 현재 Revision 이미지 확인

```powershell
aws ecs describe-task-definition `
  --region ap-northeast-2 `
  --task-definition <Free-현재-Revision> `
  --query "taskDefinition.containerDefinitions[].{Name:name,Image:image}" `
  --output table
```

```powershell
aws ecs describe-task-definition `
  --region ap-northeast-2 `
  --task-definition <Paid-현재-Revision> `
  --query "taskDefinition.containerDefinitions[].{Name:name,Image:image}" `
  --output table
```

## 10. Free/Paid 이전 후보 Revision 이미지 확인

```powershell
aws ecs describe-task-definition `
  --region ap-northeast-2 `
  --task-definition <Free-이전-정상-Revision> `
  --query "taskDefinition.containerDefinitions[].{Name:name,Image:image}" `
  --output table
```

```powershell
aws ecs describe-task-definition `
  --region ap-northeast-2 `
  --task-definition <Paid-이전-정상-Revision> `
  --query "taskDefinition.containerDefinitions[].{Name:name,Image:image}" `
  --output table
```

## 11. 동일 이미지 기반 이전 정상 Revision 조합 선정

Free/Paid 이전 정상 Revision이 동일 Worker image tag 또는 digest를 사용하는지 확인한다. 바로 이전 revision 번호라는 이유만으로 rollback 대상으로 선정하지 않는다.

## 12. ECR에 이전 Worker 이미지 존재 확인

```powershell
aws ecr describe-images `
  --region ap-northeast-2 `
  --repository-name nes2net-ai-worker `
  --image-ids imageTag=<Worker-이전-정상-이미지-태그> `
  --query "imageDetails[0].{Tag:imageTags[0],Digest:imageDigest}" `
  --output table
```

## 13. Free Worker를 이전 정상 Revision으로 수동 롤백

```powershell
aws ecs update-service `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --service securevoice-dev-free-worker-service `
  --task-definition <Free-이전-정상-Revision> `
  --no-cli-pager
```

## 14. Free Worker stable 대기

```powershell
aws ecs wait services-stable `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-free-worker-service
```

## 15. Free Worker Running/Revision 확인

```powershell
aws ecs describe-services `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-free-worker-service `
  --query "services[0].{TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount}" `
  --output table
```

```powershell
$FREE_TASKS = aws ecs list-tasks `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --service-name securevoice-dev-free-worker-service `
  --desired-status RUNNING `
  --query "taskArns" `
  --output text
```

```powershell
$FREE_TASKS
```

## 16. Free Worker 30초 RUNNING 유지 확인

```powershell
Start-Sleep -Seconds 30

aws ecs describe-tasks `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --tasks $FREE_TASKS `
  --query "tasks[].{TaskDefinition:taskDefinitionArn,LastStatus:lastStatus,DesiredStatus:desiredStatus}" `
  --output table
```

## 17. Free Worker를 최신 정상 Revision으로 복구

```powershell
aws ecs update-service `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --service securevoice-dev-free-worker-service `
  --task-definition <Free-현재-Revision> `
  --no-cli-pager
```

## 18. Free Worker 복구 stable 대기 및 검증

```powershell
aws ecs wait services-stable `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-free-worker-service
```

```powershell
aws ecs describe-services `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-free-worker-service `
  --query "services[0].{TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount}" `
  --output table
```

## 19. Paid Worker를 이전 정상 Revision으로 수동 롤백

```powershell
aws ecs update-service `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --service securevoice-dev-paid-worker-service `
  --task-definition <Paid-이전-정상-Revision> `
  --no-cli-pager
```

## 20. Paid Worker stable 대기

```powershell
aws ecs wait services-stable `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-paid-worker-service
```

## 21. Paid Worker Running/Revision 확인

```powershell
aws ecs describe-services `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-paid-worker-service `
  --query "services[0].{TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount}" `
  --output table
```

```powershell
$PAID_TASKS = aws ecs list-tasks `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --service-name securevoice-dev-paid-worker-service `
  --desired-status RUNNING `
  --query "taskArns" `
  --output text
```

```powershell
$PAID_TASKS
```

## 22. Paid Worker 30초 RUNNING 유지 확인

```powershell
Start-Sleep -Seconds 30

aws ecs describe-tasks `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --tasks $PAID_TASKS `
  --query "tasks[].{TaskDefinition:taskDefinitionArn,LastStatus:lastStatus,DesiredStatus:desiredStatus}" `
  --output table
```

## 23. Paid Worker를 최신 정상 Revision으로 복구

```powershell
aws ecs update-service `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --service securevoice-dev-paid-worker-service `
  --task-definition <Paid-현재-Revision> `
  --no-cli-pager
```

## 24. Paid Worker 복구 stable 대기 및 검증

```powershell
aws ecs wait services-stable `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-paid-worker-service
```

```powershell
aws ecs describe-services `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-paid-worker-service `
  --query "services[0].{TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount}" `
  --output table
```

## 25. 최종 Free/Paid 상태 확인

```powershell
aws ecs describe-services `
  --region ap-northeast-2 `
  --cluster securevoice-dev-cluster `
  --services securevoice-dev-free-worker-service securevoice-dev-paid-worker-service `
  --query "services[].{Service:serviceName,TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount}" `
  --output table
```

## 26. 실패 시 중단 기준

아래 상황에서는 다음 단계로 진행하지 않고 중단한다.

- 현재 Revision을 확인하지 못한 경우
- 이전 정상 Revision을 확정하지 못한 경우
- 이전 정상 Revision이 참조하는 이미지가 ECR에 없는 경우
- update-service 실행 후 services-stable이 실패한 경우
- rollback 후 Running Count가 Desired Count와 일치하지 않는 경우
- Worker의 경우 30초 RUNNING 유지 검증에 실패하는 경우
- CloudWatch Logs 또는 ECS Events에서 반복적인 crash, image pull error, permission error가 확인되는 경우

중단 후에는 다음을 확인한다.

- ECS Service Events
- Stopped Task Reason
- CloudWatch Logs
- ECR 이미지 존재 여부
- Jenkins Pipeline과의 충돌 여부
- 담당자 승인 필요 여부

## 27. 최소 캡처 목록

```text
00-worker-before-rollback-current-state.png
01-worker-revision-list.png
02-worker-revision-image-check.png
03-worker-ecr-image-exists.png
04-free-worker-rollback-success.png
05-free-worker-restore-success.png
06-paid-worker-rollback-success.png
07-paid-worker-restore-success.png
08-worker-final-state.png
```

## 28. 검증 체크리스트

- [ ] Free/Paid 현재 Revision 기록
- [ ] Free/Paid 이전 정상 Revision 후보 조회
- [ ] Free/Paid 이전 정상 Revision이 동일 Worker image 조합인지 확인
- [ ] 이전 Worker image ECR 존재 확인
- [ ] Free 이전 정상 Revision으로 update-service 실행
- [ ] Free services-stable 성공
- [ ] Free 30초 RUNNING 유지 확인
- [ ] Free 최신 정상 Revision으로 복구
- [ ] Paid 이전 정상 Revision으로 update-service 실행
- [ ] Paid services-stable 성공
- [ ] Paid 30초 RUNNING 유지 확인
- [ ] Paid 최신 정상 Revision으로 복구
- [ ] 최종 Free/Paid 상태 확인

## 29. 이번 검증 예시

아래 값은 이번 검증 예시이다. 실제 장애 대응 시에는 반드시 Free/Paid 현재 Revision과 이전 정상 Revision을 다시 조회해야 한다.

Worker는 특히 바로 이전 Revision 번호가 롤백 대상이라고 가정하면 안 된다. Free/Paid가 동일한 Worker image를 사용하는 Revision 조합인지 반드시 확인해야 한다.

| 구분 | Task Definition Revision | 이미지 태그 |
|---|---|---|
| Free 현재 Revision | `securevoice-dev-free-worker:23` | `<이번 검증에서 확인한 현재 이미지 태그>` |
| Paid 현재 Revision | `securevoice-dev-paid-worker:23` | `<이번 검증에서 확인한 현재 이미지 태그>` |
| Free 롤백 대상 Revision | `securevoice-dev-free-worker:22` | `build-11-a70a114` |
| Paid 롤백 대상 Revision | `securevoice-dev-paid-worker:22` | `build-11-a70a114` |

## 30. 발표용 요약 문장

Worker 수동 rollback은 Free/Paid ECS Service의 Task Definition을 이전 정상 Revision 조합으로 순차 전환하고, 각 Service가 stable 상태에 도달한 뒤 RUNNING task와 revision을 확인하는 절차이다. 검증 완료 후에는 Free/Paid를 다시 최신 정상 Revision으로 복구해 release 일관성을 유지한다.

## 31. 한 줄 결론

Worker 수동 rollback은 특정 revision 번호를 고정하지 않고, Free/Paid가 동일 Worker image를 사용하는 이전 정상 Revision 조합을 확인한 뒤 순차적으로 전환하고 RUNNING 상태를 검증하는 절차이다.
