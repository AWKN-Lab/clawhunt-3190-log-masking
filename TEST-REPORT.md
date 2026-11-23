# 工单 3190 测试报告

执行时间：2026-11-23（本机时区 America/New_York）
执行环境：Windows / PowerShell 7 / Python 3.14.3 / fastapi 0.139.0 / uvicorn 0.49.0 / pytest 8.4.2 / httpx 0.28.1
项目根：仓库根目录

## 1. 结果汇总

| 命令 | 退出码 | 结果 |
|---|---|---|
| `python -m pytest -q` | 0 | **51 passed**, 1 warning, 6.51s |
| `python bench/bench_masking.py` | 0 | PASS（CPU mean 0.0266ms / p95 0.0469ms，限值 0.2ms） |
| `python scripts/secret_scan.py` | 0 | `PROBLEMS=0`（35 个文件） |
| `python -m compileall -q app tests bench scripts` | 0 | 语法检查通过 |

用例分布：

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_masking.py` | 35 | 值规则 8 组、敏感键 16 组、AC1 汇总、AC2 嵌套、UUID 不被误伤、白名单匹配 |
| `tests/test_logging.py` | 6 | 单行 JSON、12 字段、extra 脱敏、msg+args 脱敏、非美化输出 |
| `tests/test_middleware.py` | 8 | X-Request-ID 沿用/生成/回写、身份头、默认不记正文、白名单正文脱敏、5xx |
| `tests/test_no_uvicorn_access_log.py` | 1 | AC4：真实 uvicorn 子进程 stdout 取证 |
| `tests/test_benchmark.py` | 1 | AC3：单条脱敏 <0.2ms 断言 |

warning 说明：`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`，来自 FastAPI/Starlette 与 httpx 的版本提示，不影响任何断言。

原始输出：`artifacts/pytest.txt`

## 2. AC1 / AC2：敏感样本断言

- AC1 用例 `test_ac1_all_sample_types_masked_in_one_payload` 在同一结构中放入手机号、身份证、邮箱、JWT、口令，断言每项输出形态，并逐一断言原文（含 JWT、口令）不出现在序列化结果中。
- AC2 用例 `test_ac2_nested_dict_and_list_redacted` 覆盖三层 dict、list 内的 dict、list 内的 list，断言敏感键全部为 `[REDACTED]`，非敏感键与数字原样保留。
- 日志路径由 `test_extra_payload_masked`、`test_msg_and_args_masked_before_serialization`、`test_whitelisted_body_logged_and_masked` 验证：脱敏发生在 Formatter 序列化之前。

## 3. AC3：基准输出（原样）

命令：`python bench/bench_masking.py`（3000 次，预热 200 次，仅测脱敏，不含 IO 与序列化）

```text
masking benchmark (single log record, masking only)
batches        : 10 x 2000
wall mean      : 0.06817 ms
wall p50       : 0.06701 ms
wall p95       : 0.07842 ms
cpu  mean      : 0.02656 ms
cpu  p50       : 0.03125 ms
cpu  p95       : 0.04688 ms
limit          : 0.20000 ms
result         : PASS (cpu mean < 0.2 ms and cpu p95 < 0.2 ms)
```

说明：样本是含嵌套 payload（手机号/身份证/邮箱/口令/JWT/银行卡）的完整日志记录，属偏重样本。单条计时会被操作系统计时粒度（约 15.6ms）与并行进程调度放大，因此按 10 批 × 2000 条测量后摊薄：CPU 每条均值 0.0266ms、p95 0.0469ms，墙钟均值 0.0682ms，均有 4 倍以上余量。`tests/test_benchmark.py` 以 CPU 均值与 p95 双门禁断言。

原始输出：`artifacts/bench.txt`

## 4. AC4：无 uvicorn 默认访问日志

### 4.1 容器内实测（主证据）

- 环境：Docker Desktop 29.9.2（Windows + WSL2），基础镜像 `python:3.11-slim`，**不加** `--no-access-log`。
- 执行：`docker build` → `docker run -d --name ch3190-review -p 127.0.0.1::8000` → 请求 `/health` 两次 → `docker logs` → `docker rm -f`。
- 实测映射端口 `127.0.0.1:64482`；容器状态 `running`，`restarts=0`。
- `docker logs` 共 7 行：3 条 JSON（1 条启动 + 2 条 `app.access`）+ 4 条 uvicorn 生命周期信息，**默认访问日志 0 条**。
- 断言（`python scripts/check_container_logs.py artifacts/docker-evidence.txt`）：

```text
container log check
lines=7
json_lines=3
access_log_json_lines=2
uvicorn_default_access_lines=0
PROBLEMS=0
RESULT: PASS
```

原始取证：`artifacts/docker-evidence.txt`（构建、运行、端口映射、docker logs、容器状态）、`artifacts/docker-build.txt`、`artifacts/docker-log-check.txt`。

### 4.2 进程级自动化回归（CI 可跑）

`tests/test_no_uvicorn_access_log.py` 的取证逻辑：绑定回环端口 0 取空闲端口 → 以 `python -m uvicorn app.main:app` 启动（**不加** `--no-access-log`）→ 请求 `/health` 两次 → 终止进程 → 抓 stdout/stderr。

断言：
1. 不存在 `INFO:     127.0.0.1:xxxxx - "GET /health HTTP/1.1" 200 OK` 形态的行；
2. 不存在任何 `"GET ... HTTP/1.1" 200` 裸访问行；
3. 至少 2 条 `"logger":"app.access"` 的 JSON 访问记录，字段完整。

人工复跑同样场景的原始日志（stdout / stderr 分开保存）：`artifacts/uvicorn-stdout.txt`、`artifacts/uvicorn-stderr.txt`。

```text
INFO:     Started server process [16568]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:57010 (Press CTRL+C to quit)
```

结论：进程 stderr 只有 uvicorn 生命周期信息，**没有任何访问日志行**；访问日志全部来自本中间件，为单行 JSON。容器日志结论与之一致。

## 5. SHA256 清单与干净目录复校验

```text
python scripts/manifest.py build    -> MANIFEST.sha256 已生成：39 个文件
python scripts/manifest.py verify   -> 清单条目 39，匹配 39，PROBLEMS=0，RESULT: PASS（退出码 0）
```

干净目录复校验（复制到临时干净目录，排除缓存目录）：

| 步骤 | 退出码 | 结果 |
|---|---|---|
| `python scripts/manifest.py verify` | 0 | 39/39 匹配，PROBLEMS=0，RESULT: PASS |
| `python -m pytest -q` | 0 | 51 passed, 1 warning |

说明：robocopy 退出码 1 表示「已复制文件」，属正常；清单校验与测试均退出码 0。
公开化处理：`artifacts/pytest.txt` 中本机 site-packages 绝对路径已替换为 `<site-packages>`，测试结果与条数未改；原始输出保留在仓库外的本地目录。

## 6. 未执行项

- 镜像仅本地构建与运行，未推送到任何 registry。
- 未投标、未调用平台提交接口。
