"""请求日志中间件测试：X-Request-ID 回写、字段、白名单与脱敏。"""

from __future__ import annotations

import io
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

ORG_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
SITE_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d480"
USER_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d481"


@pytest.fixture()
def stream() -> io.StringIO:
    return io.StringIO()


def _access_records(stream: io.StringIO) -> list[dict]:
    records = []
    for line in stream.getvalue().splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload["logger"] == "app.access":
            records.append(payload)
    return records


def test_request_id_echoed_from_header(stream: io.StringIO) -> None:
    app = create_app(stream=stream, whitelist=())
    with TestClient(app) as client:
        resp = client.get("/health", headers={"X-Request-ID": "req-abc"})

    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "req-abc"
    record = _access_records(stream)[-1]
    assert record["request_id"] == "req-abc"
    assert record["route"] == "/health"
    assert record["status"] == 200
    assert isinstance(record["duration_ms"], float)


def test_request_id_generated_when_absent(stream: io.StringIO) -> None:
    app = create_app(stream=stream, whitelist=())
    with TestClient(app) as client:
        resp = client.get("/health")

    value = resp.headers["x-request-id"]
    uuid.UUID(value)  # 必须是合法 UUID
    assert _access_records(stream)[-1]["request_id"] == value


def test_identity_headers_logged(stream: io.StringIO) -> None:
    app = create_app(stream=stream, whitelist=())
    with TestClient(app) as client:
        client.get("/health", headers={"X-Org-Id": ORG_ID, "X-Site-Id": SITE_ID, "X-User-Id": USER_ID})

    record = _access_records(stream)[-1]
    assert record["org_id"] == ORG_ID
    assert record["site_id"] == SITE_ID
    assert record["user_id"] == USER_ID


def test_invalid_identity_header_dropped(stream: io.StringIO) -> None:
    app = create_app(stream=stream, whitelist=())
    with TestClient(app) as client:
        client.get("/health", headers={"X-User-Id": "not-a-uuid"})

    assert _access_records(stream)[-1]["user_id"] is None


def test_body_not_logged_by_default(stream: io.StringIO) -> None:
    app = create_app(stream=stream, whitelist=())
    with TestClient(app) as client:
        client.post("/api/echo", json={"password": "p", "phone": "13800138000"})

    record = _access_records(stream)[-1]
    assert "request_body" not in record
    assert "response_body" not in record
    assert "13800138000" not in stream.getvalue()


def test_whitelisted_body_logged_and_masked(stream: io.StringIO) -> None:
    app = create_app(stream=stream, whitelist=("/api/echo",))
    with TestClient(app) as client:
        client.post(
            "/api/echo",
            json={"password": "p", "phone": "13800138000", "nested": {"token": "t"}},
        )

    record = _access_records(stream)[-1]
    body = record["request_body"]
    assert body["password"] == "[REDACTED]"
    assert body["phone"] == "138****8000"
    assert body["nested"]["token"] == "[REDACTED]"
    assert "13800138000" not in stream.getvalue()

    response_body = record["response_body"]
    assert response_body["echo"]["phone"] == "138****8000"


def test_path_prefix_whitelist(stream: io.StringIO) -> None:
    app = create_app(stream=stream, whitelist=("/api/users/*",))
    with TestClient(app) as client:
        client.get("/api/users/13800138000")

    record = _access_records(stream)[-1]
    assert record["request_body"] is None
    assert record["response_body"]["user_id"] == "138****8000"


def test_5xx_status_logged(stream: io.StringIO) -> None:
    app = create_app(stream=stream, whitelist=())

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/boom")

    assert resp.status_code == 500
    assert _access_records(stream)[-1]["status"] == 500
