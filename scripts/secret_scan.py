"""公开前密钥与隐私扫描。

规则：cph_ / sk- / ghp_ 等令牌、私钥头、内网 IP、本机路径、agent 与 bid 编号、邮箱。
零命中才允许发布（PROBLEMS=0）。

用法：python scripts/secret_scan.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "node_modules", ".approval_tests_temp", ".local-raw"}
SKIP_FILES = {".env"}

# 允许出现的合成数据与回环地址
EMAIL_ALLOWLIST = ("example.com", "example.org", "example.net", "example.invalid")
IP_ALLOWLIST = ("127.0.0.1",)

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("clawhunt_key", re.compile(r"cph_[A-Za-z0-9]{10,}")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("github_token", re.compile(r"\b(ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{16,}")),
    ("private_key", re.compile(r"BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY")),
    ("internal_ip",
     re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
    ("local_path", re.compile(r"\b[A-Za-z]:[\\/]|file:/{3}|/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/")),
    ("agent_id", re.compile(r"\b(?:agent_id|target_agent_id|agent\s*id)\b\s*[:=#]?\s*\d+", re.IGNORECASE)),
    ("bid_no", re.compile(r"\bbid\b\s*[:=#]?\s*\d{3,}", re.IGNORECASE)),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".zip", ".gz", ".pdf", ".ico"}


def _iter_files() -> list[pathlib.Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILES or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        files.append(path)
    return files


def main() -> int:
    problems: list[str] = []
    for path in _iter_files():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:  # pragma: no cover
            problems.append(f"{path.relative_to(ROOT)}: 读取失败 {exc}")
            continue
        for number, line in enumerate(lines, start=1):
            for name, pattern in RULES:
                for match in pattern.finditer(line):
                    text = match.group(0)
                    if name == "email" and text.split("@")[-1].lower() in EMAIL_ALLOWLIST:
                        continue
                    if name == "internal_ip" and text in IP_ALLOWLIST:
                        continue
                    if name == "local_path" and text == "http://":  # pragma: no cover
                        continue
                    problems.append(f"{path.relative_to(ROOT)}:{number} [{name}] {text[:80]}")

    if problems:
        print(f"PROBLEMS={len(problems)}")
        for item in problems:
            print(f"  - {item}")
        return 1
    print(f"scanned_files={len(_iter_files())}")
    print("PROBLEMS=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
