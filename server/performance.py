"""Bounded, per-instance request and SQL timing; no user identifiers or query text."""
from __future__ import annotations

import os
import re
import statistics
import threading
import time
from collections import deque

_local = threading.local()
_guard = threading.Lock()
_samples = deque(maxlen=5000)


def begin_request() -> None:
    _local.queries = 0
    _local.db_ms = 0.0
    _local.sql_started = []


def before_sql(*_args) -> None:
    if hasattr(_local, "queries"):
        _local.sql_started.append(time.perf_counter())


def after_sql(*_args) -> None:
    if hasattr(_local, "queries") and _local.sql_started:
        _local.queries += 1
        _local.db_ms += (time.perf_counter() - _local.sql_started.pop()) * 1000


def route_key(path: str) -> str:
    clean = path.split("?", 1)[0][:160]
    clean = re.sub(r"/[0-9a-f]{32}(?=/|$)", "/:id", clean, flags=re.I)
    clean = re.sub(r"/(?:IB|PL|TBMT|KHLCNT)[A-Za-z0-9._-]{4,50}(?=/|$)", "/:code", clean, flags=re.I)
    return clean


def finish_request(method: str, path: str, status: int, elapsed_ms: float) -> dict:
    sample = {"method": method, "route": route_key(path), "status": int(status),
              "elapsed_ms": round(elapsed_ms, 2),
              "db_query_count": getattr(_local, "queries", 0),
              "db_duration_ms": round(getattr(_local, "db_ms", 0.0), 2),
              "at": time.time()}
    with _guard:
        _samples.append(sample)
    return sample


def snapshot() -> dict:
    with _guard:
        samples = list(_samples)
    def percentile(values: list[float], proportion: float) -> float:
        if not values:
            return 0.0
        values.sort()
        return round(values[min(len(values) - 1, int(proportion * (len(values) - 1)))], 2)
    routes = {}
    for item in samples:
        key = item["method"] + " " + item["route"]
        routes.setdefault(key, []).append(item)
    top = []
    for key, rows in routes.items():
        times = [row["elapsed_ms"] for row in rows]
        top.append({"route": key, "count": len(rows),
                    "p50_ms": round(statistics.median(times), 2),
                    "p95_ms": percentile(times, .95),
                    "db_query_avg": round(sum(row["db_query_count"] for row in rows) / len(rows), 1),
                    "errors_5xx": sum(row["status"] >= 500 for row in rows)})
    top.sort(key=lambda row: (-row["p95_ms"], -row["count"]))
    from sqlalchemy import func, select
    from server.database import background_jobs, get_db
    db = get_db()
    with db.engine.connect() as conn:
        queue_length = conn.scalar(select(func.count()).select_from(background_jobs).where(
            background_jobs.c.status.in_(("pending", "queued", "retry")))) or 0
    return {"scope": "this_instance", "request_count": len(samples),
            "error_count_5xx": sum(item["status"] >= 500 for item in samples),
            "p50_ms": round(statistics.median([item["elapsed_ms"] for item in samples]), 2) if samples else 0,
            "p95_ms": percentile([item["elapsed_ms"] for item in samples], .95),
            "queue_length": queue_length, "db_pool": db.engine.pool.status(),
            "routes": top[:20]}


def slow_request_ms() -> int:
    try:
        return max(100, min(int(os.environ.get("SLOW_REQUEST_MS", "1000")), 60000))
    except ValueError:
        return 1000
