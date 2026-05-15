import json
import os
import tempfile

import boto3

from config import AWS_REGION


class S3Client:
    def __init__(self):
        self.client = boto3.client("s3", region_name=AWS_REGION)

    def download_audio(self, bucket, key):
        suffix = os.path.splitext(key)[1] or ".wav"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()

        self.client.download_file(bucket, key, tmp.name)
        return tmp.name

    def upload_json(self, bucket, key, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json"
        )
