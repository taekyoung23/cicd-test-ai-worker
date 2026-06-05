import json

import boto3

from config import AWS_REGION, QUEUE_TYPE, get_queue_url


class SQSClient:
    def __init__(self):
        self.client = boto3.client("sqs", region_name=AWS_REGION)
        self.queue_url = get_queue_url()

        if not self.queue_url:
            raise ValueError("QUEUE_URL is empty. Set QUEUE_URL or FREE_QUEUE_URL/PAID_QUEUE_URL.")

        print(f"[SQS] queue_type={QUEUE_TYPE}", flush=True)
        print(f"[SQS] queue_url={self.queue_url}", flush=True)

    def receive_messages(self, max_number: int = 1, wait_time: int = 20, visibility_timeout: int = 300):
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max_number,
            WaitTimeSeconds=wait_time,
            VisibilityTimeout=visibility_timeout,
        )

        return response.get("Messages", [])

    def parse_body(self, sqs_message: dict) -> dict:
        body = sqs_message.get("Body")
        if not body:
            raise ValueError("SQS message body is empty")

        return json.loads(body)

    def delete_message(self, receipt_handle: str):
        self.client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
        )
