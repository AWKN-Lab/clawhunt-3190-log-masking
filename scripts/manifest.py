"""生成与校验 SHA256 清单。

用法：
    python scripts/manifest.py build      # 生成 MANIFEST.sha256
    python scripts/manifest.py verify     # 逐文件重新计算并比对
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git", ".venv", ".mypy_cache", ".approval_tests_temp", "node_modules", ".local-raw"}
EXCLUDE_PREFIXES = ("docs/raw/",)
EXCLUDE_FILES = {MANIFEST.name, ".env"}


def _iter_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(EXCLUDE_PREFIXES):
            continue
        if path.name in EXCLUDE_FILES or path.suffix == ".pyc":
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build() -> int:
    lines = [f"{_sha256(path)}  {path.relative_to(ROOT).as_posix()}" for path in _iter_files()]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"MANIFEST.sha256 已生成：{len(lines)} 个文件")
    return 0


def verify() -> int:
    if not MANIFEST.exists():
        print("MANIFEST.sha256 不存在", file=sys.stderr)
        return 2
    entries: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, rel = line.partition("  ")
        entries[rel] = digest

    missing: list[str] = []
    mismatched: list[str] = []
    for rel, expected in entries.items():
        path = ROOT / rel
        if not path.exists():
            missing.append(rel)
            continue
        actual = _sha256(path)
        if actual != expected:
            mismatched.append(f"{rel}: 期望 {expected} 实际 {actual}")

    untracked = [
        path.relative_to(ROOT).as_posix()
        for path in _iter_files()
        if path.relative_to(ROOT).as_posix() not in entries
    ]

    print(f"校验目录：{ROOT}")
    print(f"清单条目：{len(entries)}  匹配：{len(entries) - len(missing) - len(mismatched)}")
    if missing:
        print(f"缺失 {len(missing)}: {missing}")
    if mismatched:
        print(f"不一致 {len(mismatched)}:")
        for item in mismatched:
            print(f"  - {item}")
    if untracked:
        print(f"清单外文件 {len(untracked)}: {untracked}")
    ok = not missing and not mismatched and not untracked
    problems = len(missing) + len(mismatched) + len(untracked)
    print(f"PROBLEMS={problems}")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    if command == "build":
        raise SystemExit(build())
    if command == "verify":
        raise SystemExit(verify())
    print("未知命令，使用 build 或 verify", file=sys.stderr)
    raise SystemExit(2)
