# ClawHunt #3190 · 结构化日志与落盘前脱敏过滤器

FastAPI 统一结构化日志：单行 JSON 输出到 stdout，**脱敏在序列化之前完成**，访问日志由本中间件统一产出并关闭 uvicorn 默认访问日志。

- Python 3.11+（本机实测 3.14.3）
- 依赖：FastAPI、uvicorn；测试：pytest、httpx
- 无任何向境外发送数据的 SDK

## 1. 安装

```bash
cd clawhunt-3190-log-masking
python -m pip install -r requirements.txt
```

## 2. 运行

```bash
# 开发/验收：不传 --no-access-log，验证默认访问日志确实被应用关闭
python -m uvicorn app.main:app --host 127.0.0.1 --port 8090

# 冒烟
curl -s http://127.0.0.1:8090/health
curl -s -X POST http://127.0.0.1:8090/api/echo \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: demo-1' \
  -d '{"phone":"13800138000","password":"P@ssw0rd!"}'
```

stdout 每行一条 JSON。启动后访问 `/health`，输出示例（节选）：

```json
{"ts":"2026-11-23T12:00:00.123Z","level":"INFO","logger":"app.access","msg":"GET /health","request_id":"demo-1","org_id":null,"site_id":null,"user_id":null,"route":"/health","status":200,"duration_ms":1.234,"env":"dev"}
```

> 端口纪律：启动监听服务前先查本机端口登记与占用；示例端口 8090 属开发候选区间，使用前请自查。

## 3. 验证

```bash
python -m pytest -q                      # 51 用例，含真实 uvicorn 子进程集成用例
python -m pytest tests/test_masking.py -q
python -m pytest tests/test_no_uvicorn_access_log.py -q
python bench/bench_masking.py            # AC3 基准输出
```

预期结果见 [TEST-REPORT.md](TEST-REPORT.md) 与 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 4. 字段表

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts` | string | ISO 8601，UTC，毫秒精度，`Z` 结尾 |
| `level` | string | 日志级别，如 `INFO` |
| `logger` | string | 日志器名，访问日志为 `app.access` |
| `msg` | string | 消息正文（已脱敏） |
| `request_id` | string | 中间件生成 UUID，或沿用请求头 `X-Request-ID` |
| `org_id` | string/null | 组织 UUID，来自请求头 `X-Org-Id`（非法值置 null） |
| `site_id` | string/null | 站点 UUID，来自 `X-Site-Id` |
| `user_id` | string/null | 内部用户 UUID，来自 `X-User-Id`；**不记录姓名** |
| `route` | string | 路由路径（优先取匹配到的路由模板，否则取原始 path） |
| `status` | int/null | HTTP 状态码；非请求日志为 null |
| `duration_ms` | float/null | 处理耗时（毫秒，3 位小数） |
| `env` | string | 运行环境，来自 `APP_ENV`，默认 `dev` |

扩展字段（如白名单命中的 `request_body`、`response_body`）追加在固定字段之后，同样先脱敏。

## 5. 脱敏规则表

### 5.1 键名规则（命中即整值替换为 `[REDACTED]`）

| 类别 | 命中键名 |
|---|---|
| 口令 | `password`、`passwd` |
| 密钥/凭证 | `secret`、`token`、`access_token`、`refresh_token`、`authorization`、`cookie` |
| 验证码 | `totp`、`otp`、`otp_code` |
| 证件/卡 | `id_card`、`bank_card` |

判定口径：键名小写后**整键命中**，或按非字母数字切段后**任一段命中**。因此 `access_token`、`password_hash`、`token_type` 都会命中。`dict`/`list` 递归处理。

### 5.2 值规则（键名未命中时，对字符串值执行）

| 类型 | 形态 | 输出 |
|---|---|---|
| JWT | 三段 base64url（`.` 分隔，每段 ≥8 字符） | 整体替换 `[JWT]` |
| 邮箱 | `user@example.com` | 保留首字符与域名：`z***@example.com` |
| 身份证 | 18 位（末位可为 `X`） | 保留首尾各 1 位：`1****************4` |
| 银行卡 | 12–17 位、19–20 位数字 | 保留后 4 位：`************7890` |
| 手机号 | 11 位、`1[3-9]` 开头 | 前 3 后 4，中间 `****`：`138****8000` |

执行顺序：JWT → 邮箱 → 身份证 → 银行卡 → 手机号。18 位纯数字优先按身份证口径处理（需求同时点名两类的边界选择），已写入 [ACCEPTANCE.md](ACCEPTANCE.md)。

### 5.3 规则覆盖

`MASKING_RULES_PATH` 指向 JSON 文件可覆盖键名表与标记：

```json
{"sensitive_keys": ["password", "token", "my_custom_secret"], "redacted_marker": "[REDACTED]", "jwt_marker": "[JWT]"}
```

## 6. 配置（全部来自环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_ENV` | `dev` | 写入每条日志的 `env` 字段 |
| `LOG_LEVEL` | `INFO` | 根日志器级别 |
| `LOG_BODY_WHITELIST` | 空 | 记录请求/响应体的路径，逗号分隔；`/api/orders/*` 为前缀匹配 |
| `LOG_MAX_BODY_BYTES` | `65536` | 超过则不记录正文，输出 `[BODY_TOO_LARGE:n]` |
| `MASKING_RULES_PATH` | 空 | 自定义脱敏规则 JSON |

