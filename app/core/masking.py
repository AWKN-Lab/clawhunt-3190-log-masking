"""结构化日志的落盘前脱敏过滤器。

设计要点（对应工单 3190 需求）：
- 脱敏在日志记录**序列化之前**执行：由 ``logging.Filter`` 改写 LogRecord，
  随后 JSON Formatter 才做序列化，因此落盘/输出到 stdout 的永远是脱敏后的值。
- 键名规则命中即整值替换为 ``[REDACTED]``，dict / list 递归处理。
- 值规则按固定顺序执行：JWT → 邮箱 → 18 位身份证 → 银行卡 → 手机号。
- 规则可通过 JSON 文件覆盖（``MASKING_RULES_PATH``），默认使用本文件内置规则。

判定口径（README 同步说明）：
- 键名按小写后「整键命中」或「按非字母数字切分后任一段命中」判定，
  因此 ``access_token``、``token_type``、``password_hash`` 都会被命中。
- 18 位纯数字串按需求「18 位身份证号」处理，保留首尾各 1 位；
  银行/储蓄卡取 12–17、19–20 位（避免与身份证口径互相吞掉）。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

REDACTED = "[REDACTED]"
JWT_MARK = "[JWT]"

# 需求点名的敏感键（①）
DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "totp",
        "otp",
        "otp_code",
        "id_card",
        "bank_card",
    }
)

# JWT 与邮箱按触发字符单独处理；数字类规则合并为单次扫描（身份证/银行卡/手机号）。
_JWT_RE = re.compile(r"(?<![\w-])(?:[A-Za-z0-9_-]{8,}\.){2}[A-Za-z0-9_-]{8,}(?![\w-])")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NUMERIC_RE = re.compile(
    r"(?P<id>(?<![\w-])\d{17}[\dXx](?![\w-]))"
    r"|(?P<bank>(?<![\w-])(?:\d{12,17}|\d{19,20})(?![\w-]))"
    r"|(?P<phone>(?<![\w-])1[3-9]\d{9}(?![\w-]))"
)

_DIGIT_RE = re.compile(r"\d")

_DEFAULT_RULES: dict[str, Any] = {
    "sensitive_keys": sorted(DEFAULT_SENSITIVE_KEYS),
    "jwt_marker": JWT_MARK,
    "redacted_marker": REDACTED,
}


def _load_rules() -> dict[str, Any]:
    """读取可选规则文件；文件不存在或损坏时回落内置默认值。"""

    rules = dict(_DEFAULT_RULES)
    path = os.environ.get("MASKING_RULES_PATH", "").strip()
    if not path:
        return rules
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return rules
    if isinstance(payload, dict):
        keys = payload.get("sensitive_keys")
        if isinstance(keys, list) and all(isinstance(k, str) for k in keys):
            rules["sensitive_keys"] = [k.strip().lower() for k in keys if k.strip()]
        for marker in ("jwt_marker", "redacted_marker"):
            value = payload.get(marker)
            if isinstance(value, str) and value:
                rules[marker] = value
    return rules


_RULES = _load_rules()
_SENSITIVE_KEYS: frozenset[str] = frozenset(_RULES["sensitive_keys"])
_REDACTED: str = _RULES["redacted_marker"]
_JWT_MARK: str = _RULES["jwt_marker"]


def is_sensitive_key(key: str) -> bool:
    """键名是否命中敏感词表（整键或分段命中）。

    用 str.replace/split 代替正则切分，keys 属于高频路径。
    """

    lowered = key.lower()
    if lowered in _SENSITIVE_KEYS:
        return True
    if "_" not in lowered and "-" not in lowered:
        return False
    for segment in lowered.replace("-", "_").split("_"):
        if segment and segment in _SENSITIVE_KEYS:
            return True
    return False


def _mask_jwt(match: re.Match[str]) -> str:
    return _JWT_MARK


def _mask_email(match: re.Match[str]) -> str:
    value = match.group(0)
    local, _, domain = value.partition("@")
    return f"{local[:1]}***@{domain}"


def _mask_numeric(match: re.Match[str]) -> str:
    value = match.group(0)
    kind = match.lastgroup
    if kind == "id":
        return f"{value[0]}{'*' * 16}{value[-1]}"
    if kind == "bank":
        return f"{'*' * (len(value) - 4)}{value[-4:]}"
    return f"{value[:3]}****{value[-4:]}"  # phone


def mask_text(value: str) -> str:
    """对单个字符串按值规则脱敏；无敏感特征时原样返回。

    用触发字符短路，避免对普通字段做无谓的正则扫描；
    数字类三条规则合并为一次 sub。这是「单条 < 0.2ms」的关键路径。
    """

    if len(value) < 6:  # 最短敏感值（邮箱）为 6 字符
        return value
    if (
        len(value) == 36
        and value[8] == "-"
        and value[13] == "-"
        and value[18] == "-"
        and value[23] == "-"
    ):
        return value  # 内部 UUID 不含敏感值，直接放行（日志高频字段）
    has_at = "@" in value
    has_dot = "." in value
    has_digit = _DIGIT_RE.search(value) is not None
    if not has_at and not has_dot and not has_digit:
        return value
    if has_dot and value.count(".") >= 2:
        value = _JWT_RE.sub(_mask_jwt, value)
    if has_at:
        value = _EMAIL_RE.sub(_mask_email, value)
    if has_digit:
        value = _NUMERIC_RE.sub(_mask_numeric, value)
    return value


def mask_value(value: Any) -> Any:
    """按值规则脱敏任意标量/容器（键名规则不参与）。"""

    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {k: mask_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        masked = [mask_value(item) for item in value]
        return type(value)(masked) if isinstance(value, tuple) else masked
    return value


def mask_payload(payload: Any) -> Any:
    """递归脱敏：键名命中先整体替换，否则继续按值规则处理。"""

    if isinstance(payload, dict):
        result: dict[Any, Any] = {}
        for key, value in payload.items():
            if isinstance(key, str) and is_sensitive_key(key):
                result[key] = _REDACTED
            else:
                result[key] = mask_payload(value)
        return result
    if isinstance(payload, list):
        return [mask_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(mask_payload(item) for item in payload)
    if isinstance(payload, str):
        return mask_text(payload)
    return payload


def mask_before_serialize(payload: Any) -> Any:
    """序列化前脱敏的统一入口（与日志 Filter 共用同一实现）。"""

    return mask_payload(payload)


def encode_payload(payload: Any) -> str:
    """把结构化成 JSON 文本；序列化失败时回落为脱敏后的 repr。"""

    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return mask_text(repr(payload))


def load_whitelist(raw: str | Iterable[str] | None) -> tuple[str, ...]:
    """解析请求/响应体记录白名单。

    支持逗号分隔字符串或字符串序列；``/api/orders/*`` 形式为前缀匹配。
    """

    if raw is None:
        return ()
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",")]
    else:
        items = [str(part).strip() for part in raw]
    return tuple(item for item in items if item)


def whitelisted(path: str, whitelist: Iterable[str]) -> bool:
    for rule in whitelist:
        if rule.endswith("*"):
            if path.startswith(rule[:-1]):
                return True
        elif path == rule:
            return True
    return False
