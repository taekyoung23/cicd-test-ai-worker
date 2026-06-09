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

        // Free Worker가 안정 상태에 도달하지 못하면 Pipeline을 중단합니다.
        stage('Free Worker Stable Wait') {
            options {
                // ECS 안정화를 무기한 기다리지 않고 제한 시간을 초과하면 실패 처리합니다.
                timeout(time: 15, unit: 'MINUTES')
            }
            steps {
                sh '''
                    set -eu
                    aws ecs wait services-stable \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${FREE_ECS_SERVICE_NAME}"
                    aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${FREE_ECS_SERVICE_NAME}" \
                      --query 'services[0].events[0:5].[createdAt,message]' \
                      --output table
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
                sh '''
                    set -eu

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

        // Free Worker 성공 후 Paid Worker가 안정화되지 않으면 Pipeline을 실패 처리합니다.
        // TODO: Free와 Paid가 항상 동일 Revision이어야 한다면 Rollback 정책을 추가합니다.
        stage('Paid Worker Stable Wait') {
            options {
                // Free Worker 성공 후 Paid Worker 배포도 제한 시간 안에 안정화되어야 합니다.
                timeout(time: 15, unit: 'MINUTES')
            }
            steps {
                sh '''
                    set -eu
                    aws ecs wait services-stable \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${PAID_ECS_SERVICE_NAME}"
                    aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${PAID_ECS_SERVICE_NAME}" \
                      --query 'services[0].events[0:5].[createdAt,message]' \
                      --output table
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
                sh '''
                    set -eu

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
            }
        }
    }

    post {
        success {
            echo "Worker image build completed: ${env.IMAGE_URI}"
        }
        failure {
            echo "Worker pipeline failed. Build: ${env.BUILD_URL}, commit: ${env.GIT_COMMIT_SHA}, image: ${env.IMAGE_URI}"
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
