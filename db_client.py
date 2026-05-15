import pymysql

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


class DBClient:
    def __init__(self):
        self.conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor
        )

    def update_status(self, request_id, status, error_message=None):
        sql = """
        UPDATE inference_requests
        SET status=%s,
            error_message=%s,
            updated_at=NOW()
        WHERE request_id=%s
        """

        with self.conn.cursor() as cur:
            cur.execute(sql, (status, error_message, request_id))

    def update_success(self, request_id, result, result_bucket, result_key):
        sql = """
        UPDATE inference_requests
        SET status='SUCCEEDED',
            label=%s,
            confidence=%s,
            fake_prob=%s,
            real_prob=%s,
            result_bucket=%s,
            result_key=%s,
            model_name=%s,
            model_version=%s,
            inference_time_sec=%s,
            updated_at=NOW(),
            completed_at=NOW()
        WHERE request_id=%s
        """

        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    result["label"],
                    result["confidence"],
                    result["fake_prob"],
                    result["real_prob"],
                    result_bucket,
                    result_key,
                    result["model_name"],
                    result["model_version"],
                    result["inference_time_sec"],
                    request_id,
                )
            )
