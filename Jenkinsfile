def slackDisplay(value) {
    return value == null || value.toString().trim() == '' ? 'N/A' : value.toString()
}

def workerRunbookLink() {
    return '<https://github.com/taekyoung23/cicd-test-ai-worker/blob/ktk-cicd/docs/runbooks/worker-deployment-runbook.md|운영 가이드>'
}

def sendSlackNotification(String title, Map details) {
    String messageFile = ".slack-message-${env.BUILD_NUMBER ?: 'unknown'}.txt"
    String payloadFile = ".slack-payload-${env.BUILD_NUMBER ?: 'unknown'}.json"
    try {
        String body = ([title] + details.collect { key, value ->
            "*${key}:* ${slackDisplay(value)}"
        }).join('\n')
        writeFile(file: messageFile, text: body)
        withCredentials([
            string(credentialsId: 'slack-webhook-url', variable: 'SLACK_WEBHOOK_URL')
        ]) {
            int slackStatus = sh(
                returnStatus: true,
                script: """
                    set +x
                    set -e
                    python3 - '${messageFile}' '${payloadFile}' <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as message_file:
    message = message_file.read()

with open(sys.argv[2], "w", encoding="utf-8") as payload_file:
    json.dump({"text": message}, payload_file)
PY
                    curl --fail --silent --show-error --connect-timeout 5 --max-time 10 \
                      --header 'Content-Type: application/json' \
                      --data-binary @'${payloadFile}' \
                      "\${SLACK_WEBHOOK_URL}" >/dev/null
                """
            )
            if (slackStatus == 0) {
                echo 'Slack notification sent'
            } else {
                echo "Slack notification failed but ignored. Exit code: ${slackStatus}"
            }
        }
    } catch (Exception ignored) {
        echo 'Slack notification failed but ignored'
    } finally {
        try {
            sh(returnStatus: true, script: "rm -f '${messageFile}' '${payloadFile}'")
        } catch (Exception ignored) {
            echo 'Slack notification payload cleanup failed but ignored'
        }
    }
}

def readTrivySummary(String serviceType) {
    Map summary = [
        status        : 'TRIVY_SCAN_INCOMPLETE',
        high_count    : 'N/A',
        critical_count: 'N/A'
    ]
    String resultPath = ".trivy-result-${serviceType}-${env.BUILD_NUMBER ?: 'unknown'}.json"
    try {
        if (fileExists(resultPath)) {
            String parsedText = sh(
                returnStdout: true,
                script: """
                    python3 - '${resultPath}' <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as result_file:
    data = json.load(result_file)

print(f"status={data.get('status', 'TRIVY_SCAN_INCOMPLETE')}")
print(f"high_count={data.get('high_count', 'N/A')}")
print(f"critical_count={data.get('critical_count', 'N/A')}")
PY
                """
            ).trim()
            parsedText.split('\\n').each { line ->
                int separator = line.indexOf('=')
                if (separator > 0) {
                    String key = line.substring(0, separator)
                    String value = line.substring(separator + 1)
                    if (summary.containsKey(key)) {
                        summary[key] = value?.trim() ? value.trim() : summary[key]
                    }
                }
            }
        } else {
            echo "Trivy summary file not found: ${resultPath}; using incomplete defaults."
        }
    } catch (Exception error) {
        echo "Unable to read Trivy summary from ${resultPath}; using incomplete defaults. Reason: ${error.getClass().getSimpleName()}: ${error.getMessage()}"
    }
    return summary
}

def trivySlackDetails(String serviceType) {
    Map trivy = readTrivySummary(serviceType)
    return [
        'Trivy'          : trivy.status,
        'Trivy HIGH'     : trivy.high_count,
        'Trivy CRITICAL' : trivy.critical_count,
        'Trivy Mode'     : 'WARNING',
        'Trivy Gate'     : 'NOT_APPLIED',
        'Trivy Report'   : 'Jenkins Artifact 확인'
    ]
}

def readEcsServiceRevisionSafely(String serviceName) {
    try {
        return sh(
            script: """
                set -eu
                aws ecs describe-services \
                  --region '${env.AWS_REGION}' \
                  --cluster '${env.ECS_CLUSTER_NAME}' \
                  --services '${serviceName}' \
                  --query 'services[0].taskDefinition' \
                  --output text
            """,
            returnStdout: true
        ).trim()
    } catch (Exception ignored) {
        echo 'Unable to read final ECS revision for Slack notification; ignored.'
        return 'UNKNOWN'
    }
}

