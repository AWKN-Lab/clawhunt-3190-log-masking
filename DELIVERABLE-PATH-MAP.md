# 交付物路径对照表（DELIVERABLE PATH MAP）

> **为什么有这张表**：投标时提交的第一版提案里写的是"计划中的文件路径"；本仓落地时
> 部分文件做了更准确的命名或换了位置（**同一实现**）。买家若按提案里的路径找会找不到，
> 本表给出**一一对应**，按提案的路径也能定位到本仓的实现与证据。
>
> - 提案原文（第一版）：`proposals/3190-proposal.md`（工作区 `output/proposals/`）
> - 平台现行提案：2026-11-24 修订版，`sha256=414cbfe8b698e928c519ea30a6a5f61f7b211a390a14412cf15e5e83184e2563`
>   （修订后即按本表"本仓实际路径"书写）
> - 逐条验收对照见 `ACCEPTANCE.md`；证据见 `ACCEPTANCE-EVIDENCE.md` / `ACCEPTANCE-EVIDENCE-EN.md` / `TEST-REPORT.md`

## 一、路径对照

| 提案里写的路径 | 本仓实际路径 | 说明 |
|---|---|---|
| `app/core/logging.py` | `app/core/logging.py` | 同名：单行 JSON 日志出口（脱敏在序列化之前） |
| `app/core/logging_rules.yml` | `app/core/masking.py`（内置规则）<br>`app/core/config.py`（配置读取） | 规则**未用独立 yml**：默认用 `masking.py` 内置规则，可用环境变量 `MASKING_RULES_PATH` 指向 JSON 覆盖 |
| `app/core/middleware.py` | `app/core/middleware.py` | 同名：请求日志中间件（`X-Request-ID` 回写、`duration_ms`、`status`、`route`） |
| `tests/test_logging_redaction.py` | `tests/test_logging.py`<br>`tests/test_masking.py` | 拆成两个文件：日志格式断言 / 脱敏断言（AC1、AC2） |
| `tests/bench_redaction.py` | `tests/test_benchmark.py`（pytest 版）<br>`bench/bench_masking.py`（独立基准脚本） | AC3 基准：两处都可跑，输出见 `artifacts/bench.txt` |
| `docker/Dockerfile` + `docker/entrypoint.sh` | `Dockerfile`（**仓库根**） | 单文件；启动命令（`uvicorn --no-access-log`）写在 Dockerfile 的 `CMD` 里，没有单独的 entrypoint 文件 |
| `README.md` | `README.md` | 字段表 / 规则表 / 复跑命令 / 对接点说明 |

## 二、提案未列、但本仓实际提供（用于验收）

| 路径 | 用途 |
|---|---|
| `ACCEPTANCE.md` / `ACCEPTANCE-EVIDENCE.md` / `ACCEPTANCE-EVIDENCE-EN.md` | 逐条 AC ↔ 实现 ↔ 复跑命令 ↔ 实测输出（中文 + 英文） |
| `TEST-REPORT.md` | 全量测试报告 |
| `artifacts/` | 真实运行产物：`pytest.txt`、`bench.txt`、`docker-build.txt`、`docker-evidence.txt`、`docker-log-check.txt`、`uvicorn-stdout.txt`、`uvicorn-stderr.txt` |
| `scripts/check_container_logs.py` | AC4 容器日志断言（可对任意日志文件复跑） |
| `scripts/secret_scan.py` / `scripts/manifest.py` | 秘密扫描 / SHA256 清单（`build` / `verify`） |
| `docs/3190-requirement-original.md`、`docs/problem-3190.json` | 需求原文快照（可核对本仓是否跑偏） |
| `tests/test_middleware.py`、`tests/test_no_uvicorn_access_log.py` | 中间件与"无 uvicorn 默认访问日志"的独立用例 |

## 三、复跑命令（与提案一致）

```bash
python -m pip install -r requirements.txt
python -m pytest -q                 # 51 用例，含真实 uvicorn 子进程集成用例
python -m pytest tests/test_masking.py -q
python -m pytest tests/test_no_uvicorn_access_log.py -q
python bench/bench_masking.py       # AC3 基准输出
python scripts/check_container_logs.py artifacts/docker-evidence.txt   # AC4 容器日志断言
python scripts/secret_scan.py
python scripts/manifest.py verify   # 清单逐文件比对
```

## 四、变更说明

本表为**新增说明文件**，不改动任何实现、测试或证据；
`MANIFEST.sha256` 已按本仓规则重算（`python scripts/manifest.py build`），可 `verify` 通过。
