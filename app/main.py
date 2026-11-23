"""FastAPI 应用装配（工单 3190 交付物的可运行外壳）。

真实项目中由平台主应用 import 本模块的 ``create_app`` 或直接复用
``app.core.logging`` / ``app.core.middleware``；本文件的示例路由只用于
验证日志与脱敏行为，不承载业务。
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable, TextIO

from fastapi import FastAPI, Request

from app.core import logging as app_logging
from app.core.config import Settings, get_settings
from app.core.middleware import RequestLogMiddleware


def create_app(
    settings: Settings | None = None,
    stream: TextIO | None = None,
    whitelist: Iterable[str] | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        app_logging.configure_logging(level=settings.log_level, env=settings.env, stream=stream)
        app_logging.get_logger("app").info("application started", extra={"env": settings.env})
        yield

    application = FastAPI(title="structured-logging-demo", lifespan=lifespan)
    application.state.settings = settings
    application.state.log_stream = stream

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/echo")
    async def echo(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        return {"request_id": request.headers.get("x-request-id"), "echo": payload}

    @application.get("/api/users/{user_id}")
    async def get_user(user_id: str) -> dict[str, str]:
        return {"user_id": user_id}

    application.add_middleware(
        RequestLogMiddleware,
        whitelist=tuple(whitelist) if whitelist is not None else settings.body_whitelist,
        max_body_bytes=settings.max_body_bytes,
    )
    return application


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    # 注意：不传 --no-access-log 也应由 configure_logging 关闭默认访问日志
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8090)