def maskSensitiveText(String text) {
    if (text == null) {
        return 'N/A'
    }
    String masked = text
    masked = masked.replaceAll(/arn:aws:[A-Za-z0-9_:\\/+=,.@-]+/, '[MASKED_ARN]')
    masked = masked.replaceAll(/(?<![0-9])[0-9]{12}(?![0-9])/, '[MASKED_ACCOUNT]')
    masked = masked.replaceAll(/[0-9]{12}\.dkr\.ecr\.[A-Za-z0-9-]+\.amazonaws\.com\/[A-Za-z0-9._\/-]+(:[A-Za-z0-9._-]+)?/, '[MASKED_ECR_URI]')
    masked = masked.replaceAll(/https?:\/\/hooks\.slack\.com\/[A-Za-z0-9\/+_-]+/, '[MASKED_SLACK_WEBHOOK]')
    masked = masked.replaceAll(/https?:\/\/[^\\s"']*X-Amz-Signature=[^\\s"']+/, '[MASKED_PRESIGNED_URL]')
    masked = masked.replaceAll(/(ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]+/, '[MASKED_GITHUB_TOKEN]')
    masked = masked.replaceAll(/A[KS]IA[0-9A-Z]{16}/, '[MASKED_AWS_KEY]')
    masked = masked.replaceAll(/(?i)(password|passwd|pwd|secret|token|authorization|credential)(\\s*[:=]\\s*)[^\\s,'"}]+/, '$1$2[MASKED_SECRET]')
    masked = masked.replaceAll(/(?i)(db[_-]?(host|user|password)|database[_-]?url)(\\s*[:=]\\s*)[^\\s,'"}]+/, '$1$3[MASKED_DB]')
    masked = masked.replaceAll(/https:\/\/sqs\.[A-Za-z0-9-]+\.amazonaws\.com\/[0-9]{12}\/[A-Za-z0-9._-]+/, '[MASKED_QUEUE_URL]')
    masked = masked.replaceAll(/s3:\/\/[^\\s,'"}]+/, '[MASKED_S3_PATH]')
    masked = masked.replaceAll(/(?<![0-9])(?:10|172\\.(?:1[6-9]|2[0-9]|3[0-1])|192\\.168)\\.[0-9]{1,3}\\.[0-9]{1,3}(?![0-9])/, '[MASKED_IP]')
    masked = masked.replaceAll(/(?<![0-9])(?:[0-9]{1,3}\\.){3}[0-9]{1,3}(?![0-9])/, '[MASKED_IP]')
    masked = masked.replaceAll(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/, '[MASKED_EMAIL]')
    return masked
}

def truncateText(String text, int maxLength = 12000) {
    if (text == null) {
        return 'N/A'
    }
    if (text.length() <= maxLength) {
        return text
    }
    return text.substring(text.length() - maxLength)
}

def collectConsoleLogTail(int lineCount = 200) {
    try {
        return maskSensitiveText(truncateText(currentBuild.rawBuild.getLog(lineCount).join('\n')))
    } catch (Exception ignored) {
        echo 'AI failure summary: Jenkins console log tail collection failed but ignored.'
        return 'LOG_COLLECTION_FAILED'
    }
}

def runMaskedCommand(String command, int maxLength = 8000) {
    try {
        String output = sh(script: command, returnStdout: true).trim()
        return maskSensitiveText(truncateText(output, maxLength))
    } catch (Exception ignored) {
        return 'LOG_COLLECTION_FAILED'
    }
}

def collectWorkerServiceDiagnostics(String serviceName, String logGroupName) {
    String serviceEvents = runMaskedCommand("""
        set +e
        aws ecs describe-services \
          --region '${env.AWS_REGION}' \
          --cluster '${env.ECS_CLUSTER_NAME}' \
          --services '${serviceName}' \
          --query 'services[0].events[0:8].[createdAt,message]' \
          --output text
    """)
    String stoppedTasks = runMaskedCommand("""
        set +e
        STOPPED_TASK_ARNS=\$(aws ecs list-tasks \
          --region '${env.AWS_REGION}' \
          --cluster '${env.ECS_CLUSTER_NAME}' \
          --service-name '${serviceName}' \
          --desired-status STOPPED \
          --max-results 5 \
          --query 'taskArns' \
          --output text 2>/dev/null)
        if [ -n "\${STOPPED_TASK_ARNS}" ] && [ "\${STOPPED_TASK_ARNS}" != "None" ]; then
          aws ecs describe-tasks \
            --region '${env.AWS_REGION}' \
            --cluster '${env.ECS_CLUSTER_NAME}' \
            --tasks \${STOPPED_TASK_ARNS} \
            --query 'tasks[].[taskArn,taskDefinitionArn,stopCode,stoppedReason]' \
            --output text
        else
          echo 'NO_RECENT_STOPPED_TASKS'
        fi
    """)
    String cloudWatchLogs = runMaskedCommand("""
        set +e
        START_TIME=\$(( \$(date +%s%3N) - 600000 ))
        aws logs filter-log-events \
          --region '${env.AWS_REGION}' \
          --log-group-name '${logGroupName}' \
          --start-time "\${START_TIME}" \
          --limit 30 \
          --query 'events[].message' \
          --output text
    """)
    return [
        service_events  : serviceEvents,
        stopped_tasks   : stoppedTasks,
        cloudwatch_logs : cloudWatchLogs
    ]
}

def buildAiFailurePrompt(String serviceName, Map context) {
    String contextJson = groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(context))
    return """너는 SecureVoiceGuard CI/CD 장애 분석 보조 에이전트다.

아래 정보는 Jenkins Pipeline 실패 이후 수집된 메타데이터와 마스킹된 로그다.
제공된 정보 안에서만 판단하고, 확정 원인이 아니라 "추정 원인"으로 표현해라.
민감정보, 계정 ID, ARN, IP, URL, Secret, Token, DB 정보, Queue URL, S3 경로는 출력하지 마라.
Jenkins console log tail이 LOG_COLLECTION_FAILED이면 Slack 요약에 언급하지 마라. 이것은 배포 실패 원인이 아니라 보조 로그 수집 제한이다.
Trivy Mode가 WARNING이고 Gate가 NOT_APPLIED이면 Trivy findings를 배포 실패 원인이나 Next Action으로 쓰지 마라.
내부 테스트 관련 파라미터나 테스트 맥락을 암시하는 표현은 출력하지 마라.
Worker는 이번 범위에서 SQS/DLQ/RDS/S3/inference 런타임 원인 분석을 하지 말고 배포 실패 정보만 요약해라.
Rollback 결과가 RECOVERY_VERIFIED이면 baseline revision으로 정상 복구된 것으로 표현해라.
Rollback 결과가 ROLLBACK_FAILED이면 수동 복구 확인이 필요하다고 표현해라.
Rollback 결과가 ROLLBACK_NOT_REQUIRED이면 rollback이 필요 없는 실패로 표현해라.
Slack 운영 알림용으로 짧고 실무적으로 작성해라.

출력 형식:

Likely Cause:
<1~2문장. 실패 stage와 target 기준의 추정 원인만 작성>

Rollback Status:
<rollback result와 복구 여부를 1문장으로 작성>

Next Action:
<운영자가 다음에 확인할 위치만 1~2문장으로 작성>

서비스: ${serviceName}
입력 데이터:
${contextJson}
"""
}

def writeAiFailureSummaryArtifact(String serviceType, Map summary) {
    String artifactPath = ".ai-failure-summary-${serviceType}-${env.BUILD_NUMBER ?: 'unknown'}.json"
    try {
        writeFile(
            file: artifactPath,
            text: groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(summary))
        )
    } catch (Exception ignored) {
        echo "AI failure summary: unable to write ${artifactPath}; ignored."
    }
    return artifactPath
}

def resolveWorkerAiSummaryTarget() {
    if (env.FREE_UPDATE_REQUESTED == 'true' && env.PAID_UPDATE_REQUESTED == 'true') {
        return 'Free/Paid Worker'
    }
    if (env.PAID_UPDATE_REQUESTED == 'true') {
        return 'Paid Worker'
    }
    if (env.FREE_UPDATE_REQUESTED == 'true') {
        return 'Free Worker'
    }
    return 'Worker Build/Pre-Deploy'
}

def fallbackWorkerLikelyCause(String failedStage, String target) {
    if ((target ?: '').contains('Free/Paid')) {
        return 'Worker 배포 검증 실패가 감지되었습니다.'
    }
    if ((target ?: '').contains('Paid')) {
        return 'Paid Worker 배포 후 RUNNING 또는 revision 검증 단계에서 실패가 감지되었습니다.'
    }
    if ((target ?: '').contains('Free')) {
        return 'Free Worker 배포 후 RUNNING 또는 revision 검증 단계에서 실패가 감지되었습니다.'
    }
    if ((failedStage ?: '').contains('SERVICE') || (failedStage ?: '').contains('VERIFY') || (failedStage ?: '').contains('VERIFICATION')) {
        return 'Worker 배포 검증 단계에서 실패가 감지되었습니다.'
    }
    return 'ECS Service Update 이전 단계에서 실패했습니다.'
}

def fallbackWorkerRollbackStatusText(String rollbackStatus, String target, String compensationRollback) {
    boolean compensationNeeded = compensationRollback != null && compensationRollback != 'N/A'
    switch (rollbackStatus ?: 'N/A') {
        case 'RECOVERY_VERIFIED':
            if (compensationNeeded || (target ?: '').contains('Free/Paid')) {
                return 'RECOVERY_VERIFIED — Worker rollback 및 필요한 보상 rollback 처리가 완료되었습니다.'
            }
            return 'RECOVERY_VERIFIED — baseline revision으로 정상 복구되었습니다.'
        case 'ROLLBACK_FAILED':
            return 'RECOVERY_FAILED — 수동 복구 확인이 필요합니다.'
        case 'EXTERNAL_UPDATE_DETECTED':
            return 'MANUAL_REVIEW_REQUIRED — 외부 업데이트가 감지되어 수동 확인이 필요합니다.'
        case 'ROLLBACK_NOT_REQUIRED':
            return 'NOT_REQUIRED'
        case 'ROLLBACK_NOT_COMPLETED':
            return 'NOT_COMPLETED — rollback 완료 여부 확인이 필요합니다.'
        default:
            return rollbackStatus ?: 'N/A'
    }
}

def fallbackWorkerNextAction(String rollbackStatus, String target) {
    switch (rollbackStatus ?: 'N/A') {
        case 'ROLLBACK_FAILED':
            return '즉시 ECS Service Events, stopped task reason, 현재 task definition revision, Free/Paid Worker final revision을 확인하고 baseline revision으로 수동 rollback을 검토하세요.'
        case 'ROLLBACK_NOT_REQUIRED':
            return '실패한 Jenkins stage의 build/test/docker/ecr 로그를 확인하세요.'
        default:
            if ((target ?: '').contains('Free/Paid')) {
                return 'Free/Paid Worker의 final task definition revision, ECS Service Events, stopped task reason, Worker CloudWatch Logs를 확인하세요.'
            }
            return 'ECS Service Events, stopped task reason, Worker CloudWatch Logs, task definition revision, container startup error를 우선 확인하세요.'
    }
}

def invokeBedrockFailureSummary(String serviceType, String prompt, Map metadata) {
    String modelId = params.BEDROCK_MODEL_ID ?: env.BEDROCK_MODEL_ID
    if (modelId == null || modelId.trim() == '') {
        Map skipped = [
            enabled          : true,
            provider         : 'bedrock',
            status           : 'BEDROCK_SKIPPED_EMPTY_MODEL_ID',
            error            : 'BEDROCK_MODEL_ID is not configured',
            failed_stage     : metadata.failed_stage ?: 'N/A',
            rollback_status  : metadata.rollback_status ?: 'N/A',
            summary_for_slack: 'AI Failure Summary skipped: BEDROCK_MODEL_ID is not configured.',
            masked           : true
        ]
        writeAiFailureSummaryArtifact(serviceType, skipped)
        return skipped
    }

    String promptFile = ".ai-failure-prompt-${serviceType}-${env.BUILD_NUMBER ?: 'unknown'}.txt"
    String requestFile = ".ai-failure-request-${serviceType}-${env.BUILD_NUMBER ?: 'unknown'}.json"
    String responseFile = ".ai-failure-response-${serviceType}-${env.BUILD_NUMBER ?: 'unknown'}.json"
    String errorFile = ".ai-failure-error-${serviceType}-${env.BUILD_NUMBER ?: 'unknown'}.log"
    String runtimeSummaryFile = ".ai-failure-runtime-summary-${serviceType}-${env.BUILD_NUMBER ?: 'unknown'}.json"
    String propertiesFile = ".ai-failure-summary-${serviceType}-${env.BUILD_NUMBER ?: 'unknown'}.properties"
    writeFile(file: promptFile, text: maskSensitiveText(truncateText(prompt, 12000)))

    int status = sh(
        returnStatus: true,
        script: """
            set +x
            set +e
            python3 - '${promptFile}' '${requestFile}' <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as prompt_file:
    prompt = prompt_file.read()

# Bedrock model id/region/model access must be verified in the target AWS account.
# This request body uses the Anthropic Claude Messages API schema.
with open(sys.argv[2], "w", encoding="utf-8") as request_file:
    json.dump({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 700,
        "temperature": 0.2,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": prompt}]
        }]
    }, request_file)
PY
            rm -f '${responseFile}' '${errorFile}' '${runtimeSummaryFile}' '${propertiesFile}'
            timeout 30 aws bedrock-runtime invoke-model \
              --region "\${BEDROCK_REGION:-${env.AWS_REGION}}" \
              --model-id '${modelId}' \
              --content-type 'application/json' \
              --accept 'application/json' \
              --cli-binary-format raw-in-base64-out \
              --body "fileb://${requestFile}" \
              '${responseFile}' >/dev/null 2>'${errorFile}'
            BEDROCK_STATUS=\$?
            BEDROCK_MODEL_ID_FOR_SUMMARY='${modelId}' python3 - '${responseFile}' '${runtimeSummaryFile}' '${errorFile}' '${propertiesFile}' "\${BEDROCK_STATUS}" <<'PY'
import json
import os
import sys

response_path, summary_path, error_path, properties_path, status = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
summary_text = ""
error = ""
status_name = "SUMMARY_FAILED"
section_labels = ["Likely Cause", "Rollback Status", "Next Action"]

def read_error():
    try:
        with open(error_path, "r", encoding="utf-8", errors="replace") as error_file:
            return error_file.read().strip()
    except Exception:
        return ""

def classify_error(message):
    lowered = message.lower()
    if "accessdenied" in lowered or "not authorized" in lowered or "unauthorized" in lowered:
        return "BEDROCK_ACCESS_DENIED"
    if "validationexception" in lowered or "validation" in lowered:
        return "BEDROCK_VALIDATION_ERROR"
    return "BEDROCK_INVOKE_FAILED"

def extract_sections(text):
    sections = {label: "" for label in section_labels}
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        matched = None
        for label in section_labels:
            if line.lower().startswith(label.lower() + ":"):
                matched = label
                remainder = line[len(label) + 1:].strip()
                sections[label] = remainder
                break
        if matched:
            current = matched
            continue
        if current and line:
            if sections[current]:
                sections[current] += " "
            sections[current] += line
    return sections

if status == "0":
    try:
        with open(response_path, "r", encoding="utf-8") as response_file:
            response = json.load(response_file)
        if isinstance(response.get("content"), list) and response["content"]:
            summary_text = response["content"][0].get("text", "")
        elif isinstance(response.get("output"), dict):
            content = response["output"].get("message", {}).get("content", [])
            if content:
                summary_text = content[0].get("text", "")
        elif response.get("generation"):
            summary_text = response.get("generation", "")
        if not summary_text:
            error = "Bedrock response parsing failed"
            status_name = "BEDROCK_RESPONSE_PARSE_FAILED"
        else:
            status_name = "SUMMARY_CREATED"
    except Exception as exc:
        error = f"Bedrock response parsing failed: {exc}"
        status_name = "BEDROCK_RESPONSE_PARSE_FAILED"
else:
    stderr_text = read_error()
    error = f"Bedrock invoke-model failed with exit code {status}"
    if stderr_text:
        error = f"{error}: {stderr_text[:1200]}"
    status_name = classify_error(stderr_text)

sections = extract_sections(summary_text) if summary_text else {label: "" for label in section_labels}
payload = {
    "enabled": True,
    "provider": "bedrock",
    "model": os.environ.get("BEDROCK_MODEL_ID_FOR_SUMMARY", "configured-via-jenkins-parameter"),
    "status": status_name,
    "invoke_exit_code": status,
    "summary_for_slack": summary_text if summary_text else "AI Failure Summary failed. Check Jenkins console and AWS deployment logs manually.",
    "likely_cause": sections.get("Likely Cause", ""),
    "rollback_status_text": sections.get("Rollback Status", ""),
    "next_action": sections.get("Next Action", ""),
    "error": error,
    "masked": True,
}
with open(summary_path, "w", encoding="utf-8") as summary_file:
    json.dump(payload, summary_file, indent=2, ensure_ascii=False)
with open(properties_path, "w", encoding="utf-8") as properties_file:
    for key in ["enabled", "provider", "model", "status", "invoke_exit_code", "summary_for_slack", "likely_cause", "rollback_status_text", "next_action", "error", "masked"]:
        value = payload.get(key, "")
        value = str(value).replace("\\r", "\\\\r").replace("\\n", "\\\\n")
        properties_file.write(f"{key}={value}\\n")
PY
            exit 0
        """
    )
    Map parsed = [
        enabled          : true,
        provider         : 'bedrock',
        status           : 'SUMMARY_FAILED',
        invoke_exit_code : 'N/A',
        error            : "AI summary shell wrapper failed with exit code ${status}",
        summary_for_slack: 'AI Failure Summary failed. Check Jenkins console and AWS deployment logs manually.',
        likely_cause     : fallbackWorkerLikelyCause(metadata.failed_stage ?: 'N/A', metadata.target ?: 'Unknown'),
        rollback_status_text: fallbackWorkerRollbackStatusText(metadata.rollback_status ?: 'N/A', metadata.target ?: 'Unknown', metadata.compensation_rollback ?: 'N/A'),
        next_action      : fallbackWorkerNextAction(metadata.rollback_status ?: 'N/A', metadata.target ?: 'Unknown'),
        masked           : true
    ]
    try {
        if (fileExists(errorFile)) {
            String bedrockError = maskSensitiveText(truncateText(readFile(errorFile), 1200))
            if (bedrockError?.trim()) {
                echo "AI failure summary: Bedrock stderr summary: ${bedrockError.trim()}"
            }
        }
        if (fileExists(propertiesFile)) {
            Map fromProperties = [:]
            readFile(propertiesFile).split('\\n').each { line ->
                int separator = line.indexOf('=')
                if (separator > 0) {
                    String key = line.substring(0, separator)
                    String value = line.substring(separator + 1)
                    fromProperties[key] = value.replace('\\n', '\n').replace('\\r', '\r')
                }
            }
            parsed = fromProperties
            parsed.enabled = parsed.enabled == 'true'
            parsed.masked = parsed.masked == 'true'
        }
    } catch (Exception error) {
        echo "AI failure summary: unable to parse summary properties; using failed fallback. Reason: ${error.getClass().getSimpleName()}: ${error.getMessage()}"
    }
    echo "AI failure summary: shell wrapper exit code=${status}, Bedrock invoke exit code=${parsed.invoke_exit_code ?: 'N/A'}, summary status=${parsed.status ?: 'N/A'}, error=${maskSensitiveText(truncateText(parsed.error ?: 'N/A', 1200))}"
    parsed.failed_stage = metadata.failed_stage ?: 'N/A'
    parsed.likely_cause = parsed.likely_cause ?: fallbackWorkerLikelyCause(parsed.failed_stage, metadata.target ?: 'Unknown')
    parsed.evidence = metadata.evidence ?: 'N/A'
    parsed.impact = metadata.impact ?: 'N/A'
    parsed.rollback_status = metadata.rollback_status ?: 'N/A'
    parsed.compensation_rollback = metadata.compensation_rollback ?: 'N/A'
    parsed.rollback_status_text = parsed.rollback_status_text ?:
        fallbackWorkerRollbackStatusText(parsed.rollback_status, metadata.target ?: 'Unknown', parsed.compensation_rollback)
    parsed.next_action = parsed.next_action ?: fallbackWorkerNextAction(parsed.rollback_status, metadata.target ?: 'Unknown')
    parsed.masked = true
    writeAiFailureSummaryArtifact(serviceType, parsed)
    sh(returnStatus: true, script: "rm -f '${promptFile}' '${requestFile}' '${responseFile}' '${runtimeSummaryFile}' '${propertiesFile}' '${errorFile}'")
    return parsed
}

def sendAiFailureSummarySlack(String title, Map summary, Map details) {
    sendSlackNotification(title, [
        Service            : details.service ?: 'N/A',
        Target             : details.target ?: 'N/A',
        Job                : env.JOB_NAME,
        Build              : env.BUILD_NUMBER,
        'Failed Stage'     : details.failed_stage ?: 'N/A',
        'AI Summary Status': summary.status ?: 'N/A',
        'Likely Cause'     : summary.likely_cause ?: fallbackWorkerLikelyCause(details.failed_stage ?: 'N/A', details.target ?: 'Unknown'),
        'Rollback Status'  : summary.rollback_status_text ?:
            fallbackWorkerRollbackStatusText(details.rollback_status ?: 'N/A', details.target ?: 'Unknown', details.compensation_rollback ?: 'N/A'),
        'Next Action'      : summary.next_action ?: fallbackWorkerNextAction(details.rollback_status ?: 'N/A', details.target ?: 'Unknown'),
        Jenkins            : maskSensitiveText(env.BUILD_URL ?: 'N/A'),
        Runbook            : workerRunbookLink()
    ])
}

def generateWorkerAiFailureSummary() {
    try {
        Map trivy = readTrivySummary('worker')
        String baseName = env.ECS_CLUSTER_NAME.replace('-cluster', '')
        Map freeDiagnostics = collectWorkerServiceDiagnostics(env.FREE_ECS_SERVICE_NAME, "/ecs/${baseName}-free-worker")
        Map paidDiagnostics = collectWorkerServiceDiagnostics(env.PAID_ECS_SERVICE_NAME, "/ecs/${baseName}-paid-worker")
        String rollbackStatus = (env.FREE_UPDATE_REQUESTED == 'true' || env.PAID_UPDATE_REQUESTED == 'true') ?
            (env.WORKER_ROLLBACK_RESULT ?: 'ROLLBACK_NOT_COMPLETED') : 'ROLLBACK_NOT_REQUIRED'
        String target = resolveWorkerAiSummaryTarget()
        String impact = (env.FREE_UPDATE_REQUESTED == 'true' || env.PAID_UPDATE_REQUESTED == 'true') ?
            'Worker ECS Service Update 이후 실패하여 Free/Paid rollback 결과 확인이 필요합니다.' :
            'Worker ECS Service Update 전 실패이므로 운영 Worker service 변경은 없습니다.'
        String compensationRollback = env.PAID_UPDATE_REQUESTED == 'true' ? 'FREE_COMPENSATING_ROLLBACK_REQUIRED' : 'N/A'
        Map context = [
            job_name                         : env.JOB_NAME,
            build_number                     : env.BUILD_NUMBER,
            build_url                        : maskSensitiveText(env.BUILD_URL ?: 'N/A'),
            git_commit                       : env.GIT_COMMIT_SHA ?: env.GIT_SHORT_SHA ?: 'N/A',
            git_short_sha                    : env.GIT_SHORT_SHA ?: 'N/A',
            image_uri                        : maskSensitiveText(env.IMAGE_URI ?: 'N/A'),
            image_digest                     : env.IMAGE_DIGEST ?: 'N/A',
            deploy_phase                     : env.DEPLOY_PHASE ?: 'N/A',
            free_update_requested            : env.FREE_UPDATE_REQUESTED ?: 'false',
            paid_update_requested            : env.PAID_UPDATE_REQUESTED ?: 'false',
            free_baseline_task_definition    : maskSensitiveText(env.FREE_PREVIOUS_TASK_DEFINITION_ARN ?: 'N/A'),
            paid_baseline_task_definition    : maskSensitiveText(env.PAID_PREVIOUS_TASK_DEFINITION_ARN ?: 'N/A'),
            free_requested_task_definition   : maskSensitiveText(env.FREE_TASK_DEFINITION_ARN ?: 'N/A'),
            paid_requested_task_definition   : maskSensitiveText(env.PAID_TASK_DEFINITION_ARN ?: 'N/A'),
            free_final_task_definition       : maskSensitiveText(env.FREE_FINAL_TASK_DEFINITION_ARN ?: readEcsServiceRevisionSafely(env.FREE_ECS_SERVICE_NAME)),
            paid_final_task_definition       : maskSensitiveText(env.PAID_FINAL_TASK_DEFINITION_ARN ?: readEcsServiceRevisionSafely(env.PAID_ECS_SERVICE_NAME)),
            worker_rollback_result           : rollbackStatus,
            free_compensation_rollback_result: compensationRollback,
            trivy_status                     : trivy.status,
            trivy_high_count                 : trivy.high_count,
            trivy_critical_count             : trivy.critical_count,
            trivy_mode                       : 'WARNING',
            trivy_gate                       : 'NOT_APPLIED',
            jenkins_console_log_tail         : collectConsoleLogTail(),
            free_worker_ecs_events           : freeDiagnostics.service_events,
            paid_worker_ecs_events           : paidDiagnostics.service_events,
            free_worker_stopped_tasks        : freeDiagnostics.stopped_tasks,
            paid_worker_stopped_tasks        : paidDiagnostics.stopped_tasks,
            free_worker_cloudwatch_logs_tail : freeDiagnostics.cloudwatch_logs,
            paid_worker_cloudwatch_logs_tail : paidDiagnostics.cloudwatch_logs
        ]
        Map metadata = [
            failed_stage         : env.DEPLOY_PHASE ?: 'N/A',
            rollback_status      : rollbackStatus,
            impact               : impact,
            evidence             : "${freeDiagnostics.service_events}\n${paidDiagnostics.service_events}",
            compensation_rollback: compensationRollback,
            target               : target
        ]
        Map summary = invokeBedrockFailureSummary('worker', buildAiFailurePrompt('AI Worker', context), metadata)
        sendAiFailureSummarySlack(':mag: Worker AI Failure Summary', summary, [
            service              : 'AI Worker',
            target               : target,
            failed_stage         : env.DEPLOY_PHASE ?: 'N/A',
            rollback_status      : rollbackStatus,
            compensation_rollback: compensationRollback
        ])
    } catch (Exception ignored) {
        echo 'AI failure summary for Worker failed but ignored.'
        writeAiFailureSummaryArtifact('worker', [
            enabled          : true,
            provider         : 'bedrock',
            status           : 'SUMMARY_FAILED',
            error            : 'AI failure summary failed before or during helper execution',
            summary_for_slack: 'AI Failure Summary failed. Check Jenkins console and AWS deployment logs manually.',
            masked           : true
        ])
    }
}

pipeline {
    agent any

    options {
        // 장애 분석을 위해 로그에 시간을 기록하고, 동일 Job의 배포가 동시에 실행되지 않도록 합니다.
        timestamps()
        disableConcurrentBuilds()
        // Jenkins 저장공간이 계속 증가하지 않도록 최근 빌드 이력 20개만 보관합니다.
        buildDiscarder(logRotator(numToKeepStr: '20'))
        // Workspace Checkout은 Source Checkout Stage에서 Shallow Clone으로 한 번만 수행합니다.
        skipDefaultCheckout(true)
        // Free와 Paid Worker를 순차 배포하므로 전체 Pipeline 제한 시간을 길게 설정합니다.
        timeout(time: 45, unit: 'MINUTES')
    }

    parameters {
        choice(
            name: 'ROLLBACK_TEST_MODE',
            choices: ['NONE', 'FREE_VERIFY_FAIL', 'PAID_VERIFY_FAIL'],
            description: 'Worker automatic rollback verification only'
        )
        string(
            name: 'BEDROCK_MODEL_ID',
            defaultValue: 'anthropic.claude-3-haiku-20240307-v1:0',
            description: 'Optional Bedrock model id for AI Failure Summary. Leave empty to skip AI summary.'
        )
    }

    environment {
        DOCKER_BUILDKIT = '1'
        TRIVY_IMAGE = 'aquasec/trivy:0.71.0'
        TRIVY_REPORT_DIR = 'trivy-reports'
        DEPLOYMENT_SUMMARY_DIR = 'deployment-summaries'
        APP_ENV = 'ci'
        WORKER_MODE = 'mock'
        AWS_REGION = 'ap-northeast-2'
        AWS_ACCOUNT_ID = '455535733131'
        ECR_REPOSITORY = 'nes2net-ai-worker'
        ECS_CLUSTER_NAME = 'securevoice-dev-cluster'
        FREE_ECS_SERVICE_NAME = 'securevoice-dev-free-worker-service'
        FREE_ECS_TASK_FAMILY = 'securevoice-dev-free-worker'
        FREE_CONTAINER_NAME = 'free-worker'
        PAID_ECS_SERVICE_NAME = 'securevoice-dev-paid-worker-service'
        PAID_ECS_TASK_FAMILY = 'securevoice-dev-paid-worker'
        PAID_CONTAINER_NAME = 'paid-worker'
        MODEL_DIR = '/models'
        MODEL_PATH = '/models/wav2LM_Nes2Net_X.pth'
        LOCAL_AUDIO_PATH = './samples/fake_01.wav'
    }

    stages {
        // Webhook을 발생시킨 커밋을 Checkout하고 고정된 fairseq Submodule을 초기화합니다.
        stage('Source Checkout') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: scm.branches,
                    userRemoteConfigs: scm.userRemoteConfigs,
                    extensions: [[
                        $class: 'CloneOption',
                        shallow: true,
                        depth: 1,
                        noTags: true,
                        timeout: 10
                    ]]
                ])
                sh '''
                    set -eu
                    if ! git submodule update --init --recursive --depth 1; then
                      echo "Shallow submodule checkout failed; retrying with the full pinned submodule history."
                      git submodule update --init --recursive
                    fi
                '''
                script {
                    env.FREE_UPDATE_REQUESTED = 'false'
                    env.PAID_UPDATE_REQUESTED = 'false'
                    env.DEPLOY_PHASE = 'PRE_DEPLOY'
                    // 전체 SHA는 배포 추적용으로, 짧은 SHA는 이미지 태그용으로 저장합니다.
                    env.GIT_COMMIT_SHA = sh(
                        script: 'git rev-parse HEAD',
                        returnStdout: true
                    ).trim()
                    env.GIT_SHORT_SHA = sh(
                        script: 'git rev-parse --short=7 HEAD',
                        returnStdout: true
                    ).trim()
                    env.GIT_REPOSITORY_URL = sh(
                        script: 'git config --get remote.origin.url',
                        returnStdout: true
                    ).trim()
                    env.IMAGE_TAG = "build-${env.BUILD_NUMBER}-${env.GIT_SHORT_SHA}"
                }
                echo "Image tag: ${env.IMAGE_TAG}"
            }
        }

        // Worker 문법과 주요 모듈을 검증하고 fairseq 테스트를 제외한 Repository 테스트를 실행합니다.
        stage('Worker Build & Test') {
            steps {
                sh '''
                    set -eu
                    python3 -m compileall \
                      worker.py \
                      inference.py \
                      config.py \
                      model_downloader.py \
                      s3_client.py \
                      sqs_client.py \
                      db_client.py \
                      healthcheck.py \
                      model_scripts
                    python3 healthcheck.py
                    if find . -path ./fairseq_src -prune -o -maxdepth 3 -type f \\( -name "test_*.py" -o -name "*_test.py" \\) -print | grep -q .; then
                      python3 -m venv .venv
                      . .venv/bin/activate
                      python -m pip install --upgrade pip setuptools wheel
                      python -m pip install -r requirements-test.txt
                      python -m pytest --ignore=fairseq_src
                    else
                      echo "No pytest test files found. Skipping pytest."
                    fi
                '''
            }
        }

        // Free와 Paid Service가 함께 사용할 Worker 이미지를 한 번만 빌드합니다.
        stage('BuildKit Image Build') {
            steps {
                script {
                    env.ECR_REGISTRY = "${env.AWS_ACCOUNT_ID}.dkr.ecr.${env.AWS_REGION}.amazonaws.com"
                    env.IMAGE_URI = "${env.ECR_REGISTRY}/${env.ECR_REPOSITORY}:${env.IMAGE_TAG}"
                }
                sh '''
                    set -eu
                    docker build \
                      --progress=plain \
                      --label securevoice.service=worker \
                      --label securevoice.git_sha="${GIT_SHORT_SHA}" \
                      --label securevoice.jenkins_build="${BUILD_NUMBER}" \
                      -t "${IMAGE_URI}" \
                      .
                '''
            }
        }

        // 빌드한 이미지에서 Health Check와 주요 Worker 모듈 Import가 가능한지 확인합니다.
        stage('Docker Image Smoke Test') {
            steps {
                sh '''
                    set -eu

                    docker run --rm -i \
                      -e APP_ENV="${APP_ENV}" \
                      -e WORKER_MODE="${WORKER_MODE}" \
                      -e AWS_REGION="${AWS_REGION}" \
                      -e MODEL_DIR="${MODEL_DIR}" \
                      -e MODEL_PATH="${MODEL_PATH}" \
                      -e LOCAL_AUDIO_PATH="${LOCAL_AUDIO_PATH}" \
                      "${IMAGE_URI}" \
                      python healthcheck.py

                    docker run --rm -i \
                      -e APP_ENV="${APP_ENV}" \
                      -e WORKER_MODE="${WORKER_MODE}" \
                      -e AWS_REGION="${AWS_REGION}" \
                      -e MODEL_DIR="${MODEL_DIR}" \
                      -e MODEL_PATH="${MODEL_PATH}" \
                      -e LOCAL_AUDIO_PATH="${LOCAL_AUDIO_PATH}" \
                      "${IMAGE_URI}" \
                      python - <<'PY'
import config
import db_client
import healthcheck
import inference
import model_downloader
import s3_client
import sqs_client
import worker

print("worker image import smoke test passed")
PY
                '''
            }
        }

        // PyTorch와 fairseq를 포함한 Worker 이미지를 ECR Push 전에 Scan하고 결과를 경고로 기록합니다.
        stage('Trivy Image Scan - Warning Mode') {
            steps {
                sh '''
                    set -u

                    REPORT_FILE="trivy-worker-${BUILD_NUMBER}.json"
                    REPORT_PATH="${TRIVY_REPORT_DIR}/${REPORT_FILE}"
                    TRIVY_RESULT_PATH=".trivy-result-worker-${BUILD_NUMBER}.json"
                    TRIVY_CONTAINER_NAME="trivy-worker-${BUILD_NUMBER}"

                    mkdir -p "${TRIVY_REPORT_DIR}" .trivy-cache
                    rm -f "${REPORT_PATH}"
                    python3 - "${TRIVY_RESULT_PATH}" <<'PY'
import json
import sys

with open(sys.argv[1], "w", encoding="utf-8") as result_file:
    json.dump({
        "status": "TRIVY_SCAN_INCOMPLETE",
        "high_count": "N/A",
        "critical_count": "N/A",
    }, result_file)
PY
                    docker rm -f "${TRIVY_CONTAINER_NAME}" >/dev/null 2>&1 || true

                    cleanup() {
                      docker rm -f "${TRIVY_CONTAINER_NAME}" >/dev/null 2>&1 || true
                    }
                    trap cleanup EXIT

                    echo "Starting Worker image vulnerability scan in Warning Mode."
                    echo "Worker image scan may take longer because the image includes PyTorch and fairseq."
                    echo "Scan target: ${IMAGE_URI}"
                    echo "Severity: HIGH,CRITICAL"
                    echo "Trivy image: ${TRIVY_IMAGE}"

                    set +e
                    timeout --signal=TERM 15m docker run --rm \
                      --name "${TRIVY_CONTAINER_NAME}" \
                      -v /var/run/docker.sock:/var/run/docker.sock \
                      -v "${PWD}/.trivy-cache:/root/.cache/trivy" \
                      -v "${PWD}/${TRIVY_REPORT_DIR}:/reports" \
                      "${TRIVY_IMAGE}" \
                      image \
                      --scanners vuln \
                      --severity HIGH,CRITICAL \
                      --exit-code 0 \
                      --format json \
                      --output "/reports/${REPORT_FILE}" \
                      "${IMAGE_URI}"
                    TRIVY_STATUS=$?

                    if [ "${TRIVY_STATUS}" -ne 0 ] || [ ! -s "${REPORT_PATH}" ]; then
                      echo "TRIVY_SCAN_INCOMPLETE"
                      echo "WARNING: Trivy execution or vulnerability DB download failed. Deployment will continue."
                      exit 0
                    fi

                    REPORT_PATH="${REPORT_PATH}" TRIVY_RESULT_PATH="${TRIVY_RESULT_PATH}" python3 - <<'PY'
import json
import os

report_path = os.environ["REPORT_PATH"]
result_path = os.environ["TRIVY_RESULT_PATH"]

with open(report_path, "r", encoding="utf-8") as report_file:
    report = json.load(report_file)

counts = {"HIGH": 0, "CRITICAL": 0}

for result in report.get("Results", []):
    for vulnerability in result.get("Vulnerabilities") or []:
        severity = vulnerability.get("Severity")
        if severity in counts:
            counts[severity] += 1

total = counts["HIGH"] + counts["CRITICAL"]

if total:
    status = "TRIVY_SCAN_COMPLETED_WITH_FINDINGS"
else:
    status = "TRIVY_SCAN_COMPLETED_NO_FINDINGS"

with open(result_path, "w", encoding="utf-8") as result_file:
    json.dump({
        "status": status,
        "high_count": counts["HIGH"],
        "critical_count": counts["CRITICAL"],
    }, result_file)

print(status)
print(f"HIGH={counts['HIGH']}")
print(f"CRITICAL={counts['CRITICAL']}")
print("Warning Mode: vulnerabilities do not block deployment.")
PY
                    REPORT_STATUS=$?
                    if [ "${REPORT_STATUS}" -ne 0 ]; then
                      echo "TRIVY_SCAN_INCOMPLETE"
                      echo "WARNING: Trivy report parsing failed. Deployment will continue."
                    fi
                    exit 0
                '''
            }
        }

        // 공통 Worker 이미지를 Push하기 전에 Docker가 ECR에 인증하도록 로그인합니다.
        stage('ECR Login') {
            steps {
                // ECR Login은 ECS 배포 상태를 변경하지 않으므로 일시적 실패 시 재시도합니다.
                retry(2) {
                    sh '''
                        set -eu
                        aws ecr get-login-password --region "${AWS_REGION}" \
                          | docker login --username AWS --password-stdin "${ECR_REGISTRY}"
                    '''
                }
            }
        }

        // 공통 이미지를 한 번만 Push하고 두 Worker Service가 동일한 IMAGE_URI를 사용합니다.
        stage('ECR Push') {
            steps {
                // 동일한 고유 빌드 태그의 Push는 일시적 네트워크 실패 후 재시도해도 안전합니다.
                retry(2) {
                    sh '''
                        set -eu
                        docker push "${IMAGE_URI}"
                    '''
                }
                // Push 직후 ECR 메타데이터 조회가 잠시 지연될 수 있어 읽기 작업만 재시도합니다.
                retry(3) {
                    script {
                        env.IMAGE_DIGEST = sh(
                            script: '''
                                set -eu
                                aws ecr describe-images \
                                  --region "${AWS_REGION}" \
                                  --repository-name "${ECR_REPOSITORY}" \
                                  --image-ids imageTag="${IMAGE_TAG}" \
                                  --query 'imageDetails[0].imageDigest' \
                                  --output text
                            ''',
                            returnStdout: true
                        ).trim()
                    }
                }
                echo "Published shared Worker image digest: ${env.IMAGE_DIGEST}"
            }
        }

        // Free/Paid Worker 배포와 검증을 하나의 Stage에서 순차 처리합니다.
        stage('Worker Deploy & Verify') {
            options {
                // targeted polling으로 배포 시간을 줄이되 전체 배포 구간은 제한합니다.
                timeout(time: 15, unit: 'MINUTES')
            }
            steps {
                script {
                    echo '[Free] Baseline Capture'
                    env.FREE_PREVIOUS_TASK_DEFINITION_ARN = sh(
                        script: '''
                            set -eu
                            aws ecs describe-services \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --services "${FREE_ECS_SERVICE_NAME}" \
                              --query 'services[0].taskDefinition' \
                              --output text
                        ''',
                        returnStdout: true
                    ).trim()
                    echo '[Paid] Baseline Capture'
                    env.PAID_PREVIOUS_TASK_DEFINITION_ARN = sh(
                        script: '''
                            set -eu
                            aws ecs describe-services \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --services "${PAID_ECS_SERVICE_NAME}" \
                              --query 'services[0].taskDefinition' \
                              --output text
                        ''',
                        returnStdout: true
                    ).trim()
                    if (!env.FREE_PREVIOUS_TASK_DEFINITION_ARN || env.FREE_PREVIOUS_TASK_DEFINITION_ARN == 'None') {
                        error('Unable to capture the Free Worker rollback baseline task definition.')
                    }
                    if (!env.PAID_PREVIOUS_TASK_DEFINITION_ARN || env.PAID_PREVIOUS_TASK_DEFINITION_ARN == 'None') {
                        error('Unable to capture the Paid Worker rollback baseline task definition.')
                    }
                    env.FREE_PREVIOUS_IMAGE_URI = sh(
                        script: '''
                            set -eu
                            aws ecs describe-task-definition \
                              --region "${AWS_REGION}" \
                              --task-definition "${FREE_PREVIOUS_TASK_DEFINITION_ARN}" \
                              --query "taskDefinition.containerDefinitions[?name=='${FREE_CONTAINER_NAME}'].image | [0]" \
                              --output text
                        ''',
                        returnStdout: true
                    ).trim()
                    env.PAID_PREVIOUS_IMAGE_URI = sh(
                        script: '''
                            set -eu
                            aws ecs describe-task-definition \
                              --region "${AWS_REGION}" \
                              --task-definition "${PAID_PREVIOUS_TASK_DEFINITION_ARN}" \
                              --query "taskDefinition.containerDefinitions[?name=='${PAID_CONTAINER_NAME}'].image | [0]" \
                              --output text
                        ''',
                        returnStdout: true
                    ).trim()
                    env.FREE_PREVIOUS_DESIRED_COUNT = sh(
                        script: '''
                            set -eu
                            aws ecs describe-services \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --services "${FREE_ECS_SERVICE_NAME}" \
                              --query 'services[0].desiredCount' \
                              --output text
                        ''',
                        returnStdout: true
                    ).trim()
                    env.PAID_PREVIOUS_DESIRED_COUNT = sh(
                        script: '''
                            set -eu
                            aws ecs describe-services \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --services "${PAID_ECS_SERVICE_NAME}" \
                              --query 'services[0].desiredCount' \
                              --output text
                        ''',
                        returnStdout: true
                    ).trim()
                    if (!env.FREE_PREVIOUS_IMAGE_URI || env.FREE_PREVIOUS_IMAGE_URI == 'None' ||
                        !env.PAID_PREVIOUS_IMAGE_URI || env.PAID_PREVIOUS_IMAGE_URI == 'None') {
                        error('Unable to capture the Worker rollback baseline image URI.')
                    }
                    if (!env.FREE_PREVIOUS_DESIRED_COUNT || env.FREE_PREVIOUS_DESIRED_COUNT == 'None' ||
                        !env.PAID_PREVIOUS_DESIRED_COUNT || env.PAID_PREVIOUS_DESIRED_COUNT == 'None') {
                        error('Unable to capture the Worker rollback baseline desired count.')
                    }
                    echo "Captured Free Worker rollback baseline: ${env.FREE_PREVIOUS_TASK_DEFINITION_ARN}"
                    echo "Captured Paid Worker rollback baseline: ${env.PAID_PREVIOUS_TASK_DEFINITION_ARN}"
                    echo "Free previous image: ${env.FREE_PREVIOUS_IMAGE_URI}"
                    echo "Paid previous image: ${env.PAID_PREVIOUS_IMAGE_URI}"
                    echo "Free previous desired count: ${env.FREE_PREVIOUS_DESIRED_COUNT}"
                    echo "Paid previous desired count: ${env.PAID_PREVIOUS_DESIRED_COUNT}"
                    env.PREVIOUS_IMAGES_MATCH = env.FREE_PREVIOUS_IMAGE_URI == env.PAID_PREVIOUS_IMAGE_URI ? 'true' : 'false'
                    echo "Free/Paid previous images match: ${env.PREVIOUS_IMAGES_MATCH}"
                    if (env.PREVIOUS_IMAGES_MATCH != 'true') {
                        echo 'Warning: Free/Paid rollback baselines use different images. Each service will still be restored to its own captured baseline.'
                    }
                }

                script {
                    echo '[Free] Register Task Definition'
                    env.FREE_TASK_DEFINITION_ARN = sh(
                        script: '''
                            set -eu
                            aws sts get-caller-identity --query Account --output text >/dev/null
                            aws ecs describe-services \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --services "${FREE_ECS_SERVICE_NAME}" \
                              --query 'services[0].serviceName' \
                              --output text >/dev/null
                            aws ecs describe-task-definition \
                              --region "${AWS_REGION}" \
                              --task-definition "${FREE_ECS_TASK_FAMILY}" \
                              --query taskDefinition \
                              --output json > free-task-definition-current.json

                            TASK_DEFINITION_FILE="free-task-definition-current.json" \
                            OUTPUT_FILE="free-task-definition-new.json" \
                            CONTAINER_NAME="${FREE_CONTAINER_NAME}" \
                            python3 - <<'PY'
import json
import os

with open(os.environ["TASK_DEFINITION_FILE"], "r", encoding="utf-8") as f:
    current = json.load(f)

for container in current.get("containerDefinitions", []):
    if container.get("name") == os.environ["CONTAINER_NAME"]:
        container["image"] = os.environ["IMAGE_URI"]
        break
else:
    raise SystemExit(f'container not found: {os.environ["CONTAINER_NAME"]}')

allowed = [
    "family", "taskRoleArn", "executionRoleArn", "networkMode",
    "containerDefinitions", "volumes", "placementConstraints",
    "requiresCompatibilities", "cpu", "memory", "runtimePlatform",
    "ipcMode", "pidMode", "proxyConfiguration", "inferenceAccelerators",
    "ephemeralStorage",
]
next_def = {key: current[key] for key in allowed if current.get(key) is not None}

with open(os.environ["OUTPUT_FILE"], "w", encoding="utf-8") as f:
    json.dump(next_def, f, indent=2)
PY

                            aws ecs register-task-definition \
                              --region "${AWS_REGION}" \
                              --cli-input-json file://free-task-definition-new.json \
                              --query 'taskDefinition.taskDefinitionArn' \
                              --output text
                        ''',
                        returnStdout: true
                    ).trim()
                    echo "Registered Free Worker task definition: ${env.FREE_TASK_DEFINITION_ARN}"

                    env.DEPLOY_PHASE = 'FREE_SERVICE_UPDATE'
                    echo '[Free] Service Update'
                    sh '''
                        set -eu
                        CIRCUIT_BREAKER="$(aws ecs describe-services \
                          --region "${AWS_REGION}" \
                          --cluster "${ECS_CLUSTER_NAME}" \
                          --services "${FREE_ECS_SERVICE_NAME}" \
                          --query 'services[0].deploymentConfiguration.deploymentCircuitBreaker.[enable,rollback]' \
                          --output text)"

                        if ! printf '%s\n' "${CIRCUIT_BREAKER}" | awk '$1 == "True" && $2 == "True" { enabled = 1 } END { exit !enabled }'; then
                          echo "Free Worker deployment circuit breaker with rollback must be enabled before deployment: ${CIRCUIT_BREAKER}"
                          exit 1
                        fi
                    '''

                    env.FREE_UPDATE_REQUESTED = 'true'
                    sh '''
                        set -eu
                        aws ecs update-service \
                          --region "${AWS_REGION}" \
                          --cluster "${ECS_CLUSTER_NAME}" \
                          --service "${FREE_ECS_SERVICE_NAME}" \
                          --task-definition "${FREE_TASK_DEFINITION_ARN}" \
                          --no-cli-pager >/dev/null
                        echo "[Free] service update requested using ${IMAGE_URI}"
                    '''

                    env.DEPLOY_PHASE = 'FREE_SERVICE_STABILIZATION_FAILED'
                    echo '[Free] Targeted Stable Check'
                    sh '''
                        set -eu

                        wait_for_worker_revision_running() {
                          LABEL="$1"
                          SERVICE_NAME="$2"
                          EXPECTED_REVISION="$3"
                          OBSERVATION_SECONDS="${4:-15}"
                          MAX_ATTEMPTS="${5:-36}"
                          SLEEP_SECONDS="${6:-5}"
                          MATCHING_TASK_ARNS=""

                          attempt=1
                          while [ "${attempt}" -le "${MAX_ATTEMPTS}" ]; do
                            SERVICE_JSON="$(aws ecs describe-services \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --services "${SERVICE_NAME}" \
                              --query 'services[0].{TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' \
                              --output json)"
                            CURRENT_REVISION="$(printf '%s' "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("TaskDefinition", ""))')"
                            DESIRED_COUNT="$(printf '%s' "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Desired", 0))')"
                            RUNNING_COUNT="$(printf '%s' "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Running", 0))')"
                            PENDING_COUNT="$(printf '%s' "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Pending", 0))')"

                            if ! printf '%s' "${DESIRED_COUNT}" | grep -Eq '^[0-9]+$'; then
                              echo "[${LABEL}] invalid desired count: ${DESIRED_COUNT}"
                              exit 1
                            fi
                            if [ "${DESIRED_COUNT}" -lt 1 ]; then
                              echo "[${LABEL}] desired count is 0. Worker RUNNING verification requires at least one task."
                              exit 1
                            fi

                            TASK_ARNS="$(aws ecs list-tasks \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --service-name "${SERVICE_NAME}" \
                              --desired-status RUNNING \
                              --query 'taskArns' \
                              --output text)"
                            MATCHING_TASK_ARNS=""
                            MATCHING_COUNT="0"
                            if [ -n "${TASK_ARNS}" ] && [ "${TASK_ARNS}" != "None" ]; then
                              MATCHING_TASK_ARNS="$(aws ecs describe-tasks \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --tasks ${TASK_ARNS} \
                                --query "tasks[?taskDefinitionArn=='${EXPECTED_REVISION}'].taskArn" \
                                --output text)"
                              if [ -n "${MATCHING_TASK_ARNS}" ] && [ "${MATCHING_TASK_ARNS}" != "None" ]; then
                                MATCHING_COUNT="$(printf '%s\n' ${MATCHING_TASK_ARNS} | wc -w | tr -d ' ')"
                              fi
                            fi

                            echo "[${LABEL}] poll ${attempt}/${MAX_ATTEMPTS}: serviceRevision=${CURRENT_REVISION}, desired=${DESIRED_COUNT}, running=${RUNNING_COUNT}, pending=${PENDING_COUNT}, matchingRevisionTasks=${MATCHING_COUNT}"

                            if [ "${CURRENT_REVISION}" = "${EXPECTED_REVISION}" ] && [ "${MATCHING_COUNT}" -ge "${DESIRED_COUNT}" ]; then
                              echo "[${LABEL}] requested revision has ${MATCHING_COUNT}/${DESIRED_COUNT} RUNNING task(s)."
                              echo "[${LABEL}] observing RUNNING tasks for ${OBSERVATION_SECONDS}s."
                              sleep "${OBSERVATION_SECONDS}"

                              FINAL_REVISION="$(aws ecs describe-services \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" \
                                --query 'services[0].taskDefinition' \
                                --output text)"
                              if [ "${FINAL_REVISION}" != "${EXPECTED_REVISION}" ]; then
                                echo "[${LABEL}] service revision changed during observation: ${FINAL_REVISION}"
                                exit 1
                              fi

                              NON_RUNNING_TASKS="$(aws ecs describe-tasks \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --tasks ${MATCHING_TASK_ARNS} \
                                --query "tasks[?lastStatus!='RUNNING'].taskArn" \
                                --output text)"
                              if [ -n "${NON_RUNNING_TASKS}" ] && [ "${NON_RUNNING_TASKS}" != "None" ]; then
                                echo "[${LABEL}] requested revision tasks did not remain RUNNING: ${NON_RUNNING_TASKS}"
                                exit 1
                              fi

                              echo "[${LABEL}] targeted stable check passed."
                              return 0
                            fi

                            attempt=$((attempt + 1))
                            sleep "${SLEEP_SECONDS}"
                          done

                          echo "[${LABEL}] targeted stable check timed out."
                          aws ecs describe-services \
                            --region "${AWS_REGION}" \
                            --cluster "${ECS_CLUSTER_NAME}" \
                            --services "${SERVICE_NAME}" \
                            --query 'services[0].deployments[].{Status:status,RolloutState:rolloutState,TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount,Failed:failedTasks}' \
                            --output table || true
                          aws ecs describe-services \
                            --region "${AWS_REGION}" \
                            --cluster "${ECS_CLUSTER_NAME}" \
                            --services "${SERVICE_NAME}" \
                            --query 'services[0].events[0:10].[createdAt,message]' \
                            --output table || true
                          exit 1
                        }

                        wait_for_worker_revision_running "Free" "${FREE_ECS_SERVICE_NAME}" "${FREE_TASK_DEFINITION_ARN}" 15
                    '''

                    env.DEPLOY_PHASE = 'FREE_POST_DEPLOY_VERIFICATION_FAILED'
                    echo '[Free] Revision Verification'
                    sh '''
                        set -eu
                        FINAL_FREE_TASK_DEFINITION_ARN="$(aws ecs describe-services \
                          --region "${AWS_REGION}" \
                          --cluster "${ECS_CLUSTER_NAME}" \
                          --services "${FREE_ECS_SERVICE_NAME}" \
                          --query 'services[0].taskDefinition' \
                          --output text)"
                        echo "Requested Free Worker task definition: ${FREE_TASK_DEFINITION_ARN}"
                        echo "Final Free Worker task definition: ${FINAL_FREE_TASK_DEFINITION_ARN}"
                        if [ "${FINAL_FREE_TASK_DEFINITION_ARN}" != "${FREE_TASK_DEFINITION_ARN}" ]; then
                          echo "Free Worker service revision changed before post-deploy verification completed."
                          exit 1
                        fi
                        if [ "${ROLLBACK_TEST_MODE:-NONE}" = "FREE_VERIFY_FAIL" ]; then
                          echo "Intentional Free Worker verification failure for rollback test."
                          exit 1
                        fi
                        STOPPED_TASK_ARNS="$(aws ecs list-tasks \
                          --region "${AWS_REGION}" \
                          --cluster "${ECS_CLUSTER_NAME}" \
                          --service-name "${FREE_ECS_SERVICE_NAME}" \
                          --desired-status STOPPED \
                          --max-results 5 \
                          --query 'taskArns' \
                          --output text)"
                        if [ -n "${STOPPED_TASK_ARNS}" ] && [ "${STOPPED_TASK_ARNS}" != "None" ]; then
                          aws ecs describe-tasks \
                            --region "${AWS_REGION}" \
                            --cluster "${ECS_CLUSTER_NAME}" \
                            --tasks ${STOPPED_TASK_ARNS} \
                            --query 'tasks[].[taskArn,stopCode,stoppedReason]' \
                            --output table || true
                        fi
                        echo "[Free] Verification Passed for ${FREE_TASK_DEFINITION_ARN}"
                    '''
                }

                script {
                    echo '[Paid] Register Task Definition'
                    env.DEPLOY_PHASE = 'PAID_DEPLOY_PRE_UPDATE_FAILED'
                    env.PAID_TASK_DEFINITION_ARN = sh(
                        script: '''
                            set -eu
                            aws ecs describe-services \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --services "${PAID_ECS_SERVICE_NAME}" \
                              --query 'services[0].serviceName' \
                              --output text >/dev/null
                            aws ecs describe-task-definition \
                              --region "${AWS_REGION}" \
                              --task-definition "${PAID_ECS_TASK_FAMILY}" \
                              --query taskDefinition \
                              --output json > paid-task-definition-current.json

                            TASK_DEFINITION_FILE="paid-task-definition-current.json" \
                            OUTPUT_FILE="paid-task-definition-new.json" \
                            CONTAINER_NAME="${PAID_CONTAINER_NAME}" \
                            python3 - <<'PY'
import json
import os

with open(os.environ["TASK_DEFINITION_FILE"], "r", encoding="utf-8") as f:
    current = json.load(f)

for container in current.get("containerDefinitions", []):
    if container.get("name") == os.environ["CONTAINER_NAME"]:
        container["image"] = os.environ["IMAGE_URI"]
        break
else:
    raise SystemExit(f'container not found: {os.environ["CONTAINER_NAME"]}')

allowed = [
    "family", "taskRoleArn", "executionRoleArn", "networkMode",
    "containerDefinitions", "volumes", "placementConstraints",
    "requiresCompatibilities", "cpu", "memory", "runtimePlatform",
    "ipcMode", "pidMode", "proxyConfiguration", "inferenceAccelerators",
    "ephemeralStorage",
]
next_def = {key: current[key] for key in allowed if current.get(key) is not None}

with open(os.environ["OUTPUT_FILE"], "w", encoding="utf-8") as f:
    json.dump(next_def, f, indent=2)
PY

                            aws ecs register-task-definition \
                              --region "${AWS_REGION}" \
                              --cli-input-json file://paid-task-definition-new.json \
                              --query 'taskDefinition.taskDefinitionArn' \
                              --output text
                        ''',
                        returnStdout: true
                    ).trim()
                    echo "Registered Paid Worker task definition: ${env.PAID_TASK_DEFINITION_ARN}"

                    env.DEPLOY_PHASE = 'PAID_SERVICE_UPDATE'
                    echo '[Paid] Service Update'
                    sh '''
                        set -eu
                        CIRCUIT_BREAKER="$(aws ecs describe-services \
                          --region "${AWS_REGION}" \
                          --cluster "${ECS_CLUSTER_NAME}" \
                          --services "${PAID_ECS_SERVICE_NAME}" \
                          --query 'services[0].deploymentConfiguration.deploymentCircuitBreaker.[enable,rollback]' \
                          --output text)"

                        if ! printf '%s\n' "${CIRCUIT_BREAKER}" | awk '$1 == "True" && $2 == "True" { enabled = 1 } END { exit !enabled }'; then
                          echo "Paid Worker deployment circuit breaker with rollback must be enabled before deployment: ${CIRCUIT_BREAKER}"
                          exit 1
                        fi
                    '''

                    env.PAID_UPDATE_REQUESTED = 'true'
                    sh '''
                        set -eu
                        aws ecs update-service \
                          --region "${AWS_REGION}" \
                          --cluster "${ECS_CLUSTER_NAME}" \
                          --service "${PAID_ECS_SERVICE_NAME}" \
                          --task-definition "${PAID_TASK_DEFINITION_ARN}" \
                          --no-cli-pager >/dev/null
                        echo "[Paid] service update requested using ${IMAGE_URI}"
                    '''

                    env.DEPLOY_PHASE = 'PAID_SERVICE_STABILIZATION_FAILED'
                    echo '[Paid] Targeted Stable Check'
                    sh '''
                        set -eu

                        wait_for_worker_revision_running() {
                          LABEL="$1"
                          SERVICE_NAME="$2"
                          EXPECTED_REVISION="$3"
                          OBSERVATION_SECONDS="${4:-15}"
                          MAX_ATTEMPTS="${5:-36}"
                          SLEEP_SECONDS="${6:-5}"
                          MATCHING_TASK_ARNS=""

                          attempt=1
                          while [ "${attempt}" -le "${MAX_ATTEMPTS}" ]; do
                            SERVICE_JSON="$(aws ecs describe-services \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --services "${SERVICE_NAME}" \
                              --query 'services[0].{TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' \
                              --output json)"
                            CURRENT_REVISION="$(printf '%s' "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("TaskDefinition", ""))')"
                            DESIRED_COUNT="$(printf '%s' "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Desired", 0))')"
                            RUNNING_COUNT="$(printf '%s' "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Running", 0))')"
                            PENDING_COUNT="$(printf '%s' "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Pending", 0))')"

                            if ! printf '%s' "${DESIRED_COUNT}" | grep -Eq '^[0-9]+$'; then
                              echo "[${LABEL}] invalid desired count: ${DESIRED_COUNT}"
                              exit 1
                            fi
                            if [ "${DESIRED_COUNT}" -lt 1 ]; then
                              echo "[${LABEL}] desired count is 0. Worker RUNNING verification requires at least one task."
                              exit 1
                            fi

                            TASK_ARNS="$(aws ecs list-tasks \
                              --region "${AWS_REGION}" \
                              --cluster "${ECS_CLUSTER_NAME}" \
                              --service-name "${SERVICE_NAME}" \
                              --desired-status RUNNING \
                              --query 'taskArns' \
                              --output text)"
                            MATCHING_TASK_ARNS=""
                            MATCHING_COUNT="0"
                            if [ -n "${TASK_ARNS}" ] && [ "${TASK_ARNS}" != "None" ]; then
                              MATCHING_TASK_ARNS="$(aws ecs describe-tasks \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --tasks ${TASK_ARNS} \
                                --query "tasks[?taskDefinitionArn=='${EXPECTED_REVISION}'].taskArn" \
                                --output text)"
                              if [ -n "${MATCHING_TASK_ARNS}" ] && [ "${MATCHING_TASK_ARNS}" != "None" ]; then
                                MATCHING_COUNT="$(printf '%s\n' ${MATCHING_TASK_ARNS} | wc -w | tr -d ' ')"
                              fi
                            fi

                            echo "[${LABEL}] poll ${attempt}/${MAX_ATTEMPTS}: serviceRevision=${CURRENT_REVISION}, desired=${DESIRED_COUNT}, running=${RUNNING_COUNT}, pending=${PENDING_COUNT}, matchingRevisionTasks=${MATCHING_COUNT}"

                            if [ "${CURRENT_REVISION}" = "${EXPECTED_REVISION}" ] && [ "${MATCHING_COUNT}" -ge "${DESIRED_COUNT}" ]; then
                              echo "[${LABEL}] requested revision has ${MATCHING_COUNT}/${DESIRED_COUNT} RUNNING task(s)."
                              echo "[${LABEL}] observing RUNNING tasks for ${OBSERVATION_SECONDS}s."
                              sleep "${OBSERVATION_SECONDS}"

                              FINAL_REVISION="$(aws ecs describe-services \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" \
                                --query 'services[0].taskDefinition' \
                                --output text)"
                              if [ "${FINAL_REVISION}" != "${EXPECTED_REVISION}" ]; then
                                echo "[${LABEL}] service revision changed during observation: ${FINAL_REVISION}"
                                exit 1
                              fi

                              NON_RUNNING_TASKS="$(aws ecs describe-tasks \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --tasks ${MATCHING_TASK_ARNS} \
                                --query "tasks[?lastStatus!='RUNNING'].taskArn" \
                                --output text)"
                              if [ -n "${NON_RUNNING_TASKS}" ] && [ "${NON_RUNNING_TASKS}" != "None" ]; then
                                echo "[${LABEL}] requested revision tasks did not remain RUNNING: ${NON_RUNNING_TASKS}"
                                exit 1
                              fi

                              echo "[${LABEL}] targeted stable check passed."
                              return 0
                            fi

                            attempt=$((attempt + 1))
                            sleep "${SLEEP_SECONDS}"
                          done

                          echo "[${LABEL}] targeted stable check timed out."
                          aws ecs describe-services \
                            --region "${AWS_REGION}" \
                            --cluster "${ECS_CLUSTER_NAME}" \
                            --services "${SERVICE_NAME}" \
                            --query 'services[0].deployments[].{Status:status,RolloutState:rolloutState,TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount,Failed:failedTasks}' \
                            --output table || true
                          aws ecs describe-services \
                            --region "${AWS_REGION}" \
                            --cluster "${ECS_CLUSTER_NAME}" \
                            --services "${SERVICE_NAME}" \
                            --query 'services[0].events[0:10].[createdAt,message]' \
                            --output table || true
                          exit 1
                        }

                        wait_for_worker_revision_running "Paid" "${PAID_ECS_SERVICE_NAME}" "${PAID_TASK_DEFINITION_ARN}" 15
                    '''

                    env.DEPLOY_PHASE = 'PAID_POST_DEPLOY_VERIFICATION_FAILED'
                    echo '[Paid] Revision Verification'
                    sh '''
                        set -eu
                        FINAL_PAID_TASK_DEFINITION_ARN="$(aws ecs describe-services \
                          --region "${AWS_REGION}" \
                          --cluster "${ECS_CLUSTER_NAME}" \
                          --services "${PAID_ECS_SERVICE_NAME}" \
                          --query 'services[0].taskDefinition' \
                          --output text)"
                        echo "Requested Paid Worker task definition: ${PAID_TASK_DEFINITION_ARN}"
                        echo "Final Paid Worker task definition: ${FINAL_PAID_TASK_DEFINITION_ARN}"
                        if [ "${FINAL_PAID_TASK_DEFINITION_ARN}" != "${PAID_TASK_DEFINITION_ARN}" ]; then
                          echo "Paid Worker service revision changed before post-deploy verification completed."
                          exit 1
                        fi
                        if [ "${ROLLBACK_TEST_MODE:-NONE}" = "PAID_VERIFY_FAIL" ]; then
                          echo "Intentional Paid Worker verification failure for rollback test."
                          exit 1
                        fi
                        STOPPED_TASK_ARNS="$(aws ecs list-tasks \
                          --region "${AWS_REGION}" \
                          --cluster "${ECS_CLUSTER_NAME}" \
                          --service-name "${PAID_ECS_SERVICE_NAME}" \
                          --desired-status STOPPED \
                          --max-results 5 \
                          --query 'taskArns' \
                          --output text)"
                        if [ -n "${STOPPED_TASK_ARNS}" ] && [ "${STOPPED_TASK_ARNS}" != "None" ]; then
                          aws ecs describe-tasks \
                            --region "${AWS_REGION}" \
                            --cluster "${ECS_CLUSTER_NAME}" \
                            --tasks ${STOPPED_TASK_ARNS} \
                            --query 'tasks[].[taskArn,stopCode,stoppedReason]' \
                            --output table || true
                        fi
                        echo "[Paid] Verification Passed for ${PAID_TASK_DEFINITION_ARN}"
                    '''

                    env.DEPLOY_PHASE = 'DEPLOY_SUCCESS'
                    echo 'Worker Deploy & Verify completed.'
                }
            }
        }

        // 두 Worker Service의 감사와 장애 분석에 필요한 배포 식별 정보를 출력합니다.
        stage('Deployment Summary') {
            steps {
                echo "Repository: ${env.GIT_REPOSITORY_URL}"
                echo "Git commit: ${env.GIT_COMMIT_SHA}"
                echo "Jenkins build: ${env.BUILD_URL}"
                echo "Shared image URI: ${env.IMAGE_URI}"
                echo "Shared image digest: ${env.IMAGE_DIGEST}"
                echo "Free Worker service: ${env.FREE_ECS_SERVICE_NAME}"
                echo "Free Worker task definition: ${env.FREE_TASK_DEFINITION_ARN}"
                echo "Paid Worker service: ${env.PAID_ECS_SERVICE_NAME}"
                echo "Paid Worker task definition: ${env.PAID_TASK_DEFINITION_ARN}"
                echo "Rollback baseline Free revision: ${env.FREE_PREVIOUS_TASK_DEFINITION_ARN}"
                echo "Rollback baseline Free image: ${env.FREE_PREVIOUS_IMAGE_URI}"
                echo "Rollback baseline Free desired count: ${env.FREE_PREVIOUS_DESIRED_COUNT}"
                echo "Rollback baseline Paid revision: ${env.PAID_PREVIOUS_TASK_DEFINITION_ARN}"
                echo "Rollback baseline Paid image: ${env.PAID_PREVIOUS_IMAGE_URI}"
                echo "Rollback baseline Paid desired count: ${env.PAID_PREVIOUS_DESIRED_COUNT}"
                echo "Rollback baseline images match: ${env.PREVIOUS_IMAGES_MATCH}"
            }
        }
    }

    post {
        success {
            echo "Worker image build completed: ${env.IMAGE_URI}"
            echo "Deployment result: DEPLOY_SUCCESS"
            script {
                sendSlackNotification(':white_check_mark: Worker deployment succeeded', [
                    Result                       : 'SUCCESS',
                    Job                          : env.JOB_NAME,
                    Build                        : env.BUILD_NUMBER,
                    Commit                       : env.GIT_COMMIT_SHA ?: env.GIT_SHORT_SHA,
                    'Shared Worker Image URI'    : env.IMAGE_URI,
                    'Shared Worker Image Digest' : env.IMAGE_DIGEST,
                    'Free Worker Service'        : env.FREE_ECS_SERVICE_NAME,
                    'Free Task Definition'       : env.FREE_TASK_DEFINITION_ARN,
                    'Paid Worker Service'        : env.PAID_ECS_SERVICE_NAME,
                    'Paid Task Definition'       : env.PAID_TASK_DEFINITION_ARN,
                    'Jenkins Build URL'          : env.BUILD_URL
                ] + trivySlackDetails('worker'))
            }
        }
        unsuccessful {
            echo "Worker pipeline did not complete successfully. Build: ${env.BUILD_URL}, commit: ${env.GIT_COMMIT_SHA}, image: ${env.IMAGE_URI}"
            script {
                String failureScenario = env.PAID_UPDATE_REQUESTED == 'true' ?
                    'PAID_FAILED; PAID_ROLLBACK_AND_FREE_COMPENSATING_ROLLBACK_REQUIRED' :
                    (env.FREE_UPDATE_REQUESTED == 'true' ?
                        'FREE_FAILED; FREE_ROLLBACK_REQUIRED; PAID_NOT_DEPLOYED' :
                        'FAILED_BEFORE_WORKER_SERVICE_UPDATE')
                sendSlackNotification(':x: Worker deployment failed', [
                    Result                       : 'FAILED',
                    Job                          : env.JOB_NAME,
                    Build                        : env.BUILD_NUMBER,
                    Commit                       : env.GIT_COMMIT_SHA ?: env.GIT_SHORT_SHA,
                    'Deploy Phase'               : env.DEPLOY_PHASE,
                    Scenario                     : failureScenario,
                    'Shared Worker Image URI'    : env.IMAGE_URI,
                    'Free Worker Service'        : env.FREE_ECS_SERVICE_NAME,
                    'Paid Worker Service'        : env.PAID_ECS_SERVICE_NAME,
                    'Free Update Requested'      : env.FREE_UPDATE_REQUESTED,
                    'Paid Update Requested'      : env.PAID_UPDATE_REQUESTED,
                    'Jenkins Build URL'          : env.BUILD_URL,
                    Runbook                      : workerRunbookLink()
                ] + trivySlackDetails('worker'))

                if (env.DEPLOY_PHASE == 'DEPLOY_SUCCESS') {
                    echo "Rollback skipped: Worker deployment verification already succeeded."
                } else if (env.FREE_UPDATE_REQUESTED != 'true' && env.PAID_UPDATE_REQUESTED != 'true') {
                    echo "Rollback skipped: Worker services were not updated by this build."
                } else {
                    int rollbackStatus = sh(
                        returnStatus: true,
                        script: '''
                            set -u

                            print_worker_diagnostics() {
                              SERVICE_NAME="$1"
                              aws ecs describe-services \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" \
                                --query 'services[0].deployments[].{Status:status,RolloutState:rolloutState,Reason:rolloutStateReason,TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount,Failed:failedTasks}' \
                                --output table || true
                              aws ecs describe-services \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" \
                                --query 'services[0].events[0:10].[createdAt,message]' \
                                --output table || true
                              STOPPED_TASK_ARNS="$(aws ecs list-tasks \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --service-name "${SERVICE_NAME}" \
                                --desired-status STOPPED \
                                --max-results 5 \
                                --query 'taskArns' \
                                --output text 2>/dev/null || true)"
                              if [ -n "${STOPPED_TASK_ARNS}" ] && [ "${STOPPED_TASK_ARNS}" != "None" ]; then
                                aws ecs describe-tasks \
                                  --region "${AWS_REGION}" \
                                  --cluster "${ECS_CLUSTER_NAME}" \
                                  --tasks ${STOPPED_TASK_ARNS} \
                                  --query 'tasks[].[taskArn,taskDefinitionArn,stopCode,stoppedReason]' \
                                  --output table || true
                              fi
                            }

                            verify_worker_service() {
                              SERVICE_NAME="$1"
                              EXPECTED_REVISION="$2"
                              DESIRED_COUNT="$(aws ecs describe-services \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" \
                                --query 'services[0].desiredCount' \
                                --output text)" || return 1
                              RUNNING_COUNT="$(aws ecs describe-services \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" \
                                --query 'services[0].runningCount' \
                                --output text)" || return 1
                              case "${DESIRED_COUNT}:${RUNNING_COUNT}" in
                                *[!0-9:]*)
                                  echo "Rollback verification failed: Invalid Desired/Running Count values for ${SERVICE_NAME}: desired=${DESIRED_COUNT}, running=${RUNNING_COUNT}"
                                  return 1
                                  ;;
                              esac
                              if [ "${DESIRED_COUNT}" -eq 0 ]; then
                                echo "Rollback verification incomplete: Desired Count is 0 for ${SERVICE_NAME}."
                                echo "Worker execution-state verification requires at least one RUNNING task."
                                return 3
                              fi
                              if [ "${RUNNING_COUNT}" -ne "${DESIRED_COUNT}" ]; then
                                echo "Rollback verification failed: Running Count (${RUNNING_COUNT}) does not match Desired Count (${DESIRED_COUNT}) for ${SERVICE_NAME}."
                                return 1
                              fi

                              TASK_ARNS="$(aws ecs list-tasks \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --service-name "${SERVICE_NAME}" \
                                --desired-status RUNNING \
                                --query 'taskArns' \
                                --output text)" || return 1
                              if [ -z "${TASK_ARNS}" ] || [ "${TASK_ARNS}" = "None" ]; then
                                echo "Rollback verification failed: No RUNNING tasks found for ${SERVICE_NAME}."
                                return 1
                              fi
                              UNEXPECTED_TASKS="$(aws ecs describe-tasks \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --tasks ${TASK_ARNS} \
                                --query "tasks[?taskDefinitionArn!='${EXPECTED_REVISION}'].taskArn" \
                                --output text)" || return 1
                              if [ -n "${UNEXPECTED_TASKS}" ] && [ "${UNEXPECTED_TASKS}" != "None" ]; then
                                echo "Rollback verification failed: RUNNING tasks use an unexpected revision: ${UNEXPECTED_TASKS}"
                                return 1
                              fi
                              sleep 15
                              NON_RUNNING_TASKS="$(aws ecs describe-tasks \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --tasks ${TASK_ARNS} \
                                --query "tasks[?lastStatus!='RUNNING'].taskArn" \
                                --output text)" || return 1
                              if [ -n "${NON_RUNNING_TASKS}" ] && [ "${NON_RUNNING_TASKS}" != "None" ]; then
                                echo "Rollback verification failed: Tasks did not remain RUNNING: ${NON_RUNNING_TASKS}"
                                return 1
                              fi
                              return 0
                            }

                            rollback_worker_service() {
                              LABEL="$1"
                              SERVICE_NAME="$2"
                              REQUESTED_REVISION="$3"
                              PREVIOUS_REVISION="$4"
                              CURRENT_REVISION="$(aws ecs describe-services \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" \
                                --query 'services[0].taskDefinition' \
                                --output text)" || return 1

                              echo "${LABEL} previous revision: ${PREVIOUS_REVISION}"
                              echo "${LABEL} requested revision: ${REQUESTED_REVISION}"
                              echo "${LABEL} current revision before rollback: ${CURRENT_REVISION}"

                              if [ "${CURRENT_REVISION}" = "${PREVIOUS_REVISION}" ]; then
                                echo "${LABEL} rollback action: PREVIOUS_REVISION_ALREADY_ACTIVE"
                              elif [ "${CURRENT_REVISION}" = "${REQUESTED_REVISION}" ]; then
                                echo "${LABEL} rollback action: JENKINS_EXPLICIT_ROLLBACK"
                                EXPLICIT_ROLLBACK_PERFORMED="true"
                                aws ecs update-service \
                                  --region "${AWS_REGION}" \
                                  --cluster "${ECS_CLUSTER_NAME}" \
                                  --service "${SERVICE_NAME}" \
                                  --task-definition "${PREVIOUS_REVISION}" \
                                  --no-cli-pager >/dev/null || return 1
                              else
                                echo "${LABEL} rollback result: EXTERNAL_UPDATE_DETECTED"
                                echo "Automatic rollback stopped to avoid overwriting another deployment."
                                print_worker_diagnostics "${SERVICE_NAME}"
                                return 2
                              fi

                              aws ecs wait services-stable \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" || return 1
                              FINAL_REVISION="$(aws ecs describe-services \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" \
                                --query 'services[0].taskDefinition' \
                                --output text)" || return 1
                              if [ "${FINAL_REVISION}" != "${PREVIOUS_REVISION}" ]; then
                                echo "${LABEL} rollback result: ROLLBACK_FAILED (unexpected final revision: ${FINAL_REVISION})"
                                return 1
                              fi
                              verify_worker_service "${SERVICE_NAME}" "${PREVIOUS_REVISION}"
                              VERIFY_STATUS=$?
                              if [ "${VERIFY_STATUS}" -eq 3 ]; then
                                echo "${LABEL} rollback result: ROLLBACK_VERIFICATION_INCOMPLETE"
                                return 3
                              fi
                              if [ "${VERIFY_STATUS}" -ne 0 ]; then
                                echo "${LABEL} rollback result: ROLLBACK_FAILED"
                                return 1
                              fi
                              echo "${LABEL} rollback result: PREVIOUS_REVISION_RECOVERY_VERIFIED"
                              return 0
                            }

                            assert_service_unchanged() {
                              LABEL="$1"
                              SERVICE_NAME="$2"
                              EXPECTED_REVISION="$3"
                              CURRENT_REVISION="$(aws ecs describe-services \
                                --region "${AWS_REGION}" \
                                --cluster "${ECS_CLUSTER_NAME}" \
                                --services "${SERVICE_NAME}" \
                                --query 'services[0].taskDefinition' \
                                --output text)" || return 1
                              if [ "${CURRENT_REVISION}" != "${EXPECTED_REVISION}" ]; then
                                echo "${LABEL} result: EXTERNAL_UPDATE_DETECTED (${CURRENT_REVISION})"
                                return 2
                              fi
                              echo "${LABEL} remained unchanged: ${CURRENT_REVISION}"
                            }

                            echo "Rollback trigger: ${DEPLOY_PHASE}"
                            ROLLBACK_VERIFICATION_INCOMPLETE="false"
                            EXPLICIT_ROLLBACK_PERFORMED="false"

                            if [ "${PAID_UPDATE_REQUESTED}" = "true" ]; then
                              rollback_worker_service \
                                "Paid Worker" \
                                "${PAID_ECS_SERVICE_NAME}" \
                                "${PAID_TASK_DEFINITION_ARN}" \
                                "${PAID_PREVIOUS_TASK_DEFINITION_ARN}"
                              STATUS=$?
                              if [ "${STATUS}" -eq 3 ]; then
                                ROLLBACK_VERIFICATION_INCOMPLETE="true"
                              elif [ "${STATUS}" -ne 0 ]; then
                                if [ "${STATUS}" -eq 2 ]; then
                                  echo "Paid Worker rollback result: EXTERNAL_UPDATE_DETECTED"
                                else
                                  echo "Paid Worker rollback result: ROLLBACK_FAILED"
                                fi
                                print_worker_diagnostics "${PAID_ECS_SERVICE_NAME}"
                                exit "${STATUS}"
                              fi

                              rollback_worker_service \
                                "Free Worker compensating rollback" \
                                "${FREE_ECS_SERVICE_NAME}" \
                                "${FREE_TASK_DEFINITION_ARN}" \
                                "${FREE_PREVIOUS_TASK_DEFINITION_ARN}"
                              STATUS=$?
                              if [ "${STATUS}" -eq 3 ]; then
                                ROLLBACK_VERIFICATION_INCOMPLETE="true"
                              elif [ "${STATUS}" -ne 0 ]; then
                                if [ "${STATUS}" -eq 2 ]; then
                                  echo "Free Worker compensating rollback result: EXTERNAL_UPDATE_DETECTED"
                                else
                                  echo "Free Worker compensating rollback result: ROLLBACK_FAILED"
                                fi
                                print_worker_diagnostics "${FREE_ECS_SERVICE_NAME}"
                                exit "${STATUS}"
                              fi

                              if [ "${ROLLBACK_VERIFICATION_INCOMPLETE}" = "true" ]; then
                                echo "Rollback result: ROLLBACK_VERIFICATION_INCOMPLETE"
                                echo "Previous revisions were restored, but Worker RUNNING-state verification could not be completed because Desired Count is 0."
                                exit 3
                              fi
                              if [ "${EXPLICIT_ROLLBACK_PERFORMED}" = "true" ]; then
                                echo "Rollback result: JENKINS_ROLLBACK_SUCCESS"
                              else
                                echo "Rollback result: PREVIOUS_REVISION_RECOVERY_VERIFIED"
                              fi
                            elif [ "${FREE_UPDATE_REQUESTED}" = "true" ]; then
                              rollback_worker_service \
                                "Free Worker" \
                                "${FREE_ECS_SERVICE_NAME}" \
                                "${FREE_TASK_DEFINITION_ARN}" \
                                "${FREE_PREVIOUS_TASK_DEFINITION_ARN}"
                              STATUS=$?
                              if [ "${STATUS}" -eq 3 ]; then
                                ROLLBACK_VERIFICATION_INCOMPLETE="true"
                              elif [ "${STATUS}" -ne 0 ]; then
                                if [ "${STATUS}" -eq 2 ]; then
                                  echo "Free Worker rollback result: EXTERNAL_UPDATE_DETECTED"
                                else
                                  echo "Free Worker rollback result: ROLLBACK_FAILED"
                                fi
                                print_worker_diagnostics "${FREE_ECS_SERVICE_NAME}"
                                exit "${STATUS}"
                              fi

                              assert_service_unchanged \
                                "Paid Worker" \
                                "${PAID_ECS_SERVICE_NAME}" \
                                "${PAID_PREVIOUS_TASK_DEFINITION_ARN}" || exit $?

                              if [ "${ROLLBACK_VERIFICATION_INCOMPLETE}" = "true" ]; then
                                echo "Rollback result: ROLLBACK_VERIFICATION_INCOMPLETE"
                                echo "Free Worker previous revision was restored, but RUNNING-state verification could not be completed because Desired Count is 0."
                                exit 3
                              fi
                              if [ "${EXPLICIT_ROLLBACK_PERFORMED}" = "true" ]; then
                                echo "Rollback result: JENKINS_ROLLBACK_SUCCESS; Paid deployment was not started."
                              else
                                echo "Rollback result: PREVIOUS_REVISION_RECOVERY_VERIFIED; Paid deployment was not started."
                              fi
                            fi
                        '''
                    )
                    if (rollbackStatus == 3) {
                        echo 'Worker rollback result: ROLLBACK_VERIFICATION_INCOMPLETE'
                    } else if (rollbackStatus == 2) {
                        echo 'Worker rollback result: EXTERNAL_UPDATE_DETECTED'
                    } else if (rollbackStatus != 0) {
                        echo "Worker rollback handling did not complete successfully. Exit code: ${rollbackStatus}"
                    }
                    env.WORKER_ROLLBACK_RESULT = rollbackStatus == 0 ? 'RECOVERY_VERIFIED' :
                        (rollbackStatus == 3 ? 'ROLLBACK_VERIFICATION_INCOMPLETE' :
                            (rollbackStatus == 2 ? 'EXTERNAL_UPDATE_DETECTED' : 'ROLLBACK_FAILED'))
                    env.FREE_FINAL_TASK_DEFINITION_ARN = readEcsServiceRevisionSafely(env.FREE_ECS_SERVICE_NAME)
                    env.PAID_FINAL_TASK_DEFINITION_ARN = readEcsServiceRevisionSafely(env.PAID_ECS_SERVICE_NAME)
                    String rollbackScenario = env.PAID_UPDATE_REQUESTED == 'true' ?
                        'PAID_ROLLBACK_AND_FREE_COMPENSATING_ROLLBACK' :
                        'FREE_ROLLBACK; PAID_NOT_DEPLOYED'
                    String freeRollbackResult = env.FREE_FINAL_TASK_DEFINITION_ARN == env.FREE_PREVIOUS_TASK_DEFINITION_ARN ?
                        'BASELINE_RESTORED' :
                        (env.FREE_FINAL_TASK_DEFINITION_ARN == env.FREE_TASK_DEFINITION_ARN ?
                            'REQUESTED_REVISION_STILL_ACTIVE' : 'EXTERNAL_OR_UNEXPECTED_REVISION')
                    String paidRollbackResult = env.PAID_UPDATE_REQUESTED == 'true' ?
                        (env.PAID_FINAL_TASK_DEFINITION_ARN == env.PAID_PREVIOUS_TASK_DEFINITION_ARN ?
                            'BASELINE_RESTORED' :
                            (env.PAID_FINAL_TASK_DEFINITION_ARN == env.PAID_TASK_DEFINITION_ARN ?
                                'REQUESTED_REVISION_STILL_ACTIVE' : 'EXTERNAL_OR_UNEXPECTED_REVISION')) :
                        (env.PAID_FINAL_TASK_DEFINITION_ARN == env.PAID_PREVIOUS_TASK_DEFINITION_ARN ?
                            'NOT_REQUIRED_PAID_NOT_DEPLOYED' : 'UNEXPECTED_REVISION_CHANGE')
                    sendSlackNotification(':warning: Worker rollback result', [
                        Scenario                         : rollbackScenario,
                        'Rollback Result'                : env.WORKER_ROLLBACK_RESULT,
                        'Free Rollback Result'           : freeRollbackResult,
                        'Free Requested Revision'        : env.FREE_TASK_DEFINITION_ARN,
                        'Free Baseline Revision'         : env.FREE_PREVIOUS_TASK_DEFINITION_ARN,
                        'Free Final Revision'            : env.FREE_FINAL_TASK_DEFINITION_ARN,
                        'Free Baseline Restored'         : env.FREE_FINAL_TASK_DEFINITION_ARN == env.FREE_PREVIOUS_TASK_DEFINITION_ARN,
                        'Free Compensating Rollback'     : env.PAID_UPDATE_REQUESTED == 'true',
                        'Paid Rollback Result'           : paidRollbackResult,
                        'Paid Requested Revision'        : env.PAID_TASK_DEFINITION_ARN,
                        'Paid Baseline Revision'         : env.PAID_PREVIOUS_TASK_DEFINITION_ARN,
                        'Paid Final Revision'            : env.PAID_FINAL_TASK_DEFINITION_ARN,
                        'Paid Baseline Restored'         : env.PAID_FINAL_TASK_DEFINITION_ARN == env.PAID_PREVIOUS_TASK_DEFINITION_ARN,
                        'Paid Deployment Started'        : env.PAID_UPDATE_REQUESTED,
                        'Deploy Phase'                   : env.DEPLOY_PHASE,
                        'Jenkins Build URL'              : env.BUILD_URL,
                        Runbook                          : workerRunbookLink()
                    ])
                }
                generateWorkerAiFailureSummary()
            }
        }
        always {
            archiveArtifacts(
                artifacts: "trivy-reports/trivy-worker-${env.BUILD_NUMBER}.json",
                allowEmptyArchive: true,
                fingerprint: true
            )
            // 현재 빌드가 생성한 파일과 이미지만 선택적으로 정리합니다.
            // 다른 Jenkins Job이 같은 Host를 사용할 수 있으므로 전체 Docker prune은 실행하지 않습니다.
            sh '''
                set +e
                rm -f "trivy-reports/trivy-worker-${BUILD_NUMBER}.json"
                rm -rf \
                  .venv \
                  free-task-definition-current.json \
                  free-task-definition-new.json \
                  paid-task-definition-current.json \
                  paid-task-definition-new.json
                if [ -n "${IMAGE_URI:-}" ]; then
                  docker image rm "${IMAGE_URI}" >/dev/null 2>&1 || true
                fi
            '''
        }
        cleanup {
            script {
                env.SUMMARY_BUILD_RESULT = currentBuild.currentResult ?: 'UNKNOWN'
                env.SUMMARY_ROLLBACK_HANDLING_EXECUTED =
                    (env.FREE_UPDATE_REQUESTED == 'true' || env.PAID_UPDATE_REQUESTED == 'true') &&
                    env.DEPLOY_PHASE != 'DEPLOY_SUCCESS' ? 'true' : 'false'
                env.SUMMARY_FREE_COMPENSATING_ROLLBACK_REQUIRED =
                    env.PAID_UPDATE_REQUESTED == 'true' && env.DEPLOY_PHASE != 'DEPLOY_SUCCESS' ? 'true' : 'false'
                env.SUMMARY_FREE_FINAL_REVISION = env.FREE_FINAL_TASK_DEFINITION_ARN ?:
                    (env.DEPLOY_PHASE == 'DEPLOY_SUCCESS' ? env.FREE_TASK_DEFINITION_ARN : 'N/A')
                env.SUMMARY_PAID_FINAL_REVISION = env.PAID_FINAL_TASK_DEFINITION_ARN ?:
                    (env.DEPLOY_PHASE == 'DEPLOY_SUCCESS' ? env.PAID_TASK_DEFINITION_ARN : 'N/A')

                if (env.DEPLOY_PHASE == 'DEPLOY_SUCCESS') {
                    env.SUMMARY_FREE_DEPLOY_RESULT = 'DEPLOY_SUCCESS'
                    env.SUMMARY_PAID_DEPLOY_RESULT = 'DEPLOY_SUCCESS'
                } else {
                    env.SUMMARY_FREE_DEPLOY_RESULT = env.FREE_UPDATE_REQUESTED == 'true' ?
                        (env.SUMMARY_FREE_FINAL_REVISION == env.FREE_PREVIOUS_TASK_DEFINITION_ARN ?
                            'BASELINE_RESTORED' : 'DEPLOY_FAILED') : 'NOT_STARTED'
                    env.SUMMARY_PAID_DEPLOY_RESULT = env.PAID_UPDATE_REQUESTED == 'true' ?
                        (env.SUMMARY_PAID_FINAL_REVISION == env.PAID_PREVIOUS_TASK_DEFINITION_ARN ?
                            'BASELINE_RESTORED' : 'DEPLOY_FAILED') : 'NOT_STARTED'
                }

                int summaryStatus = sh(
                    returnStatus: true,
                    script: '''
                        set +e
                        mkdir -p "${DEPLOYMENT_SUMMARY_DIR}"
                        python3 - <<'PY'
import datetime
import json
import os

def value(name):
    result = os.environ.get(name)
    return result if result else "N/A"

trivy = {
    "status": "TRIVY_SCAN_INCOMPLETE",
    "high_count": "N/A",
    "critical_count": "N/A",
}
trivy_path = f".trivy-result-worker-{value('BUILD_NUMBER')}.json"
try:
    with open(trivy_path, "r", encoding="utf-8") as trivy_file:
        trivy.update(json.load(trivy_file))
except Exception:
    pass
trivy.update({
    "report_path": f"trivy-reports/trivy-worker-{value('BUILD_NUMBER')}.json",
    "gate_enabled": False,
    "gate_policy": "WARNING_ONLY",
    "gate_result": "NOT_APPLIED",
})

ai_failure_summary = {
    "enabled": True,
    "provider": "bedrock",
    "status": "SUMMARY_NOT_CREATED",
    "masked": True,
}
ai_summary_path = f".ai-failure-summary-worker-{value('BUILD_NUMBER')}.json"
try:
    with open(ai_summary_path, "r", encoding="utf-8") as ai_summary_file:
        ai_failure_summary.update(json.load(ai_summary_file))
except Exception:
    pass

summary = {
    "schema_version": "1.0",
    "service_type": "worker",
    "job_name": value("JOB_NAME"),
    "build_number": value("BUILD_NUMBER"),
    "build_result": value("SUMMARY_BUILD_RESULT"),
    "git_commit_sha": value("GIT_COMMIT_SHA"),
    "git_short_sha": value("GIT_SHORT_SHA"),
    "image_tag": value("IMAGE_TAG"),
    "image_uri": value("IMAGE_URI"),
    "image_digest": value("IMAGE_DIGEST"),
    "ecs_cluster": value("ECS_CLUSTER_NAME"),
    "deploy_phase": value("DEPLOY_PHASE"),
    "free_worker": {
        "service": value("FREE_ECS_SERVICE_NAME"),
        "task_definition_family": value("FREE_ECS_TASK_FAMILY"),
        "baseline_revision": value("FREE_PREVIOUS_TASK_DEFINITION_ARN"),
        "requested_revision": value("FREE_TASK_DEFINITION_ARN"),
        "final_revision": value("SUMMARY_FREE_FINAL_REVISION"),
        "update_requested": value("FREE_UPDATE_REQUESTED"),
        "deploy_result": value("SUMMARY_FREE_DEPLOY_RESULT"),
    },
    "paid_worker": {
        "service": value("PAID_ECS_SERVICE_NAME"),
        "task_definition_family": value("PAID_ECS_TASK_FAMILY"),
        "baseline_revision": value("PAID_PREVIOUS_TASK_DEFINITION_ARN"),
        "requested_revision": value("PAID_TASK_DEFINITION_ARN"),
        "final_revision": value("SUMMARY_PAID_FINAL_REVISION"),
        "update_requested": value("PAID_UPDATE_REQUESTED"),
        "deploy_result": value("SUMMARY_PAID_DEPLOY_RESULT"),
    },
    "rollback": {
        "handling_executed": value("SUMMARY_ROLLBACK_HANDLING_EXECUTED"),
        "result": value("WORKER_ROLLBACK_RESULT"),
        "free_compensating_rollback_required": value("SUMMARY_FREE_COMPENSATING_ROLLBACK_REQUIRED"),
    },
    "trivy": {
        "mode": "WARNING",
        **trivy,
    },
    "ai_failure_summary": ai_failure_summary,
    "ecr_push_executed": value("IMAGE_DIGEST") != "N/A",
    "ecs_deploy_executed": value("FREE_UPDATE_REQUESTED") == "true" or value("PAID_UPDATE_REQUESTED") == "true",
    "build_url": value("BUILD_URL"),
    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}

summary_path = (
    f"{value('DEPLOYMENT_SUMMARY_DIR')}/"
    f"deployment-summary-worker-{value('BUILD_NUMBER')}.json"
)
with open(summary_path, "w", encoding="utf-8") as summary_file:
    json.dump(summary, summary_file, indent=2)
PY
                    '''
                )
                if (summaryStatus != 0) {
                    echo "WARNING: Worker deployment summary generation failed. Existing build result is unchanged."
                } else {
                    try {
                        archiveArtifacts(
                            artifacts: "deployment-summaries/deployment-summary-worker-${env.BUILD_NUMBER}.json",
                            fingerprint: true
                        )
                    } catch (Exception ignored) {
                        echo "WARNING: Worker deployment summary archive failed. Existing build result is unchanged."
                    }
                }
                sh(
                    returnStatus: true,
                    script: '''
                        rm -f \
                          "deployment-summaries/deployment-summary-worker-${BUILD_NUMBER}.json" \
                          ".trivy-result-worker-${BUILD_NUMBER}.json" \
                          ".ai-failure-summary-worker-${BUILD_NUMBER}.json"
                    '''
                )
            }
        }
    }
}
