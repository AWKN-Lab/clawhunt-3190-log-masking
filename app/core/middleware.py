"""请求日志中间件：生成/沿用 X-Request-ID，并统一输出访问日志。

要点：
- 访问日志由本中间件输出（单行 JSON），uvicorn 默认访问日志在
  ``configure_logging`` 中被关闭，避免重复且未脱敏的访问行。
- ``X-Request-ID`` 沿用请求头或生成 UUID，并回写到响应头。
- 请求体/响应体默认不记录；仅白名单路径记录，且同样走脱敏。
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Awaitable, Callable, Iterable

from app.core import logging as app_logging
from app.core.config import get_settings
from app.core.masking import encode_payload, mask_payload, mask_text, whitelisted

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

_UUID_HEADERS = {
    "org_id": "x-org-id",
    "site_id": "x-site-id",
    "user_id": "x-user-id",
}


def _uuid_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return None


def _header_map(scope: Scope) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }


class RequestLogMiddleware:
    """纯 ASGI 中间件，避免 BaseHTTPMiddleware 的流式响应坑。"""

    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        whitelist: Iterable[str] | None = None,
        max_body_bytes: int | None = None,
    ) -> None:
        settings = get_settings()
        self.app = app
        self.whitelist = tuple(whitelist) if whitelist is not None else settings.body_whitelist
        self.max_body_bytes = max_body_bytes or settings.max_body_bytes
        self.logger = app_logging.get_logger("app.access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = _header_map(scope)
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        path = scope.get("path", "")
        capture_body = whitelisted(path, self.whitelist)

        request_chunks: list[bytes] = []
        response_chunks: list[bytes] = []
        status_code = 500

        token = app_logging.bind_request_context(
            request_id=request_id,
            org_id=_uuid_or_none(headers.get("x-org-id")),
            site_id=_uuid_or_none(headers.get("x-site-id")),
            user_id=_uuid_or_none(headers.get("x-user-id")),
            route=path,
            status=None,
            duration_ms=None,
        )

        async def receive_wrapper() -> dict[str, Any]:
            message = await receive()
            if capture_body and message.get("type") == "http.request":
                request_chunks.append(message.get("body", b""))
            return message

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                raw_headers = list(message.get("headers", []))
                if not any(k.lower() == b"x-request-id" for k, _ in raw_headers):
                    raw_headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": raw_headers}
            elif message["type"] == "http.response.body" and capture_body:
                response_chunks.append(message.get("body", b""))
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            route = getattr(scope.get("route"), "path", None) or path
            extra: dict[str, Any] = {
                "request_id": request_id,
                "org_id": _uuid_or_none(headers.get("x-org-id")),
                "site_id": _uuid_or_none(headers.get("x-site-id")),
                "user_id": _uuid_or_none(headers.get("x-user-id")),
                "route": route,
                "status": status_code,
                "duration_ms": duration_ms,
            }
            if capture_body:
                extra["request_body"] = self._mask_body(request_chunks)
                extra["response_body"] = self._mask_body(response_chunks)
            app_logging.update_request_context(**extra)
            self.logger.info(f"{scope.get('method', '-')} {route}", extra=extra)
            app_logging.reset_request_context(token)

    def _mask_body(self, chunks: list[bytes]) -> Any:
        raw = b"".join(chunks)
        if len(raw) > self.max_body_bytes:
            return f"[BODY_TOO_LARGE:{len(raw)}]"
        if not raw:
            return None
        text = raw.decode("utf-8", errors="replace")
        try:
            import json

            return mask_payload(json.loads(text))
        except ValueError:
            return mask_text(text)
