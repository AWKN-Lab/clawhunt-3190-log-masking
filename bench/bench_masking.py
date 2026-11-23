"""基准测试脚本（AC3 证据）：打印单条日志脱敏耗时统计。

按批测量（10 批 × 2000 条）后除以批内条数，得到每条平均耗时。
CPU 时间作为门禁（不受并行进程调度放大），墙钟作为观测参考。
判定：CPU 每条均值与 P95 均 < 0.2ms。

用法：python bench/bench_masking.py
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import mask_record  # noqa: E402

SAMPLE = {
    "ts": "2026-11-23T12:00:00.123Z",
    "level": "INFO",
    "logger": "app.access",
    "msg": "POST /api/orders 用户 13800138000 下单",
    "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "org_id": "f47ac10b-58cc-4372-a567-0e02b2c3d480",
    "site_id": "f47ac10b-58cc-4372-a567-0e02b2c3d481",
    "user_id": "f47ac10b-58cc-4372-a567-0e02b2c3d482",
    "route": "/api/orders",
    "status": 201,
    "duration_ms": 12.345,
    "env": "prod",
    "payload": {
        "phone": "13800138000",
        "id_card": "110101199003071234",
        "email": "zhangsan@example.com",
        "password": "P@ssw0rd!",
        "headers": {"authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlX2hlcmU"},
        "items": [{"bank_card": "6222021234567890", "qty": 2}],
    },
}

BATCHES = 10
PER_BATCH = 2000


def _summary(samples: list[float]) -> tuple[float, float, float]:
    samples = sorted(samples)
    return (
        statistics.fmean(samples),
        samples[len(samples) // 2],
        samples[int(len(samples) * 0.95)],
    )


def main() -> int:
    for _ in range(300):
        mask_record(SAMPLE)

    wall: list[float] = []
    cpu: list[float] = []
    for _ in range(BATCHES):
        start_wall = time.perf_counter_ns()
        start_cpu = time.process_time_ns()
        for _ in range(PER_BATCH):
            mask_record(SAMPLE)
        wall.append(((time.perf_counter_ns() - start_wall) / 1_000_000) / PER_BATCH)
        cpu.append(((time.process_time_ns() - start_cpu) / 1_000_000) / PER_BATCH)

    wall_mean, wall_p50, wall_p95 = _summary(wall)
    cpu_mean, cpu_p50, cpu_p95 = _summary(cpu)

    print("masking benchmark (single log record, masking only)")
    print(f"batches        : {BATCHES} x {PER_BATCH}")
    print(f"wall mean      : {wall_mean:.5f} ms")
    print(f"wall p50       : {wall_p50:.5f} ms")
    print(f"wall p95       : {wall_p95:.5f} ms")
    print(f"cpu  mean      : {cpu_mean:.5f} ms")
    print(f"cpu  p50       : {cpu_p50:.5f} ms")
    print(f"cpu  p95       : {cpu_p95:.5f} ms")
    print("limit          : 0.20000 ms")

    ok = cpu_mean < 0.2 and cpu_p95 < 0.2
    print(f"result         : {'PASS' if ok else 'FAIL'} (cpu mean < 0.2 ms and cpu p95 < 0.2 ms)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
