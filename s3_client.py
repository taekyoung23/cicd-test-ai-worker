import json
import os
import tempfile

import boto3

from config import AWS_REGION


class S3Client:
    def __init__(self):
        self.client = boto3.client("s3", region_name=AWS_REGION)

    def download_audio(self, input_bucket: str, input_key: str) -> str:
        suffix = os.path.splitext(input_key)[1] or ".wav"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()

        print(f"[S3] download s3://{input_bucket}/{input_key} -> {tmp.name}", flush=True)
        self.client.download_file(input_bucket, input_key, tmp.name)

        return tmp.name

    def upload_result(self, result_bucket: str, result_key: str, result_json: dict):
        body = json.dumps(result_json, ensure_ascii=False).encode("utf-8")

        print(f"[S3] upload result s3://{result_bucket}/{result_key}", flush=True)
        self.client.put_object(
            Bucket=result_bucket,
            Key=result_key,
            Body=body,
            ContentType="application/json",
        )
