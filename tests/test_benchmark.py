"""基准测试（AC3）：单条日志脱敏耗时 < 0.2 毫秒。

口径：按批测量 CPU 时间再除以批内条数。原因：
- Windows 计时粒度约 15.6ms，单条计时会大量读成 0，必须按批摊薄；
- 墙钟会被并行进程与系统调度放大，CPU 时间反映脱敏本身的计算成本。
门禁：CPU 每条均值与 P95 均 < 0.2ms；墙钟均值只作观测输出。
"""

from __future__ import annotations

import statistics
import time

from app.core.logging import mask_record

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

LIMIT_MS = 0.2
BATCHES = 10
PER_BATCH = 2000


def measure() -> tuple[list[float], list[float]]:
    """返回每个批次的「单条平均耗时」（毫秒），分别为 CPU 与墙钟。"""

    cpu: list[float] = []
    wall: list[float] = []
    for _ in range(BATCHES):
        start_cpu = time.process_time_ns()
        start_wall = time.perf_counter_ns()
        for _ in range(PER_BATCH):
            mask_record(SAMPLE)
        cpu.append(((time.process_time_ns() - start_cpu) / 1_000_000) / PER_BATCH)
        wall.append(((time.perf_counter_ns() - start_wall) / 1_000_000) / PER_BATCH)
    return cpu, wall


def test_single_record_masking_under_limit() -> None:
    for _ in range(300):  # 预热
        mask_record(SAMPLE)
    cpu, wall = measure()
    cpu_sorted = sorted(cpu)
    mean = statistics.fmean(cpu_sorted)
    p95 = cpu_sorted[int(len(cpu_sorted) * 0.95)]

    print(
        f"\n[masking benchmark] batches={BATCHES}x{PER_BATCH} "
        f"cpu_mean={mean:.5f}ms cpu_p95={p95:.5f}ms "
        f"wall_mean={statistics.fmean(wall):.5f}ms limit={LIMIT_MS}ms"
    )

    assert mean < LIMIT_MS, f"CPU 均值 {mean:.5f}ms 超过 {LIMIT_MS}ms"
    assert p95 < LIMIT_MS, f"CPU P95 {p95:.5f}ms 超过 {LIMIT_MS}ms"