请求/响应体默认**不记录**；只有白名单路径记录，且同样经过脱敏。

## 7. 为什么用 `logging.Filter` 而不是 structlog

- 需求允许二选一。选 stdlib 的理由：**零第三方依赖**，私有化部署时依赖面小、审计简单。
- `Filter` 挂在 handler 上，在 `Formatter` 序列化**之前**改写 LogRecord，天然满足「落盘前脱敏」，不存在「先写后洗」的窗口。
- 注意点：logger 级 filter 不会作用于子 logger 传播上来的记录，因此过滤器同时挂在 handler 上（见 `configure_logging`）。

## 8. uvicorn 默认访问日志

`configure_logging()` 在应用启动时执行：

```python
uvicorn_access = logging.getLogger("uvicorn.access")
uvicorn_access.handlers.clear()
uvicorn_access.propagate = False
uvicorn_access.disabled = True
```

因此即使启动命令**不带** `--no-access-log`，也不会出现 `INFO: 127.0.0.1:xxxxx - "GET /path HTTP/1.1" 200 OK` 这类未脱敏行；访问日志只有 `logger=app.access` 的 JSON。

## 9. 容器

```bash
docker build -t clawhunt-3190 .
docker run --rm -d --name ch3190 -p 127.0.0.1::8000 clawhunt-3190
docker port ch3190            # 取映射到主机的端口
curl -s http://127.0.0.1:<映射端口>/health
docker logs ch3190            # 断言：无 uvicorn 默认访问日志行，只有 JSON
```

> 若需固定主机端口，先登记端口再绑定。本次交付未在本机实跑容器（Docker daemon 未运行），进程级取证见 ACCEPTANCE.md。

## 10. 目录

```
app/core/logging.py      统一日志装配、JSON Formatter、脱敏 Filter、字段表
app/core/masking.py      脱敏规则（键名表 + 值规则 + 递归 + 白名单解析）
app/core/middleware.py   请求日志中间件（X-Request-ID、耗时、状态、白名单正文）
app/core/config.py       环境变量配置
app/main.py              可运行装配与示例路由（只用于验证日志行为）
tests/                   单元测试 + 集成测试（真实 uvicorn 子进程）
bench/bench_masking.py   脱敏耗时基准（AC3）
scripts/fetch_requirement.py  工单原文抓取（复跑用，凭据只读环境变量）
docs/                    工单原文与脱敏后的接口元数据
ACCEPTANCE.md            AC 对照表
ACCEPTANCE-EVIDENCE.md   逐条 AC 与证据（测试名、命令、预期输出、断言原文）
TEST-REPORT.md           测试与基准实测输出
MANIFEST.sha256          SHA256 清单
```
