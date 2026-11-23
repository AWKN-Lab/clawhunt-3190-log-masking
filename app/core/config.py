"""环境配置。所有配置只从环境变量读取，不落盘明文。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.core.masking import load_whitelist


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: os.environ.get("APP_ENV", "dev"))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO").upper())
    body_whitelist: tuple[str, ...] = field(
        default_factory=lambda: load_whitelist(os.environ.get("LOG_BODY_WHITELIST", ""))
    )
    max_body_bytes: int = field(
        default_factory=lambda: int(os.environ.get("LOG_MAX_BODY_BYTES", "65536"))
    )


def get_settings() -> Settings:
    return Settings()
