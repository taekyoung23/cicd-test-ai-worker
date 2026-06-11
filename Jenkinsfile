pipeline {
    agent any

    options {
        // 장애 분석을 위해 로그에 시간을 기록하고, 동일 Job의 배포가 동시에 실행되지 않도록 합니다.
        timestamps()
        disableConcurrentBuilds()
        // Jenkins 저장공간이 계속 증가하지 않도록 최근 빌드 이력 20개만 보관합니다.
        buildDiscarder(logRotator(numToKeepStr: '20'))
        // Free와 Paid Worker를 순차 배포하므로 전체 Pipeline 제한 시간을 길게 설정합니다.
        timeout(time: 45, unit: 'MINUTES')
    }

    parameters {
        choice(
            name: 'ROLLBACK_TEST_MODE',
            choices: ['NONE', 'FREE_VERIFY_FAIL', 'PAID_VERIFY_FAIL'],
            description: 'Worker automatic rollback verification only'
        )
    }

    environment {
        DOCKER_BUILDKIT = '1'
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
                checkout scm
                sh 'git submodule update --init --recursive'
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
                      pip install pytest
                      pytest --ignore=fairseq_src
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

        // 롤백 대상은 단순 이전 번호가 아니라 배포 직전 각 Service가 실제 사용하던 Revision입니다.
        stage('Capture Worker Deployment Baseline') {
            steps {
                script {
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
            }
        }

        // 공통 이미지를 Free Worker에 먼저 등록하고 배포합니다.
        stage('Free Worker Deploy') {
            steps {
                script {
                    // 중복 Revision 생성을 방지하기 위해 Free Worker 등록 명령은 재시도하지 않습니다.
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
                }
                // 안정화 대기 전에 Free Worker Service Update를 한 번만 실행합니다.
                script {
                    env.DEPLOY_PHASE = 'FREE_SERVICE_UPDATE'
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
                        echo "Free Worker service update requested using ${IMAGE_URI}"
                    '''
                }
            }
        }

        // Free Worker가 안정 상태에 도달하지 못하면 Pipeline을 중단합니다.
        stage('Free Worker Stable Wait') {
            options {
                // ECS 안정화를 무기한 기다리지 않고 제한 시간을 초과하면 실패 처리합니다.
                timeout(time: 15, unit: 'MINUTES')
            }
            steps {
                script {
                    env.DEPLOY_PHASE = 'FREE_SERVICE_STABILIZATION_FAILED'
                }
                sh '''
                    set -eu
                    WAIT_EXIT=0
                    set +e
                    aws ecs wait services-stable \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${FREE_ECS_SERVICE_NAME}" || WAIT_EXIT=$?
                    set -e

                    aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${FREE_ECS_SERVICE_NAME}" \
                      --query 'services[0].deployments[].{Status:status,RolloutState:rolloutState,TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount,Failed:failedTasks}' \
                      --output table

                    aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${FREE_ECS_SERVICE_NAME}" \
                      --query 'services[0].events[0:10].[createdAt,message]' \
                      --output table

                    FINAL_FREE_TASK_DEFINITION_ARN="$(aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${FREE_ECS_SERVICE_NAME}" \
                      --query 'services[0].taskDefinition' \
                      --output text)"

                    echo "Requested Free Worker task definition: ${FREE_TASK_DEFINITION_ARN}"
                    echo "Final Free Worker task definition: ${FINAL_FREE_TASK_DEFINITION_ARN}"

                    if [ "${WAIT_EXIT}" -ne 0 ]; then
                      echo "Free Worker did not reach stable state. Paid Worker deployment will not start."
                      exit "${WAIT_EXIT}"
                    fi

                    if [ "${FINAL_FREE_TASK_DEFINITION_ARN}" != "${FREE_TASK_DEFINITION_ARN}" ]; then
                      echo "Requested Free Worker revision is not active. ECS Circuit Breaker rollback or another service update occurred."
                      echo "Paid Worker deployment will not start."
                      exit 1
                    fi

                    echo "Free Worker service is stable: ${FREE_ECS_SERVICE_NAME}"
                '''
            }
        }

        // Free Worker가 예상 Revision으로 실행되고 관찰 시간 동안 RUNNING 상태를 유지하는지 확인합니다.
        stage('Free Worker Post-Deploy Verification') {
            options {
                // 이 검증은 배포 안정성을 확인하며 실제 SQS 메시지 처리 성공까지 검증하지는 않습니다.
                timeout(time: 5, unit: 'MINUTES')
            }
            steps {
                script {
                    env.DEPLOY_PHASE = 'FREE_POST_DEPLOY_VERIFICATION_FAILED'
                }
                sh '''
                    set -eu

                    FINAL_FREE_TASK_DEFINITION_ARN="$(aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${FREE_ECS_SERVICE_NAME}" \
                      --query 'services[0].taskDefinition' \
                      --output text)"

                    if [ "${FINAL_FREE_TASK_DEFINITION_ARN}" != "${FREE_TASK_DEFINITION_ARN}" ]; then
                      echo "Free Worker service revision changed before post-deploy verification completed."
                      echo "Requested task definition: ${FREE_TASK_DEFINITION_ARN}"
                      echo "Final service task definition: ${FINAL_FREE_TASK_DEFINITION_ARN}"
                      exit 1
                    fi

                    if [ "${ROLLBACK_TEST_MODE:-NONE}" = "FREE_VERIFY_FAIL" ]; then
                      echo "Intentional Free Worker verification failure for rollback test."
                      exit 1
                    fi

                    FREE_RUNNING_TASK_ARNS="$(aws ecs list-tasks \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --service-name "${FREE_ECS_SERVICE_NAME}" \
                      --desired-status RUNNING \
                      --query 'taskArns' \
                      --output text)"

                    if [ -z "${FREE_RUNNING_TASK_ARNS}" ] || [ "${FREE_RUNNING_TASK_ARNS}" = "None" ]; then
                      echo "No RUNNING Free Worker tasks found."
                      exit 1
                    fi

                    UNEXPECTED_TASKS="$(aws ecs describe-tasks \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --tasks ${FREE_RUNNING_TASK_ARNS} \
                      --query "tasks[?taskDefinitionArn!='${FREE_TASK_DEFINITION_ARN}'].taskArn" \
                      --output text)"

                    if [ -n "${UNEXPECTED_TASKS}" ] && [ "${UNEXPECTED_TASKS}" != "None" ]; then
                      echo "Free Worker tasks use an unexpected task definition: ${UNEXPECTED_TASKS}"
                      exit 1
                    fi

                    sleep 30

                    # 짧은 Crash Loop를 감지하기 위해 관찰 시간 후 동일 Task ARN 상태를 다시 확인합니다.
                    NON_RUNNING_TASKS="$(aws ecs describe-tasks \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --tasks ${FREE_RUNNING_TASK_ARNS} \
                      --query "tasks[?lastStatus!='RUNNING'].taskArn" \
                      --output text)"

                    if [ -n "${NON_RUNNING_TASKS}" ] && [ "${NON_RUNNING_TASKS}" != "None" ]; then
                      echo "Free Worker tasks did not remain RUNNING: ${NON_RUNNING_TASKS}"
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
                      # 정상 Rolling Update도 이전 Task를 중지하므로 중지 Task 정보는 참고용으로 출력합니다.
                      aws ecs describe-tasks \
                        --region "${AWS_REGION}" \
                        --cluster "${ECS_CLUSTER_NAME}" \
                        --tasks ${STOPPED_TASK_ARNS} \
                        --query 'tasks[].[taskArn,stopCode,stoppedReason]' \
                        --output table || true
                    fi

                    echo "Free Worker post-deploy verification passed for ${FREE_TASK_DEFINITION_ARN}"
                '''
            }
        }

        // Free Worker 배포와 검증이 성공한 후 동일한 IMAGE_URI를 Paid Worker에 배포합니다.
        stage('Paid Worker Deploy') {
            steps {
                script {
                    env.DEPLOY_PHASE = 'PAID_DEPLOY_PRE_UPDATE_FAILED'
                    // Free Worker 배포 후 검증이 통과한 경우에만 Paid Worker Revision을 등록합니다.
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
                }
                // Free와 Paid Worker Service 모두 동일한 IMAGE_URI를 사용합니다.
                script {
                    env.DEPLOY_PHASE = 'PAID_SERVICE_UPDATE'
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
                        echo "Paid Worker service update requested using ${IMAGE_URI}"
                    '''
                }
            }
        }

        // Free Worker 성공 후 Paid Worker가 안정화되지 않으면 Pipeline을 실패 처리합니다.
        stage('Paid Worker Stable Wait') {
            options {
                // Free Worker 성공 후 Paid Worker 배포도 제한 시간 안에 안정화되어야 합니다.
                timeout(time: 15, unit: 'MINUTES')
            }
            steps {
                script {
                    env.DEPLOY_PHASE = 'PAID_SERVICE_STABILIZATION_FAILED'
                }
                sh '''
                    set -eu
                    WAIT_EXIT=0
                    set +e
                    aws ecs wait services-stable \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${PAID_ECS_SERVICE_NAME}" || WAIT_EXIT=$?
                    set -e

                    aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${PAID_ECS_SERVICE_NAME}" \
                      --query 'services[0].deployments[].{Status:status,RolloutState:rolloutState,TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount,Failed:failedTasks}' \
                      --output table

                    aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${PAID_ECS_SERVICE_NAME}" \
                      --query 'services[0].events[0:10].[createdAt,message]' \
                      --output table

                    FINAL_PAID_TASK_DEFINITION_ARN="$(aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${PAID_ECS_SERVICE_NAME}" \
                      --query 'services[0].taskDefinition' \
                      --output text)"

                    echo "Requested Paid Worker task definition: ${PAID_TASK_DEFINITION_ARN}"
                    echo "Final Paid Worker task definition: ${FINAL_PAID_TASK_DEFINITION_ARN}"

                    if [ "${WAIT_EXIT}" -ne 0 ]; then
                      echo "Paid Worker did not reach stable state."
                      exit "${WAIT_EXIT}"
                    fi

                    if [ "${FINAL_PAID_TASK_DEFINITION_ARN}" != "${PAID_TASK_DEFINITION_ARN}" ]; then
                      echo "Requested Paid Worker revision is not active. ECS Circuit Breaker rollback or another service update occurred."
                      aws ecs describe-services \
                        --region "${AWS_REGION}" \
                        --cluster "${ECS_CLUSTER_NAME}" \
                        --services "${FREE_ECS_SERVICE_NAME}" "${PAID_ECS_SERVICE_NAME}" \
                        --query 'services[].{Service:serviceName,TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount}' \
                        --output table
                      echo "Free Worker may already use the new image while Paid Worker was rolled back. Review both services before the next deployment."
                      exit 1
                    fi

                    echo "Paid Worker service is stable: ${PAID_ECS_SERVICE_NAME}"
                '''
            }
        }

        // Paid Worker가 예상 Revision으로 실행되고 관찰 시간 동안 RUNNING 상태를 유지하는지 확인합니다.
        stage('Paid Worker Post-Deploy Verification') {
            options {
                // 이 검증은 배포 안정성을 확인하며 실제 SQS 메시지 처리 성공까지 검증하지는 않습니다.
                timeout(time: 5, unit: 'MINUTES')
            }
            steps {
                script {
                    env.DEPLOY_PHASE = 'PAID_POST_DEPLOY_VERIFICATION_FAILED'
                }
                sh '''
                    set -eu

                    FINAL_PAID_TASK_DEFINITION_ARN="$(aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${PAID_ECS_SERVICE_NAME}" \
                      --query 'services[0].taskDefinition' \
                      --output text)"

                    if [ "${FINAL_PAID_TASK_DEFINITION_ARN}" != "${PAID_TASK_DEFINITION_ARN}" ]; then
                      echo "Paid Worker service revision changed before post-deploy verification completed."
                      echo "Requested task definition: ${PAID_TASK_DEFINITION_ARN}"
                      echo "Final service task definition: ${FINAL_PAID_TASK_DEFINITION_ARN}"
                      exit 1
                    fi

                    if [ "${ROLLBACK_TEST_MODE:-NONE}" = "PAID_VERIFY_FAIL" ]; then
                      echo "Intentional Paid Worker verification failure for rollback test."
                      exit 1
                    fi

                    PAID_RUNNING_TASK_ARNS="$(aws ecs list-tasks \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --service-name "${PAID_ECS_SERVICE_NAME}" \
                      --desired-status RUNNING \
                      --query 'taskArns' \
                      --output text)"

                    if [ -z "${PAID_RUNNING_TASK_ARNS}" ] || [ "${PAID_RUNNING_TASK_ARNS}" = "None" ]; then
                      echo "No RUNNING Paid Worker tasks found."
                      exit 1
                    fi

                    UNEXPECTED_TASKS="$(aws ecs describe-tasks \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --tasks ${PAID_RUNNING_TASK_ARNS} \
                      --query "tasks[?taskDefinitionArn!='${PAID_TASK_DEFINITION_ARN}'].taskArn" \
                      --output text)"

                    if [ -n "${UNEXPECTED_TASKS}" ] && [ "${UNEXPECTED_TASKS}" != "None" ]; then
                      echo "Paid Worker tasks use an unexpected task definition: ${UNEXPECTED_TASKS}"
                      exit 1
                    fi

                    sleep 30

                    # 짧은 Crash Loop를 감지하기 위해 관찰 시간 후 동일 Task ARN 상태를 다시 확인합니다.
                    NON_RUNNING_TASKS="$(aws ecs describe-tasks \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --tasks ${PAID_RUNNING_TASK_ARNS} \
                      --query "tasks[?lastStatus!='RUNNING'].taskArn" \
                      --output text)"

                    if [ -n "${NON_RUNNING_TASKS}" ] && [ "${NON_RUNNING_TASKS}" != "None" ]; then
                      echo "Paid Worker tasks did not remain RUNNING: ${NON_RUNNING_TASKS}"
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
                      # 정상 Rolling Update도 이전 Task를 중지하므로 중지 Task 정보는 참고용으로 출력합니다.
                      aws ecs describe-tasks \
                        --region "${AWS_REGION}" \
                        --cluster "${ECS_CLUSTER_NAME}" \
                        --tasks ${STOPPED_TASK_ARNS} \
                        --query 'tasks[].[taskArn,stopCode,stoppedReason]' \
                        --output table || true
                    fi

                    echo "Paid Worker post-deploy verification passed for ${PAID_TASK_DEFINITION_ARN}"
                '''
                script {
                    env.DEPLOY_PHASE = 'DEPLOY_SUCCESS'
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
        }
        unsuccessful {
            echo "Worker pipeline did not complete successfully. Build: ${env.BUILD_URL}, commit: ${env.GIT_COMMIT_SHA}, image: ${env.IMAGE_URI}"
            script {
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
                              sleep 30
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
                }
            }
        }
        always {
            // 현재 빌드가 생성한 파일과 이미지만 선택적으로 정리합니다.
            // 다른 Jenkins Job이 같은 Host를 사용할 수 있으므로 전체 Docker prune은 실행하지 않습니다.
            sh '''
                set +e
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
    }
}
