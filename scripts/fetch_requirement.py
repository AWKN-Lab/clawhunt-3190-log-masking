"""拉取工单 3190 原文与验收标准，原样落盘（不改写）。

凭据只从 CLAWHUNT_API_KEY 环境变量读取，绝不写盘、不打印。
用法：
    set CLAWHUNT_API_KEY=...   (Windows PowerShell: $env:CLAWHUNT_API_KEY='...')
    python scripts/fetch_requirement.py
"""

import json
import os
import pathlib
import sys
import urllib.request

PROBLEM_ID = 3190
BASE = os.environ.get("CLAWHUNT_BASE_URL", "https://clawhunt.store")
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "docs"


def main() -> int:
    key = os.environ.get("CLAWHUNT_API_KEY", "").strip()
    if not key:
        print("CLAWHUNT_API_KEY 未设置，拒绝执行", file=sys.stderr)
        return 2
    req = urllib.request.Request(
        f"{BASE}/api/v1/problems/{PROBLEM_ID}",
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "clawhunt-agent",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    payload = json.loads(body)
    data = payload["data"]

    raw_dir = OUT_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"problem-{PROBLEM_ID}.json").write_text(body, encoding="utf-8")

    md = "\n".join(
        [
            f"# 工单 {PROBLEM_ID} 原文（机器抓取，未改写）",
            "",
            f"- 拉取接口：`GET {BASE}/api/v1/problems/{PROBLEM_ID}`",
            "- 请求头：`User-Agent: clawhunt-agent`",
            f"- 标题：{data['title']}",
            "",
            "## 1. 需求原文（description 字段逐字）",
            "",
            data["description"],
            "",
            "## 2. 验收标准原文（acceptance_criteria 字段逐字）",
            "",
            "```text",
            data["acceptance_criteria"],
            "```",
            "",
            "## 3. 原始 JSON",
            "",
            f"见 `docs/raw/problem-{PROBLEM_ID}.json`（接口响应原样落盘）。",
            "",
        ]
    )
    (OUT_DIR / f"{PROBLEM_ID}-requirement-original.md").write_text(md, encoding="utf-8")
    print(f"ok: docs/{PROBLEM_ID}-requirement-original.md, docs/raw/problem-{PROBLEM_ID}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
