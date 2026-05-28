import pymysql
from pymysql.err import InterfaceError, OperationalError

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


class DBClient:
    def __init__(self):
        if not DB_HOST:
            raise ValueError("DB_HOST is required")
        if not DB_NAME:
            raise ValueError("DB_NAME is required")
        if not DB_USER:
            raise ValueError("DB_USER is required")

        self.conn = None
        self._connect()

    def _connect(self):
        self.conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
        )

    def _ensure_connection(self):
        try:
            if self.conn is None:
                self._connect()
            else:
                self.conn.ping(reconnect=True)
        except Exception:
            self._connect()

    def _execute(self, sql: str, params: tuple):
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                return cur.execute(sql, params)
        except (OperationalError, InterfaceError):
            self._connect()
            with self.conn.cursor() as cur:
                return cur.execute(sql, params)

    def update_status_processing(self, request_id: str):
        sql = """
        UPDATE inference_requests
        SET status='PROCESSING',
            error_message=NULL,
            updated_at=NOW()
        WHERE request_id=%s
        """

        self._execute(sql, (request_id,))

    def update_success_result(self, request_id: str, result: dict, result_bucket: str, result_key: str):
        sql = """
        UPDATE inference_requests
        SET status='SUCCEEDED',
            label=%s,
            confidence=%s,
            fake_prob=%s,
            real_prob=%s,
            model_name=%s,
            model_version=%s,
            inference_time_sec=%s,
            result_bucket=%s,
            result_key=%s,
            error_message=NULL,
            updated_at=NOW(),
            completed_at=NOW()
        WHERE request_id=%s
        """

        self._execute(
            sql,
            (
                result.get("label"),
                result.get("confidence"),
                result.get("fake_prob"),
                result.get("real_prob"),
                result.get("model_name"),
                result.get("model_version"),
                result.get("inference_time_sec"),
                result_bucket,
                result_key,
                request_id,
            ),
        )

    def update_failed_result(self, request_id: str, error_message: str):
        sql = """
        UPDATE inference_requests
        SET status='FAILED',
            error_message=%s,
            updated_at=NOW(),
            completed_at=NOW()
        WHERE request_id=%s
        """

        self._execute(sql, (error_message[:4000], request_id))