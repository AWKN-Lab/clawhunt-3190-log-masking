"""脱敏规则单元测试：覆盖 AC1（敏感样本）与 AC2（嵌套容器）。"""

from __future__ import annotations

import pytest

from app.core.masking import (
    JWT_MARK,
    REDACTED,
    is_sensitive_key,
    mask_payload,
    mask_text,
    whitelisted,
)

PHONE = "13800138000"
ID_CARD = "110101199003071234"
EMAIL = "zhangsan@example.com"
BANK_CARD_16 = "6222021234567890"
BANK_CARD_19 = "6222021234567890123"
JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IuWCsOW3peS4miJ9"
    ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (PHONE, "138****8000"),
        (ID_CARD, "1" + "*" * 16 + "4"),
        (EMAIL, "z***@example.com"),
        (JWT, JWT_MARK),
        (f"联系我 {PHONE}", "联系我 138****8000"),
        (f"卡号 {BANK_CARD_16}", f"卡号 {'*' * 12}7890"),
        (f"卡号 {BANK_CARD_19}", f"卡号 {'*' * 15}0123"),
        ("普通文本没有敏感信息", "普通文本没有敏感信息"),
    ],
    ids=["phone", "id-card", "email", "jwt", "phone-inline", "bank-16", "bank-19", "plain"],
)
def test_value_rules(raw: str, expected: str) -> None:
    assert mask_text(raw) == expected


def test_ac1_all_sample_types_masked_in_one_payload() -> None:
    """AC1：手机号/身份证/邮箱/JWT/口令样本在同一结构中全部被脱敏。"""

    payload = {
        "phone": PHONE,
        "id_card": ID_CARD,
        "identity_no": ID_CARD,
        "email": EMAIL,
        "authorization": f"Bearer {JWT}",
        "password": "P@ssw0rd!",
        "note": f"手机 {PHONE} 邮箱 {EMAIL}",
    }
    masked = mask_payload(payload)

    assert masked["phone"] == "138****8000"
    assert masked["id_card"] == REDACTED  # 键名命中优先整值替换
    assert masked["identity_no"] == "1" + "*" * 16 + "4"  # 仅值规则命中
    assert masked["email"] == "z***@example.com"
    assert masked["password"] == REDACTED
    assert masked["authorization"] == REDACTED
    assert PHONE not in masked["note"] and EMAIL not in masked["note"]
    # 原文不得出现在序列化结果里
    serialized = str(masked)
    for secret in (PHONE, ID_CARD, EMAIL, JWT, "P@ssw0rd!"):
        assert secret not in serialized


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "totp",
        "otp_code",
        "id_card",
        "bank_card",
        "PASSWORD",
        "password_hash",
        "token_type",
    ],
)
def test_sensitive_key_detection(key: str) -> None:
    assert is_sensitive_key(key) is True


@pytest.mark.parametrize("key", ["request_id", "org_id", "route", "status", "duration_ms", "msg"])
def test_non_sensitive_key_detection(key: str) -> None:
    assert is_sensitive_key(key) is False


def test_ac2_nested_dict_and_list_redacted() -> None:
    """AC2：嵌套 dict 与 list 中的敏感键同样替换为 [REDACTED]。"""

    payload = {
        "outer": {
            "password": "pw-1",
            "profile": {"access_token": "tok", "nickname": "张三"},
            "items": [
                {"secret": "s1", "value": 1},
                ["plain", {"cookie": "c=1"}],
            ],
        },
        "list_top": [{"refresh_token": "r"}, {"bank_card": "6222021234567890"}],
    }
    masked = mask_payload(payload)

    assert masked["outer"]["password"] == REDACTED
    assert masked["outer"]["profile"]["access_token"] == REDACTED
    assert masked["outer"]["profile"]["nickname"] == "张三"
    assert masked["outer"]["items"][0]["secret"] == REDACTED
    assert masked["outer"]["items"][0]["value"] == 1
    assert masked["outer"]["items"][1][0] == "plain"
    assert masked["outer"]["items"][1][1]["cookie"] == REDACTED
    assert masked["list_top"][0]["refresh_token"] == REDACTED
    assert masked["list_top"][1]["bank_card"] == REDACTED


def test_tuple_preserved() -> None:
    masked = mask_payload(({"password": "p"}, PHONE))
    assert isinstance(masked, tuple)
    assert masked[0]["password"] == REDACTED
    assert masked[1] == "138****8000"


def test_non_string_values_untouched() -> None:
    payload = {"status": 200, "duration_ms": 1.23, "ok": True, "none": None}
    assert mask_payload(payload) == payload


def test_uuid_not_mangled() -> None:
    value = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    assert mask_text(value) == value


def test_whitelist_matching() -> None:
    rules = ("/api/orders/*", "/api/login")
    assert whitelisted("/api/orders/123", rules) is True
    assert whitelisted("/api/login", rules) is True
    assert whitelisted("/api/logout", rules) is False
