# Acceptance Criteria and Evidence (English)

Problem 3190 (S2-INFRA-026): structured logging with pre-persistence masking.
Chinese version: `ACCEPTANCE-EVIDENCE.md` (same AC numbering).
Original requirement and AC text: `docs/3190-requirement-original.md`, `docs/problem-3190.json`.

Prerequisite: `python -m pip install -r requirements.txt` (Python 3.11+).

---

## AC1

**AC (English, sentence by sentence)**
- Using fictional mobile phone numbers, ID card numbers, email addresses, JWT strings and password samples in pytest, assert that every one of them is masked in the output.

**Test**
- `tests/test_masking.py::test_value_rules`
- `tests/test_masking.py::test_ac1_all_sample_types_masked_in_one_payload`
- `tests/test_logging.py::test_msg_and_args_masked_before_serialization`
- `tests/test_logging.py::test_extra_payload_masked`

**Command**

```bash
python -m pytest tests/test_masking.py tests/test_logging.py -q
```

**Expected output**

```text
41 passed
```

**Actual result**
- 41 passed, exit code 0.
- Masked forms: phone `138****8000`, ID `1****************4`, email `z***@example.com`, JWT `[JWT]`, password and `authorization` `[REDACTED]`.
- Assertion also checks that no raw sample value appears anywhere in the serialized record.

---

## AC2

**AC (English, sentence by sentence)**
- Sensitive keys inside nested dicts and lists are also replaced with `[REDACTED]`, asserted by tests.

**Test**
- `tests/test_masking.py::test_ac2_nested_dict_and_list_redacted`
- `tests/test_masking.py::test_tuple_preserved`
- `tests/test_middleware.py::test_whitelisted_body_logged_and_masked`

**Command**

```bash
python -m pytest tests/test_masking.py::test_ac2_nested_dict_and_list_redacted -q
python -m pytest tests/test_middleware.py::test_whitelisted_body_logged_and_masked -q
```

**Expected output**

```text
1 passed
1 passed
```

**Actual result**
- 1 passed and 1 passed, exit code 0.
- Covered shapes: three-level dict, dict inside list, list inside list, tuple; non-sensitive keys and numbers stay unchanged.

---

## AC3

**AC (English, sentence by sentence)**
- The benchmark shows that masking a single log record takes less than 0.2 milliseconds, with output attached.

**Test / script**
- `tests/test_benchmark.py::test_single_record_masking_under_limit`
- `bench/bench_masking.py`

**Command**

```bash
python bench/bench_masking.py
python -m pytest tests/test_benchmark.py -q
```

**Expected output**

```text
result         : PASS (cpu mean < 0.2 ms and cpu p95 < 0.2 ms)
1 passed
```

**Actual result (artifacts/bench.txt, verbatim)**

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

Measurement note: OS timer granularity (about 15.6 ms) and scheduler noise make single-call timings unreliable, so the benchmark measures batches of 2000 records and divides by batch size. CPU mean 0.0266 ms and p95 0.0469 ms are both far below the 0.2 ms limit.

---

## AC4

**AC (English, sentence by sentence)**
- Container logs contain no uvicorn default-format access log lines.

**Evidence 1: real container run**

```bash
docker build -t clawhunt-3190 .
docker run -d --name ch3190 -p 127.0.0.1::8000 clawhunt-3190
docker port ch3190 8000/tcp
curl -s http://127.0.0.1:<mapped-port>/health
curl -s http://127.0.0.1:<mapped-port>/health
docker logs ch3190 > container.log 2>&1
python scripts/check_container_logs.py container.log
docker rm -f ch3190
```

**Expected output**

```text
uvicorn_default_access_lines=0
PROBLEMS=0
RESULT: PASS
```

**Actual result (artifacts/docker-log-check.txt, verbatim)**

```text
container log check
lines=7
json_lines=3
access_log_json_lines=2
uvicorn_default_access_lines=0
PROBLEMS=0
RESULT: PASS
```

Environment: Docker Desktop 29.9.2 (Windows + WSL2), base image `python:3.11-slim`, container started without `--no-access-log`. Mapped port `127.0.0.1:64482`, container state `running`, `restarts=0`. The 7 log lines are 3 JSON records (1 startup + 2 `app.access`) plus 4 uvicorn lifecycle lines; no default access line.

**Evidence 2: automated regression test (process level, CI friendly)**

```bash
python -m pytest tests/test_no_uvicorn_access_log.py -q
```

**Expected output**

```text
1 passed
```

**Actual result**
- 1 passed, exit code 0.
- The test starts a real uvicorn process without `--no-access-log`, sends two `/health` requests, captures stdout, and asserts zero default access lines and at least two `app.access` JSON records.

---

## Global evidence

| Item | Command | Expected |
|---|---|---|
| Full test suite | `python -m pytest -q` | `51 passed`, exit code 0 |
| Manifest verification | `python scripts/manifest.py verify` | `PROBLEMS=0`, `RESULT: PASS` |
| Secret and privacy scan | `python scripts/secret_scan.py` | `PROBLEMS=0` |
| Clean copy | Copy to a temp directory, rerun the two checks above | `PROBLEMS=0` both |

The manifest is generated in a clean copy of the repository and re-verified in a fresh clone; see `TEST-REPORT.md`.
