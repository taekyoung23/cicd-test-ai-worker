import json

import boto3

from config import AWS_REGION, FREE_QUEUE_URL, PAID_QUEUE_URL, WORKER_TIER


class SQSClient:
    def __init__(self):
        self.client = boto3.client("sqs", region_name=AWS_REGION)

        if WORKER_TIER == "paid":
            self.queue_url = PAID_QUEUE_URL
        else:
            self.queue_url = FREE_QUEUE_URL

        if not self.queue_url:
            raise ValueError("QUEUE_URL is empty")

    def receive_messages(self, max_number=1, wait_time=20):
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max_number,
            WaitTimeSeconds=wait_time,
            VisibilityTimeout=300
        )

        return response.get("Messages", [])

    def parse_body(self, sqs_message):
        return json.loads(sqs_message["Body"])

    def delete_message(self, receipt_handle):
        self.client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle
        )
