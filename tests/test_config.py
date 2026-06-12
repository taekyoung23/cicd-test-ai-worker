import importlib

import pytest


def reload_config(monkeypatch: pytest.MonkeyPatch, **environment: str):
    keys = {
        "APP_ENV",
        "WORKER_MODE",
        "QUEUE_TYPE",
        "WORKER_TIER",
        "QUEUE_URL",
        "FREE_QUEUE_URL",
        "PAID_QUEUE_URL",
    }
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    import config

    return importlib.reload(config)


@pytest.mark.parametrize(
    ("app_env", "worker_mode", "expected"),
    [
        ("ci", "mock", True),
        ("local", "aws", True),
        ("dev", "aws", True),
        ("test", "aws", True),
        ("ci", "aws", False),
        ("prod", "aws", False),
    ],
)
def test_is_mock_mode(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    worker_mode: str,
    expected: bool,
) -> None:
    config = reload_config(
        monkeypatch,
        APP_ENV=app_env,
        WORKER_MODE=worker_mode,
    )

    assert config.is_mock_mode() is expected


def test_explicit_queue_url_has_highest_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = reload_config(
        monkeypatch,
        QUEUE_TYPE="paid",
        QUEUE_URL="https://sqs.example/explicit",
        FREE_QUEUE_URL="https://sqs.example/free",
        PAID_QUEUE_URL="https://sqs.example/paid",
    )

    assert config.get_queue_url() == "https://sqs.example/explicit"


@pytest.mark.parametrize(
    ("queue_type", "expected_url"),
    [
        ("free", "https://sqs.example/free"),
        ("paid", "https://sqs.example/paid"),
        ("unknown", "https://sqs.example/free"),
    ],
)
def test_queue_type_selects_tier_queue(
    monkeypatch: pytest.MonkeyPatch,
    queue_type: str,
    expected_url: str,
) -> None:
    config = reload_config(
        monkeypatch,
        QUEUE_TYPE=queue_type,
        FREE_QUEUE_URL="https://sqs.example/free",
        PAID_QUEUE_URL="https://sqs.example/paid",
    )

    assert config.get_queue_url() == expected_url


def test_worker_tier_is_used_when_queue_type_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = reload_config(
        monkeypatch,
        WORKER_TIER="paid",
        FREE_QUEUE_URL="https://sqs.example/free",
        PAID_QUEUE_URL="https://sqs.example/paid",
    )

    assert config.QUEUE_TYPE == "paid"
    assert config.get_queue_url() == "https://sqs.example/paid"
