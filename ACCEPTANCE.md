# 工单 3190 验收对照表

被测对象：本仓库根目录
工单原文：`docs/3190-requirement-original.md`、`docs/problem-3190.json`（需求正文与 AC 逐字保留；平台侧投标/提交者/内部仓库等字段已剔除）

命令默认在项目根目录执行；`python` 为本机 Python 3.14.3，依赖已装（见 README）。

## 一、AC 逐条对照

| # | 验收标准（原文要点） | 实现位置 | 证明方式（可复跑命令 + 预期输出） | 结论 |
|---|---|---|---|---|
| AC1 | pytest 用虚构的手机号、身份证号、邮箱、JWT、口令样本断言输出全部被脱敏 | [masking.py](app/core/masking.py#L130-L192) 值规则与递归；[logging.py](app/core/logging.py#L70-L90) `MaskingFilter` 在序列化前改写 LogRecord | `python -m pytest tests/test_masking.py tests/test_logging.py -q`<br>预期：`41 passed`，包含 `test_ac1_all_sample_types_masked_in_one_payload`、`test_msg_and_args_masked_before_serialization` | 达成 |
| AC2 | 嵌套 dict 与 list 中的敏感键同样被替换为 `[REDACTED]`（测试断言） | [masking.py](app/core/masking.py#L175-L192) `mask_payload` 递归；[masking.py](app/core/masking.py#L92-L100) 键名判定 | `python -m pytest tests/test_masking.py::test_ac2_nested_dict_and_list_redacted -q`<br>预期：`1 passed`；再跑 `tests/test_middleware.py::test_whitelisted_body_logged_and_masked` 验证日志路径 | 达成 |
| AC3 | 基准测试显示单条日志脱敏耗时 < 0.2 毫秒（附输出） | [logging.py](app/core/logging.py#L159-L163) `mask_record`；基准脚本 [bench_masking.py](bench/bench_masking.py) | `python bench/bench_masking.py`<br>预期：`cpu mean≈0.027ms / p95≈0.047ms`，`result : PASS`；`python -m pytest tests/test_benchmark.py -q` 预期 `1 passed` | 达成 |
| AC4 | 容器日志中不存在 uvicorn 默认格式的访问日志行 | [logging.py](app/core/logging.py#L121-L152) 关闭 `uvicorn.access`；[middleware.py](app/core/middleware.py#L47-L124) 统一输出 JSON 访问日志 | **容器内实测**：`docker build` → `docker run` → 请求 `/health` 两次 → `docker logs`（`artifacts/docker-evidence.txt`）。断言命令 `python scripts/check_container_logs.py artifacts/docker-evidence.txt`，预期 `uvicorn_default_access_lines=0`、`access_log_json_lines=2`、`PROBLEMS=0`。另有进程级回归 `python -m pytest tests/test_no_uvicorn_access_log.py -q`，预期 `1 passed` | 达成（容器内实测） |

### AC4 容器实测记录

- 环境：Docker Desktop 29.9.2（Windows + WSL2），基础镜像 `python:3.11-slim`，镜像内不加 `--no-access-log`。
- 执行：`docker build` → `docker run -d --name ch3190-review -p 127.0.0.1::8000` → 请求 `/health` 两次 → `docker logs` → `docker rm -f`。
- 实测映射端口 `127.0.0.1:64482`；容器 `running`，`restarts=0`。
- `docker logs` 共 7 行：3 条 JSON（1 条启动 + 2 条 `app.access`）+ 4 条 uvicorn 生命周期信息；**uvicorn 默认访问日志 0 条**。
- 断言结果：`uvicorn_default_access_lines=0`、`PROBLEMS=0`、`RESULT: PASS`（`artifacts/docker-log-check.txt`）。

复跑命令（任意有 Docker 的环境）：

```bash
docker build -t clawhunt-3190 .
docker run -d --name ch3190 -p 127.0.0.1::8000 clawhunt-3190
docker port ch3190 8000/tcp          # 取映射到主机的端口
curl -s http://127.0.0.1:<映射端口>/health
curl -s http://127.0.0.1:<映射端口>/health
docker logs ch3190 > container.log 2>&1
python scripts/check_container_logs.py container.log
docker rm -f ch3190
```

预期 `uvicorn_default_access_lines=0`，且 `access_log_json_lines>=2`。

## 二、本单范围条目核对（非 AC，但属交付要求）

| 范围要求 | 实现位置 | 证明 |
|---|---|---|
| 单行 JSON 输出到 stdout | [logging.py](app/core/logging.py#L92-L118) `JsonFormatter`（`separators=(",",":")`） | `tests/test_logging.py::test_output_is_single_line_json_with_all_fields`、`test_stdout_json_is_not_pretty_printed` |
| 12 个固定字段 ts/level/logger/msg/request_id/org_id/site_id/user_id/route/status/duration_ms/env | `JsonFormatter` 字段表；README 字段表 | 同上用例逐字段断言 |
| 脱敏在序列化之前执行 | `MaskingFilter`（handler 级过滤器，Formatter 之前执行） | `tests/test_logging.py::test_extra_payload_masked` |
| request_id 生成或沿用 `X-Request-ID` 并回写响应头 | [middleware.py](app/core/middleware.py#L62-L100) | `tests/test_middleware.py::test_request_id_echoed_from_header`、`test_request_id_generated_when_absent` |
| 键名规则 12 个敏感词 + 递归 | [masking.py](app/core/masking.py#L28-L60) 规则表 | `tests/test_masking.py::test_sensitive_key_detection`（16 个参数） |
| 值规则：手机号/身份证/邮箱/JWT/银行卡 | [masking.py](app/core/masking.py#L130-L160) | `tests/test_masking.py::test_value_rules`（8 个参数） |
| 请求体/响应体默认不记录；白名单接口记录且同样脱敏 | [middleware.py](app/core/middleware.py#L100-L125)；白名单解析 [masking.py](app/core/masking.py#L210-L232) | `tests/test_middleware.py::test_body_not_logged_by_default`、`test_whitelisted_body_logged_and_masked`、`test_path_prefix_whitelist` |
| 关闭 uvicorn 默认访问日志 | `configure_logging` | `tests/test_no_uvicorn_access_log.py` |
| README 字段表与规则表 | `README.md` | 人工核对 |

## 三、口径说明（可能被验收方追问的三处）

1. **18 位数字串优先按身份证处理**（保留首尾各 1 位）；银行卡取 12–17、19–20 位（保留后 4 位）。需求同时点名两者但位数可能重叠，这里选「18 位=身份证」的确定性口径，避免同一条规则互相吞掉。
2. **键名按「整键或按 `_`/`-` 切段」命中**，因此 `access_token`、`password_hash`、`token_type` 都会被命中；不会因为多了后缀而漏脱敏。
3. **`id_card`、`bank_card` 这类键名命中时整值替换为 `[REDACTED]`**，不再按值规则保留首尾；值规则只作用于键名未命中的字符串。两种路径都满足「不落明文」。

## 四、未执行项

- 未投标、未调用平台提交接口。
- 未安装任何付费组件；测试只依赖 fastapi/uvicorn/pytest/httpx。
- 容器做了本地构建与运行取证，但镜像未推送到任何 registry。
- 仓库已推送到 GitHub 公开仓，未使用 force push。
