"""统一结构化日志：单行 JSON 输出到 stdout，落盘前完成脱敏。

字段表（README 同步）::

    ts           ISO 8601（UTC，毫秒精度，Z 结尾）
    level        日志级别
    logger       日志器名称
    msg          消息（已脱敏）
    request_id   中间件生成或沿用请求头 X-Request-ID
    org_id       组织 UUID
    site_id      站点 UUID
    user_id      内部用户 UUID（不写姓名）
    route        请求路径
    status       HTTP 状态码
    duration_ms  处理耗时（毫秒）
    env          运行环境

为什么选 ``logging.Filter`` 而不是 structlog：
过滤器在 Formatter 序列化**之前**改写 LogRecord，满足「落盘前脱敏」；
标准库实现零第三方依赖，便于私有化部署审计。structlog 需要额外依赖，
且其 processor 链与 stdlib 混用时容易出现绕过路径。
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, TextIO

from app.core.config import get_settings
from app.core.masking import mask_before_serialize, mask_payload, mask_text

# 记录里由中间件注入的字段；其余非标准属性一律当作扩展字段输出
REQUEST_FIELDS: tuple[str, ...] = (
    "request_id",
    "org_id",
    "site_id",
    "user_id",
    "route",
    "status",
    "duration_ms",
)

_FIELD_ORDER = ("ts", "level", "logger", "msg", *REQUEST_FIELDS, "env")

_ctx: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("log_context", default={})

_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__  # type: ignore[arg-type]
) | {"message", "asctime", "taskName"}


def bind_request_context(**fields: Any) -> contextvars.Token:
    """绑定请求上下文（contextvar），供 Formatter 兜底取字段。"""

    return _ctx.set({**_ctx.get(), **fields})


def update_request_context(**fields: Any) -> None:
    _ctx.set({**_ctx.get(), **fields})


def reset_request_context(token: contextvars.Token) -> None:
    _ctx.reset(token)


class MaskingFilter(logging.Filter):
    """在序列化前把 LogRecord 的 msg / args / 扩展字段全部脱敏。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_text(record.msg)
        elif isinstance(record.msg, (dict, list, tuple)):
            record.msg = mask_payload(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = mask_payload(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(mask_payload(item) for item in record.args)

        for key in list(record.__dict__):
            if key in _STANDARD_ATTRS or key in ("msg", "args"):
                continue
            record.__dict__[key] = mask_payload(record.__dict__[key])
        return True


class JsonFormatter(logging.Formatter):
    """按固定字段顺序输出单行 JSON。"""

    def __init__(self, env: str | None = None) -> None:
        super().__init__()
        self.env = env or get_settings().env

    def format(self, record: logging.LogRecord) -> str:
        ctx = _ctx.get()
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field in REQUEST_FIELDS:
            payload[field] = getattr(record, field, ctx.get(field))
        payload["env"] = getattr(record, "env", ctx.get("env") or self.env)

        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key in payload or key in ("msg", "args"):
                continue
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def configure_logging(
    level: str | None = None,
    env: str | None = None,
    stream: TextIO | None = None,
) -> logging.Logger:
    """装配根日志器；同时关闭 uvicorn 默认访问日志。

    幂等：重复调用会重建 handler，不会叠加输出。
    """

    settings = get_settings()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for existing in list(root.filters):
        root.removeFilter(existing)

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter(env=env or settings.env))
    # 过滤器必须挂在 handler 上：logger 级 filter 不会作用于子 logger 传播上来的记录
    handler.addFilter(MaskingFilter())
    root.addHandler(handler)
    root.addFilter(MaskingFilter())
    root.setLevel(level or settings.log_level)

    # 关闭 uvicorn 默认访问日志：改由 RequestLogMiddleware 统一输出脱敏后的 JSON
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True

    return logging.getLogger("app")


def get_logger(name: str = "app") -> logging.Logger:
    return logging.getLogger(name)


def mask_record(payload: dict[str, Any]) -> dict[str, Any]:
    """供基准测试使用的单条脱敏入口（与 Filter 同一实现）。"""

    return mask_before_serialize(payload)
