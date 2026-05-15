import os

AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")

WORKER_MODE = os.getenv("WORKER_MODE", "mock")  # mock | aws
WORKER_TIER = os.getenv("WORKER_TIER", "free")  # free | paid

FREE_QUEUE_URL = os.getenv("FREE_QUEUE_URL", "")
PAID_QUEUE_URL = os.getenv("PAID_QUEUE_URL", "")

MODEL_NAME = os.getenv("MODEL_NAME", "wav2vec2_Nes2Net_X")
MODEL_VERSION = os.getenv("MODEL_VERSION", "v1")
TEST_MODE = os.getenv("TEST_MODE", "4s")

MODEL_DIR = os.getenv("MODEL_DIR", "/models")
MODEL_PATH = os.getenv("MODEL_PATH", f"{MODEL_DIR}/wav2LM_Nes2Net_X.pth")
XLSR_MODEL_PATH = os.getenv("XLSR_MODEL_PATH", "/workspace/xlsr2_300m.pt")

MODEL_BUCKET = os.getenv("MODEL_BUCKET", "")
MODEL_CHECKPOINT_KEY = os.getenv("MODEL_CHECKPOINT_KEY", "")
XLSR_MODEL_KEY = os.getenv("XLSR_MODEL_KEY", "")

LOCAL_AUDIO_PATH = os.getenv("LOCAL_AUDIO_PATH", "./samples/fake_01.wav")

DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
