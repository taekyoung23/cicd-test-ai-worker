pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        string(name: 'AWS_REGION', defaultValue: 'ap-northeast-2', description: 'AWS region for ECR')
        string(name: 'AWS_ACCOUNT_ID', defaultValue: '455535733131', description: 'AWS account ID that owns the ECR repository')
        string(name: 'ECR_REPOSITORY', defaultValue: 'nes2net-ai-worker', description: 'ECR repository name for the Worker image')
        booleanParam(name: 'RUN_PYTEST', defaultValue: true, description: 'Run pytest when tests are present')
        booleanParam(name: 'PUSH_IMAGE', defaultValue: false, description: 'Push the image to ECR after BuildKit build')
        booleanParam(name: 'DEPLOY_TO_ECS', defaultValue: false, description: 'Update ECS worker service with the newly pushed image')
        choice(name: 'WORKER_TARGET', choices: ['free', 'paid'], description: 'Worker service target')
        string(name: 'ECS_CLUSTER_NAME', defaultValue: 'securevoice-dev-cluster', description: 'ECS cluster name')
        string(name: 'ECS_SERVICE_NAME', defaultValue: '', description: 'Override ECS service name. Empty uses WORKER_TARGET default.')
        string(name: 'ECS_TASK_FAMILY', defaultValue: '', description: 'Override ECS task definition family. Empty uses WORKER_TARGET default.')
        string(name: 'CONTAINER_NAME', defaultValue: '', description: 'Override container name. Empty uses WORKER_TARGET default.')
    }

    environment {
        DOCKER_BUILDKIT = '1'
        APP_ENV = 'ci'
        WORKER_MODE = 'mock'
        AWS_REGION = "${params.AWS_REGION}"
        MODEL_DIR = '/models'
        MODEL_PATH = '/models/wav2LM_Nes2Net_X.pth'
        LOCAL_AUDIO_PATH = './samples/fake_01.wav'
    }

    stages {
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
                    if [ "${RUN_PYTEST}" = "true" ]; then
                      if find . -maxdepth 3 -type f \\( -name "test_*.py" -o -name "*_test.py" \\) | grep -q .; then
                        python3 -m venv .venv
                        . .venv/bin/activate
                        python -m pip install --upgrade pip setuptools wheel
                        pip install pytest
                        pytest
                      else
                        echo "No pytest test files found. Skipping pytest."
                      fi
                    fi
                '''
            }
        }

        stage('BuildKit Image Build') {
            steps {
                script {
                    if (!params.AWS_ACCOUNT_ID?.trim()) {
                        error('AWS_ACCOUNT_ID parameter is required to build the ECR image URI.')
                    }
                    env.ECR_REGISTRY = "${params.AWS_ACCOUNT_ID}.dkr.ecr.${params.AWS_REGION}.amazonaws.com"
                    env.IMAGE_URI = "${env.ECR_REGISTRY}/${params.ECR_REPOSITORY}:${env.IMAGE_TAG}"
                }
                sh '''
                    set -eu
                    docker build \
                      --progress=plain \
                      --label securevoice.service=worker \
                      --label securevoice.worker_target="${WORKER_TARGET}" \
                      --label securevoice.git_sha="${GIT_SHORT_SHA}" \
                      --label securevoice.jenkins_build="${BUILD_NUMBER}" \
                      -t "${IMAGE_URI}" \
                      .
                '''
            }
        }

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

        stage('ECR Login') {
            when {
                expression { return params.PUSH_IMAGE }
            }
            steps {
                sh '''
                    set -eu
                    aws ecr get-login-password --region "${AWS_REGION}" \
                      | docker login --username AWS --password-stdin "${ECR_REGISTRY}"
                '''
            }
        }

        stage('ECR Push') {
            when {
                expression { return params.PUSH_IMAGE }
            }
            steps {
                sh '''
                    set -eu
                    docker push "${IMAGE_URI}"
                '''
            }
        }

        stage('Resolve ECS Target') {
            when {
                expression { return params.DEPLOY_TO_ECS }
            }
            steps {
                script {
                    if (!params.PUSH_IMAGE) {
                        error('DEPLOY_TO_ECS=true requires PUSH_IMAGE=true so the target image exists in ECR.')
                    }

                    def defaults = [
                        free: [
                            service: 'securevoice-dev-free-worker-service',
                            family: 'securevoice-dev-free-worker',
                            container: 'free-worker'
                        ],
                        paid: [
                            service: 'securevoice-dev-paid-worker-service',
                            family: 'securevoice-dev-paid-worker',
                            container: 'paid-worker'
                        ]
                    ]

                    def selected = defaults[params.WORKER_TARGET]
                    env.RESOLVED_ECS_SERVICE_NAME = params.ECS_SERVICE_NAME?.trim() ?: selected.service
                    env.RESOLVED_ECS_TASK_FAMILY = params.ECS_TASK_FAMILY?.trim() ?: selected.family
                    env.RESOLVED_CONTAINER_NAME = params.CONTAINER_NAME?.trim() ?: selected.container

                    echo "Resolved worker ECS target: ${params.WORKER_TARGET}"
                    echo "ECS service: ${env.RESOLVED_ECS_SERVICE_NAME}"
                    echo "Task family: ${env.RESOLVED_ECS_TASK_FAMILY}"
                    echo "Container name: ${env.RESOLVED_CONTAINER_NAME}"
                }
            }
        }

        stage('ECS Deploy Dry Check') {
            when {
                expression { return params.DEPLOY_TO_ECS }
            }
            steps {
                sh '''
                    set -eu
                    aws sts get-caller-identity --query Account --output text >/dev/null
                    aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${RESOLVED_ECS_SERVICE_NAME}" \
                      --query 'services[0].serviceName' \
                      --output text
                    aws ecs describe-task-definition \
                      --region "${AWS_REGION}" \
                      --task-definition "${RESOLVED_ECS_TASK_FAMILY}" \
                      --query 'taskDefinition.family' \
                      --output text
                    echo "ECS deploy dry check complete for ${RESOLVED_ECS_SERVICE_NAME} using ${IMAGE_URI}"
                '''
            }
        }

        stage('ECS Task Definition Revision Register') {
            when {
                expression { return params.DEPLOY_TO_ECS }
            }
            steps {
                script {
                    env.NEW_TASK_DEFINITION_ARN = sh(
                        script: '''
                            set -eu
                            aws ecs describe-task-definition \
                              --region "${AWS_REGION}" \
                              --task-definition "${RESOLVED_ECS_TASK_FAMILY}" \
                              --query taskDefinition \
                              --output json > task-definition-current.json

                            CONTAINER_NAME="${RESOLVED_CONTAINER_NAME}" python3 - <<'PY'
import json
import os

image_uri = os.environ["IMAGE_URI"]
container_name = os.environ["CONTAINER_NAME"]

with open("task-definition-current.json", "r", encoding="utf-8") as f:
    current = json.load(f)

found = False
for container in current.get("containerDefinitions", []):
    if container.get("name") == container_name:
        container["image"] = image_uri
        found = True
        break

if not found:
    raise SystemExit(f"container not found in task definition: {container_name}")

allowed = [
    "family",
    "taskRoleArn",
    "executionRoleArn",
    "networkMode",
    "containerDefinitions",
    "volumes",
    "placementConstraints",
    "requiresCompatibilities",
    "cpu",
    "memory",
    "runtimePlatform",
    "ipcMode",
    "pidMode",
    "proxyConfiguration",
    "inferenceAccelerators",
    "ephemeralStorage",
]

next_def = {
    key: current[key]
    for key in allowed
    if key in current and current[key] is not None
}

with open("task-definition-new.json", "w", encoding="utf-8") as f:
    json.dump(next_def, f, indent=2)
PY

                            aws ecs register-task-definition \
                              --region "${AWS_REGION}" \
                              --cli-input-json file://task-definition-new.json \
                              --query 'taskDefinition.taskDefinitionArn' \
                              --output text
                        ''',
                        returnStdout: true
                    ).trim()
                    echo "Registered new task definition revision: ${env.NEW_TASK_DEFINITION_ARN}"
                }
            }
        }

        stage('ECS Service Update') {
            when {
                expression { return params.DEPLOY_TO_ECS }
            }
            steps {
                sh '''
                    set -eu
                    aws ecs update-service \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --service "${RESOLVED_ECS_SERVICE_NAME}" \
                      --task-definition "${NEW_TASK_DEFINITION_ARN}" \
                      --no-cli-pager >/dev/null
                    echo "ECS service update requested: ${RESOLVED_ECS_SERVICE_NAME}"
                '''
            }
        }

        stage('ECS Stable Wait') {
            when {
                expression { return params.DEPLOY_TO_ECS }
            }
            steps {
                sh '''
                    set -eu
                    aws ecs wait services-stable \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${RESOLVED_ECS_SERVICE_NAME}"
                    aws ecs describe-services \
                      --region "${AWS_REGION}" \
                      --cluster "${ECS_CLUSTER_NAME}" \
                      --services "${RESOLVED_ECS_SERVICE_NAME}" \
                      --query 'services[0].events[0:5].[createdAt,message]' \
                      --output table
                    echo "ECS worker service is stable: ${RESOLVED_ECS_SERVICE_NAME}"
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
