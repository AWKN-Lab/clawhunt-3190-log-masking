# 工单 3190 · 验收证据索引（ACCEPTANCE-EVIDENCE）

逐条 AC ↔ 证据：测试名、可复跑命令、预期输出、关键断言原文。
需求与 AC 原文见 `docs/3190-requirement-original.md`；实现位置与口径说明见 `ACCEPTANCE.md`。
英文逐句版（AC1–AC4，编号一致）：`ACCEPTANCE-EVIDENCE-EN.md`。

复跑前置：`python -m pip install -r requirements.txt`（Python 3.11+）。

---

## AC1 · 虚构手机号 / 身份证 / 邮箱 / JWT / 口令样本全部被脱敏

**测试**
- `tests/test_masking.py::test_value_rules`（8 组参数）
- `tests/test_masking.py::test_ac1_all_sample_types_masked_in_one_payload`
- `tests/test_logging.py::test_msg_and_args_masked_before_serialization`
- `tests/test_logging.py::test_extra_payload_masked`

**命令与预期**

```bash
python -m pytest tests/test_masking.py tests/test_logging.py -q
# 预期：41 passed
```

**关键断言原文（tests/test_masking.py）**

```python
assert masked["phone"] == "138****8000"
assert masked["identity_no"] == "1" + "*" * 16 + "4"
assert masked["email"] == "z***@example.com"
assert masked["authorization"] == REDACTED
assert masked["password"] == REDACTED
for secret in (PHONE, ID_CARD, EMAIL, JWT, "P@ssw0rd!"):
    assert secret not in serialized
```

覆盖样本：11 位手机号、18 位身份证号、邮箱、三段 base64url JWT、口令；日志路径额外验证 `msg` + `args` 与 `extra` 字段在序列化前被改写。

---

## AC2 · 嵌套 dict 与 list 中的敏感键同样替换为 `[REDACTED]`

**测试**
- `tests/test_masking.py::test_ac2_nested_dict_and_list_redacted`
- `tests/test_masking.py::test_tuple_preserved`
- `tests/test_middleware.py::test_whitelisted_body_logged_and_masked`

**命令与预期**

```bash
python -m pytest tests/test_masking.py::test_ac2_nested_dict_and_list_redacted -q
# 预期：1 passed

python -m pytest tests/test_middleware.py::test_whitelisted_body_logged_and_masked -q
# 预期：1 passed
```

**关键断言原文**

```python
assert masked["outer"]["password"] == REDACTED
assert masked["outer"]["profile"]["access_token"] == REDACTED
assert masked["outer"]["items"][0]["secret"] == REDACTED
assert masked["outer"]["items"][1][1]["cookie"] == REDACTED
assert masked["list_top"][1]["bank_card"] == REDACTED
```

覆盖：三层 dict、list 内 dict、list 内 list、tuple；非敏感键与数字原样保留。

---

## AC3 · 单条日志脱敏耗时 < 0.2 毫秒（附输出）

**测试 / 脚本**
- `tests/test_benchmark.py::test_single_record_masking_under_limit`
- `bench/bench_masking.py`

**命令与预期**

```bash
python bench/bench_masking.py
# 预期：result : PASS (p95 < 0.2 ms)

python -m pytest tests/test_benchmark.py -q
# 预期：1 passed
```

**实测输出（artifacts/bench.txt，原样）**

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

**关键断言原文（tests/test_benchmark.py）**

```python
assert mean < LIMIT_MS, f"CPU 均值 {mean:.5f}ms 超过 {LIMIT_MS}ms"
assert p95 < LIMIT_MS, f"CPU P95 {p95:.5f}ms 超过 {LIMIT_MS}ms"
```

说明：单条计时受系统计时粒度（约 15.6ms）与并行进程调度影响，按 10 批 × 2000 条测量后摊薄，CPU 与墙钟均远低于 0.2ms。

---

## AC4 · 容器日志中不存在 uvicorn 默认格式的访问日志行

**证据一：真实容器内实测**

```bash
docker build -t clawhunt-3190 .
docker run -d --name ch3190 -p 127.0.0.1::8000 clawhunt-3190
docker port ch3190 8000/tcp
curl -s http://127.0.0.1:<映射端口>/health
curl -s http://127.0.0.1:<映射端口>/health
docker logs ch3190 > container.log 2>&1
python scripts/check_container_logs.py container.log
```

**实测结果（本次，artifacts/docker-evidence.txt）**

- 映射端口 `127.0.0.1:64482`，容器 `running`，`restarts=0`
- `docker logs` 共 7 行：3 条 JSON（1 条启动 + 2 条 `app.access`）+ 4 条 uvicorn 生命周期信息
- 校验输出（artifacts/docker-log-check.txt，原样）：

```text
container log check
lines=7
json_lines=3
access_log_json_lines=2
uvicorn_default_access_lines=0
PROBLEMS=0
RESULT: PASS
```

**证据二：自动化回归（进程级，CI 可跑）**

- `tests/test_no_uvicorn_access_log.py::test_no_uvicorn_default_access_log`

```bash
python -m pytest tests/test_no_uvicorn_access_log.py -q
# 预期：1 passed
```

用例真实启动 `python -m uvicorn app.main:app`（**故意不加** `--no-access-log`），请求 `/health` 两次，捕获 stdout 后断言。

**关键断言原文**

```python
offenders = [line for line in lines if DEFAULT_ACCESS_RE.search(line) or UVICORN_RAW_LINE_RE.search(line)]
assert offenders == [], f"发现 uvicorn 默认访问日志: {offenders}"
assert len(access_records) >= 2, output
assert record["route"] == "/health"
assert record["status"] == 200
```

`DEFAULT_ACCESS_RE` 匹配形如 `INFO:     127.0.0.1:xxxxx - "GET /health HTTP/1.1" 200 OK` 的默认行；`UVICORN_RAW_LINE_RE` 兜底匹配裸访问行。

---

## 全局证据

| 项 | 命令 | 预期 |
|---|---|---|
| 全量测试 | `python -m pytest -q` | `51 passed`，退出码 0 |
| 清单校验 | `python scripts/manifest.py verify` | `清单条目 39 / 匹配 39`、`PROBLEMS=0` |
| 容器日志断言 | `python scripts/check_container_logs.py artifacts/docker-evidence.txt` | `uvicorn_default_access_lines=0`、`PROBLEMS=0` |
| 密钥与隐私扫描 | `python scripts/secret_scan.py` | `PROBLEMS=0` |
| 干净副本 | 在临时目录解压/复制后重跑上述两条 | 同样 `PROBLEMS=0` |

清单由干净副本生成；仓库重新克隆后再校验一次，结果记录在 `TEST-REPORT.md`。
