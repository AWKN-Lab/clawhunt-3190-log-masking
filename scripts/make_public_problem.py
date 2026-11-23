"""把平台接口原始响应转成可公开的工单元数据。

保留：id、title、difficulty、category、url、description、acceptance_criteria
剔除：提交者、投标列表、目标 agent、托管金额、内部仓库与路由字段

用法：python scripts/make_public_problem.py
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "docs" / "raw" / "problem-3190.json"
PUBLIC = ROOT / "docs" / "problem-3190.json"
KEEP = ("id", "title", "difficulty", "category", "url", "description", "acceptance_criteria")


def main() -> int:
    data = json.loads(RAW.read_text(encoding="utf-8"))["data"]
    public = {key: data.get(key) for key in KEEP}
    PUBLIC.write_text(
        json.dumps({"data": public}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"written: {PUBLIC.relative_to(ROOT)}  fields={len(public)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
