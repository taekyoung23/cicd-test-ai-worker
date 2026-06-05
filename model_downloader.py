import os

import boto3

from config import (
    AWS_REGION,
    MODEL_PATH,
    MODEL_S3_BUCKET,
    MODEL_S3_KEY,
    XLSR_MODEL_PATH,
    XLSR_MODEL_S3_KEY,
    is_mock_mode,
)


def _ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _download_if_missing(s3_client, bucket: str, key: str, local_path: str):
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        print(f"[MODEL] exists local_path={local_path}", flush=True)
        return

    _ensure_parent_dir(local_path)

    print(f"[MODEL] downloading s3://{bucket}/{key} -> {local_path}", flush=True)
    s3_client.download_file(bucket, key, local_path)
    print(f"[MODEL] downloaded local_path={local_path}", flush=True)


def prepare_models():
    if is_mock_mode():
        print("[MODEL] mock mode: skip S3 model download", flush=True)
        return

    if not MODEL_S3_BUCKET:
        raise ValueError("MODEL_S3_BUCKET is required in aws mode")

    if not MODEL_S3_KEY:
        raise ValueError("MODEL_S3_KEY is required in aws mode")

    s3_client = boto3.client("s3", region_name=AWS_REGION)

    _download_if_missing(
        s3_client=s3_client,
        bucket=MODEL_S3_BUCKET,
        key=MODEL_S3_KEY,
        local_path=MODEL_PATH,
    )

    if XLSR_MODEL_S3_KEY:
        _download_if_missing(
            s3_client=s3_client,
            bucket=MODEL_S3_BUCKET,
            key=XLSR_MODEL_S3_KEY,
            local_path=XLSR_MODEL_PATH,
        )
