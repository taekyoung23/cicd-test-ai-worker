import os

from prometheus_client import Gauge, start_http_server

APP_ENV = os.getenv("APP_ENV", "prod")
QUEUE_TYPE = os.getenv("QUEUE_TYPE", "unknown")
MODEL_NAME = os.getenv("MODEL_NAME", "unknown")
MODEL_VERSION = os.getenv("MODEL_VERSION", "unknown")

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"
METRICS_PORT = int(os.getenv("METRICS_PORT", "9100"))

WORKER_INFO = Gauge(
    "securevoice_worker_info",
    "SecureVoice worker info",
    ["env", "queue_type", "model_name", "model_version"],
)


def start_metrics_server_if_enabled() -> None:
    if not METRICS_ENABLED:
        print("[METRICS] disabled", flush=True)
        return

    start_http_server(METRICS_PORT)

    WORKER_INFO.labels(
        env=APP_ENV,
        queue_type=QUEUE_TYPE,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
    ).set(1)

    print(f"[METRICS] server started port={METRICS_PORT}", flush=True)