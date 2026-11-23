"""校验容器日志：不存在 uvicorn 默认访问日志行。

用法：
    docker logs <container> > container.log 2>&1
    python scripts/check_container_logs.py container.log

也支持传入本仓库的 artifacts/docker-evidence.txt（自动截取 `=== docker logs ===` 段）。
零条默认访问日志且至少一条 app.access JSON 记录时退出码为 0。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

DEFAULT_ACCESS_RE = re.compile(r'INFO:\s+\d+\.\d+\.\d+\.\d+:\d+ - "(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) ')
RAW_ACCESS_RE = re.compile(r'"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) [^"]* HTTP/1\.[01]" \d{3}')


def _logs_from(text: str) -> list[str]:
    if "=== docker logs ===" in text:
        text = text.split("=== docker logs ===", 1)[1]
        text = text.split("=== docker inspect status ===", 1)[0]
    return [line for line in text.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法: python scripts/check_container_logs.py <logfile>", file=sys.stderr)
        return 2
    path = pathlib.Path(argv[1])
    if not path.exists():
        print(f"文件不存在: {path}", file=sys.stderr)
        return 2

    lines = _logs_from(path.read_text(encoding="utf-8", errors="replace"))
    offenders = [line for line in lines if DEFAULT_ACCESS_RE.search(line) or RAW_ACCESS_RE.search(line)]
    json_lines = [line for line in lines if line.startswith("{")]
    access = []
    for line in json_lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("logger") == "app.access":
            access.append(record)

    print("container log check")
    print(f"lines={len(lines)}")
    print(f"json_lines={len(json_lines)}")
    print(f"access_log_json_lines={len(access)}")
    print(f"uvicorn_default_access_lines={len(offenders)}")
    for line in offenders:
        print(f"  - {line[:160]}")
    problems = len(offenders) + (0 if access else 1)
    print(f"PROBLEMS={problems}")
    print("RESULT:", "PASS" if problems == 0 else "FAIL")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
