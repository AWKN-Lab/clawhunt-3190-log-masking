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
| AC4 | 容器日志中不存在 uvicorn 默认格式的访问日志行 | [logging.py](app/core/logging.py#L121-L152) 关闭 `uvicorn.access`；[middleware.py](app/core/middleware.py#L47-L124) 统一输出 JSON 访问日志 | `python -m pytest tests/test_no_uvicorn_access_log.py -q`<br>该用例真实拉起 `uvicorn app.main:app`（**故意不加** `--no-access-log`），抓 stdout。<br>预期：`1 passed`，断言 `offenders==[]` 且至少 2 条 `"logger":"app.access"` 的 JSON 行 | 达成（进程级实跑取证）；容器内实跑未做，原因见下 |

### AC4 的诚实边界

本机 Docker daemon 未运行（`docker version` 报 `cannot find npipe dockerDesktopLinuxEngine`），本轮未启动 Docker Desktop，也没有拉任何镜像。
因此 AC4 的取证方式是：**真实 uvicorn 进程** + 捕获 stdout，证明默认访问日志被代码关闭、只剩中间件 JSON 行。容器只是把同一个 stdout 交给日志驱动，日志内容一致。
已附 [Dockerfile](Dockerfile) 供有 Docker 的环境复跑：

```bash
docker build -t clawhunt-3190 .
docker run --rm -d --name ch3190 -p 127.0.0.1::8000 clawhunt-3190
curl -s http://127.0.0.1:<映射端口>/health
docker logs ch3190
```

预期 `docker logs` 中没有任何 `INFO:     127.0.0.1:xxxxx - "GET /health HTTP/1.1" 200 OK` 行。

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

- 未投标、未调平台提交接口、未 push、未碰 GitHub（硬约束）。
- 未安装任何付费组件；测试只依赖本机已有的 fastapi/uvicorn/pytest/httpx。
- Docker 容器实跑未做（daemon 未运行），替代取证见 AC4 说明。
