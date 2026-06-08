pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
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
        // Checkout the webhook-triggering commit and initialize pinned fairseq sources.
        stage('Source Checkout') {
            steps {
                checkout scm
                sh 'git submodule update --init --recursive'
                script {
                    env.GIT_SHORT_SHA = sh(
                        script: 'git rev-parse --short=7 HEAD',
                        returnStdout: true
                    ).trim()
                    env.IMAGE_TAG = "build-${env.BUILD_NUMBER}-${env.GIT_SHORT_SHA}"
                }
                echo "Image tag: ${env.IMAGE_TAG}"
            }
        }

        // Validate Worker imports and run repository tests without collecting fairseq tests.
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

        // Build one Worker image that will be shared by Free and Paid services.
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

        // Verify the built image can run health checks and import Worker modules.
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

        // Authenticate Docker to ECR before publishing the shared Worker image.
        stage('ECR Login') {
            steps {
                sh '''
                    set -eu
                    aws ecr get-login-password --region "${AWS_REGION}" \
                      | docker login --username AWS --password-stdin "${ECR_REGISTRY}"
                '''
            }
        }

        // Push the shared image once; both Worker services deploy this exact IMAGE_URI.
        stage('ECR Push') {
            steps {
                sh '''
                    set -eu
                    docker push "${IMAGE_URI}"
                '''
            }
        }

        // Register and deploy the shared image to Free Worker first.
        stage('Free Worker Deploy') {
            steps {
                script {
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

        // Stop the pipeline if Free Worker does not reach steady state.
        stage('Free Worker Stable Wait') {
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

        // Deploy the same IMAGE_URI to Paid Worker only after Free Worker succeeds.
        stage('Paid Worker Deploy') {
            steps {
                script {
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

        // Fail the pipeline if Paid Worker cannot stabilize after Free succeeds.
        // TODO: add a rollback policy if Free and Paid must always run the same revision.
        stage('Paid Worker Stable Wait') {
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
    }

    post {
        success {
            echo "Worker image build completed: ${env.IMAGE_URI}"
        }
        failure {
            echo 'Worker build pipeline failed. Check Jenkins console output for the failing stage.'
        }
        always {
            sh '''
                set +e
                rm -rf .venv
            '''
        }
    }
}
