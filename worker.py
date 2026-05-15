import json
import traceback
from datetime import datetime, timezone

from config import (
    LOCAL_AUDIO_PATH,
    MODEL_NAME,
    MODEL_PATH,
    TEST_MODE,
    WORKER_MODE,
)
from inference import Nes2NetInference
from model_downloader import prepare_models

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def log(request_id, message):
    print(f"[REQUEST][{request_id}] {message}", flush=True)


def validate_message(message):
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

    if message["user_type"] not in ["guest", "free", "paid"]:
        raise ValueError("user_type must be guest, free, or paid")

    if message["plan"] not in ["free", "paid"]:
        raise ValueError("plan must be free or paid")

    if message["user_type"] == "guest" and message.get("user_id") is not None:
        raise ValueError("guest request must not have user_id")

    if message["user_type"] in ["free", "paid"] and not message.get("user_id"):
        raise ValueError("free/paid request requires user_id")


def process_message(message, inferencer, s3_client=None, db_client=None):
    validate_message(message)

    request_id = message["request_id"]
    user_id = message.get("user_id")
    user_type = message["user_type"]
    plan = message["plan"]

    input_bucket = message["input_bucket"]
    input_key = message["input_key"]
    result_bucket = message["result_bucket"]
    result_key = message["result_key"]

    log(request_id, f"received user_type={user_type}, plan={plan}, user_id={user_id}")
    log(request_id, f"input=s3://{input_bucket}/{input_key}")
    log(request_id, f"result=s3://{result_bucket}/{result_key}")

    try:
        if db_client:
            db_client.update_status(request_id, "PROCESSING")
            log(request_id, "db status=PROCESSING")

        if WORKER_MODE == "aws":
            audio_path = s3_client.download_audio(input_bucket, input_key)
            log(request_id, f"s3 download complete path={audio_path}")
        else:
            audio_path = message.get("local_file_path", LOCAL_AUDIO_PATH)
            log(request_id, f"mock local_file_path={audio_path}")

        result = inferencer.predict(audio_path)
        log(request_id, f"inference complete label={result['label']}, confidence={result['confidence']}")

        output = {
            "request_id": request_id,
            "user_id": user_id,
            "user_type": user_type,
            "plan": plan,
            "status": "SUCCEEDED",
            "input": {
                "bucket": input_bucket,
                "key": input_key,
            },
            "result": result,
            "processed_at": utc_now(),
        }

        if WORKER_MODE == "aws":
            s3_client.upload_json(result_bucket, result_key, output)
            log(request_id, "result json uploaded")

        if db_client:
            db_client.update_success(
                request_id=request_id,
                result=result,
                result_bucket=result_bucket,
                result_key=result_key,
            )
            log(request_id, "db status=SUCCEEDED")

        return output

    except Exception as e:
        log(request_id, f"failed error={str(e)}")

        if db_client:
            db_client.update_status(request_id, "FAILED", str(e))
            log(request_id, "db status=FAILED")

        raise


def build_inferencer():
    print("[WORKER] preparing models", flush=True)
    prepare_models()

    print("[WORKER] loading inference model", flush=True)

    return Nes2NetInference(
        model_path=MODEL_PATH,
        model_name=MODEL_NAME,
        test_mode=TEST_MODE,
    )


def run_mock():
    print("[WORKER] run_mock started", flush=True)

    inferencer = build_inferencer()

    print("[WORKER] inferencer loaded", flush=True)

    mock_message = {
        "request_id": "req-local-001",
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

    inferencer = build_inferencer()
    s3_client = S3Client()
    sqs_client = SQSClient()
    db_client = DBClient()

    print("[WORKER] started aws polling mode", flush=True)

    while True:
        messages = sqs_client.receive_messages(max_number=1, wait_time=20)

        if not messages:
            continue

        for sqs_message in messages:
            receipt_handle = sqs_message["ReceiptHandle"]

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
                print("[WORKER][ERROR]", flush=True)
                print(traceback.format_exc(), flush=True)
                # delete 안 함 → visibility timeout 후 재시도, maxReceiveCount 초과 시 DLQ


if __name__ == "__main__":
    print(f"[WORKER] entrypoint WORKER_MODE={WORKER_MODE}", flush=True)

    if WORKER_MODE == "aws":
        run_aws()
    else:
        run_mock()
