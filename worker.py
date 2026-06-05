import json
import traceback
from datetime import datetime, timezone
from metrics import start_metrics_server_if_enabled

from config import (
    LOCAL_AUDIO_PATH,
    MODEL_NAME,
    MODEL_PATH,
    QUEUE_TYPE,
    TEST_MODE,
    WORKER_MODE,
    is_mock_mode,
)
from inference import Nes2NetInference
from model_downloader import prepare_models


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def log(request_id: str, message: str):
    print(f"[REQUEST][{request_id}] {message}", flush=True)


def validate_message(message: dict):
    required = [
        "request_id",
        "user_type",
        "plan",
        "input_bucket",
        "input_key",
        "result_bucket",
        "result_key",
    ]

    for key in required:
        if key not in message:
            raise ValueError(f"missing required field: {key}")

    if not message["request_id"]:
        raise ValueError("request_id is required")

    if message["user_type"] not in ["guest", "free", "paid"]:
        raise ValueError("user_type must be guest, free, or paid")

    if message["plan"] not in ["free", "paid"]:
        raise ValueError("plan must be free or paid")

    if message["user_type"] == "guest" and message.get("user_id") is not None:
        raise ValueError("guest request must not have user_id")

    if message["user_type"] in ["free", "paid"] and not message.get("user_id"):
        raise ValueError("free/paid request requires user_id")


def build_inferencer():
    print("[WORKER] preparing models", flush=True)
    prepare_models()

    print("[WORKER] loading inference model", flush=True)
    inferencer = Nes2NetInference(
        model_path=MODEL_PATH,
        model_name=MODEL_NAME,
        test_mode=TEST_MODE,
    )

    print("[WORKER] inferencer loaded", flush=True)
    return inferencer


def process_message(message: dict, inferencer, s3_client=None, db_client=None):
    validate_message(message)

    request_id = message["request_id"]
    user_id = message.get("user_id")
    tenant_id = message.get("tenant_id")
    user_type = message["user_type"]
    plan = message["plan"]

    input_bucket = message["input_bucket"]
    input_key = message["input_key"]
    result_bucket = message["result_bucket"]
    result_key = message["result_key"]

    log(request_id, f"received tenant_id={tenant_id}, user_id={user_id}, user_type={user_type}, plan={plan}")
    log(request_id, f"input=s3://{input_bucket}/{input_key}")
    log(request_id, f"result=s3://{result_bucket}/{result_key}")

    try:
        if db_client:
            db_client.update_status_processing(request_id)
            log(request_id, "db status=PROCESSING")

        if is_mock_mode():
            audio_path = message.get("local_file_path", LOCAL_AUDIO_PATH)
            log(request_id, f"mock local_file_path={audio_path}")
        else:
            if not s3_client:
                raise ValueError("s3_client is required in aws mode")
            audio_path = s3_client.download_audio(input_bucket, input_key)
            log(request_id, f"s3 audio downloaded path={audio_path}")

        result = inferencer.predict(audio_path)
        log(request_id, f"inference complete label={result.get('label')}, confidence={result.get('confidence')}")

        result_json = {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "user_type": user_type,
            "plan": plan,
            "status": "SUCCEEDED",
            "input": {
                "bucket": input_bucket,
                "key": input_key,
            },
            "result_location": {
                "bucket": result_bucket,
                "key": result_key,
            },
            "result": result,
            "processed_at": utc_now(),
        }

        if not is_mock_mode():
            s3_client.upload_result(result_bucket, result_key, result_json)
            log(request_id, "result json uploaded")

        if db_client:
            db_client.update_success_result(
                request_id=request_id,
                result=result,
                result_bucket=result_bucket,
                result_key=result_key,
            )
            log(request_id, "db status=SUCCEEDED")

        return result_json

    except Exception as e:
        error_message = str(e)
        log(request_id, f"failed error={error_message}")

        if db_client:
            db_client.update_failed_result(request_id, error_message)
            log(request_id, "db status=FAILED")

        raise


def run_mock():
    print("[WORKER] run_mock started", flush=True)

    inferencer = build_inferencer()

    mock_message = {
        "request_id": "req-local-001",
        "tenant_id": None,
        "user_id": None,
        "user_type": "guest",
        "plan": "free",
        "input_bucket": "voice-upload-bucket",
        "input_key": "uploads/guest/req-local-001/input.wav",
        "result_bucket": "voice-result-bucket",
        "result_key": "results/guest/req-local-001/result.json",
        "local_file_path": LOCAL_AUDIO_PATH,
        "created_at": utc_now(),
    }

    output = process_message(mock_message, inferencer)
    print(json.dumps(output, indent=2, ensure_ascii=False), flush=True)


def run_aws():
    from db_client import DBClient
    from s3_client import S3Client
    from sqs_client import SQSClient

    print(f"[WORKER] started aws mode queue_type={QUEUE_TYPE}", flush=True)

    inferencer = build_inferencer()
    s3_client = S3Client()
    sqs_client = SQSClient()
    db_client = DBClient()

    while True:
        messages = sqs_client.receive_messages(max_number=1, wait_time=20, visibility_timeout=300)

        if not messages:
            continue

        for sqs_message in messages:
            receipt_handle = sqs_message["ReceiptHandle"]
            request_id = "unknown"

            try:
                body = sqs_client.parse_body(sqs_message)
                request_id = body.get("request_id", "unknown")

                log(request_id, "sqs message received")

                output = process_message(
                    body,
                    inferencer,
                    s3_client=s3_client,
                    db_client=db_client,
                )

                print(json.dumps(output, ensure_ascii=False), flush=True)

                sqs_client.delete_message(receipt_handle)
                log(request_id, "sqs message deleted")

            except Exception:
                print(f"[WORKER][ERROR][{request_id}]", flush=True)
                print(traceback.format_exc(), flush=True)
                # 실패 시 delete_message 호출하지 않음.
                # VisibilityTimeout 이후 재시도되고, maxReceiveCount 초과 시 DLQ 이동은 SQS redrive policy가 담당.


if __name__ == "__main__":
    start_metrics_server_if_enabled()

    print(f"[WORKER] entrypoint WORKER_MODE={WORKER_MODE}", flush=True)

    if is_mock_mode():
        run_mock()
    else:
        run_aws()
