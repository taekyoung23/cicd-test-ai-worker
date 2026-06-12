import importlib
import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_worker_healthcheck_script() -> None:
    env = os.environ.copy()
    env["APP_ENV"] = "ci"
    env["WORKER_MODE"] = "mock"

    result = subprocess.run(
        [sys.executable, "healthcheck.py"],
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    assert "healthcheck ok" in result.stdout


def test_config_imports_in_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.setenv("WORKER_MODE", "mock")

    import config

    config = importlib.reload(config)

    assert config.APP_ENV == "ci"
    assert config.WORKER_MODE == "mock"
    assert config.is_mock_mode()
