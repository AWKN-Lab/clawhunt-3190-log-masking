"""日志格式与 Filter 行为测试：字段表、单行 JSON、序列化前脱敏。"""

from __future__ import annotations

import io
import json

import pytest

from app.core.logging import configure_logging, get_logger, mask_record
from app.core.masking import REDACTED

FIELDS = (
    "ts",
    "level",
    "logger",
    "msg",
    "request_id",
    "org_id",
    "site_id",
    "user_id",
    "route",
    "status",
    "duration_ms",
    "env",
)


@pytest.fixture()
def log_stream() -> io.StringIO:
    stream = io.StringIO()
    configure_logging(level="INFO", env="test", stream=stream)
    yield stream
    configure_logging(level="INFO", env="test", stream=io.StringIO())


def _read_lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_output_is_single_line_json_with_all_fields(log_stream: io.StringIO) -> None:
    get_logger("unit").info("hello")
    lines = log_stream.getvalue().splitlines()

    assert len(lines) == 1
    record = json.loads(lines[0])
    for field in FIELDS:
        assert field in record, field
    assert record["level"] == "INFO"
    assert record["logger"] == "unit"
    assert record["msg"] == "hello"
    assert record["env"] == "test"
    assert record["ts"].endswith("Z") and "T" in record["ts"]


def test_request_fields_from_extra(log_stream: io.StringIO) -> None:
    get_logger("unit").info(
        "GET /api/users",
        extra={
            "request_id": "req-1",
            "org_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "site_id": "f47ac10b-58cc-4372-a567-0e02b2c3d480",
            "user_id": "f47ac10b-58cc-4372-a567-0e02b2c3d481",
            "route": "/api/users",
            "status": 200,
            "duration_ms": 1.5,
        },
    )
    record = _read_lines(log_stream)[0]
    assert record["request_id"] == "req-1"
    assert record["route"] == "/api/users"
    assert record["status"] == 200
    assert record["duration_ms"] == 1.5


def test_msg_and_args_masked_before_serialization(log_stream: io.StringIO) -> None:
    get_logger("unit").info("用户手机 %s 登录", "13800138000")
    record = _read_lines(log_stream)[0]
    assert record["msg"] == "用户手机 138****8000 登录"
    assert "13800138000" not in log_stream.getvalue()


def test_extra_payload_masked(log_stream: io.StringIO) -> None:
    get_logger("unit").info(
        "login",
        extra={"payload": {"password": "p", "user": {"phone": "13800138000"}}},
    )
    record = _read_lines(log_stream)[0]
    assert record["payload"] == {"password": REDACTED, "user": {"phone": "138****8000"}}


def test_stdout_json_is_not_pretty_printed(log_stream: io.StringIO) -> None:
    get_logger("unit").info("a", extra={"nested": {"b": 1}})
    raw = log_stream.getvalue()
    assert raw.count("\n") == 1
    assert "\n " not in raw


def test_mask_record_helper_matches_filter() -> None:
    payload = {
        "password": "x",
        "nested": [{"phone": "13800138000"}],
    }
    masked = mask_record(payload)
    assert masked["password"] == REDACTED
    assert masked["nested"][0]["phone"] == "138****8000"
