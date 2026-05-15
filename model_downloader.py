import os
import boto3

from config import (
    AWS_REGION,
    MODEL_BUCKET,
    MODEL_CHECKPOINT_KEY,
    MODEL_PATH,
    XLSR_MODEL_KEY,
    XLSR_MODEL_PATH,
    WORKER_MODE,
)


def ensure_parent(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def download_if_missing(s3_client, bucket, key, local_path):
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        print(f"[MODEL] exists local_path={local_path}", flush=True)
        return

    ensure_parent(local_path)

    print(f"[MODEL] downloading s3://{bucket}/{key} -> {local_path}", flush=True)
    s3_client.download_file(bucket, key, local_path)
    print(f"[MODEL] downloaded local_path={local_path}", flush=True)


def prepare_models():
    if WORKER_MODE != "aws":
        print("[MODEL] mock mode: skip S3 model download", flush=True)
        return

    if not MODEL_BUCKET:
        raise ValueError("MODEL_BUCKET is required in aws mode")

    if not MODEL_CHECKPOINT_KEY:
        raise ValueError("MODEL_CHECKPOINT_KEY is required in aws mode")

    s3 = boto3.client("s3", region_name=AWS_REGION)

    download_if_missing(
        s3_client=s3,
        bucket=MODEL_BUCKET,
        key=MODEL_CHECKPOINT_KEY,
        local_path=MODEL_PATH,
    )

    if XLSR_MODEL_KEY:
        download_if_missing(
            s3_client=s3,
            bucket=MODEL_BUCKET,
            key=XLSR_MODEL_KEY,
            local_path=XLSR_MODEL_PATH,
        )
