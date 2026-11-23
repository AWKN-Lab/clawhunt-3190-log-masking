"""AC4：容器/进程日志中不存在 uvicorn 默认格式的访问日志行。

本测试真实拉起 uvicorn 子进程（未加 ``--no-access-log``），通过 stdout 取证：
1. 不存在 uvicorn 默认访问日志格式行；
2. 访问日志只有本中间件输出的 JSON 行，且字段齐全。
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ACCESS_RE = re.compile(r'INFO:\s+\d+\.\d+\.\d+\.\d+:\d+ - "(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) ')
UVICORN_RAW_LINE_RE = re.compile(r'"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) [^"]* HTTP/1\.[01]" \d{3}')


def _free_loopback_port() -> int:
    """绑定回环端口 0 取得空闲端口；绑定前即完成占用检查（PORTS.md 纪律）。"""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.2)
    raise AssertionError(f"uvicorn 未在 {timeout}s 内就绪: {url}")


@pytest.mark.integration
def test_no_uvicorn_default_access_log() -> None:
    port = _free_loopback_port()
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "APP_ENV": "test",
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_ready(f"{base}/health")
        for _ in range(2):
            with urllib.request.urlopen(f"{base}/health", timeout=5) as resp:
                assert resp.status == 200
        time.sleep(0.3)  # 留出访问日志刷出时间
    finally:
        proc.terminate()
        try:
            output, _ = proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
            output, _ = proc.communicate(timeout=10)

    lines = [line for line in output.splitlines() if line.strip()]

    offenders = [line for line in lines if DEFAULT_ACCESS_RE.search(line) or UVICORN_RAW_LINE_RE.search(line)]
    assert offenders == [], f"发现 uvicorn 默认访问日志: {offenders}"

    access_records = [
        json.loads(line)
        for line in lines
        if line.startswith("{") and '"logger":"app.access"' in line
    ]
    assert len(access_records) >= 2, output
    for record in access_records:
        assert record["route"] == "/health"
        assert record["status"] == 200
        assert record["request_id"]
        assert isinstance(record["duration_ms"], float)
