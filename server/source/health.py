"""Rolling source health metrics with persisted status transitions."""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass

from sqlalchemy import insert


@dataclass(slots=True)
class HealthSample:
    at: float
    success: bool
    latency_ms: float
    error_code: str = ""
    cache_hit: bool = False
    dedup_wait: bool = False


class SourceHealthMonitor:
    def __init__(self, source: str = "egp-public", max_samples: int = 200):
        self.source = source
        self._samples: deque[HealthSample] = deque(maxlen=max_samples)
        self._status = "Healthy"
        self._lock = threading.RLock()

    def record(self, *, success: bool, latency_ms: float, error_code: str = "",
               cache_hit: bool = False, dedup_wait: bool = False) -> None:
        with self._lock:
            old = self._status
            self._samples.append(HealthSample(time.time(), success, latency_ms,
                                              error_code, cache_hit, dedup_wait))
            self._status = self._calculate_status()
            new = self._status
        if new != old:
            self._persist_transition(old, new, error_code)

    def _calculate_status(self) -> str:
        recent = list(self._samples)[-20:]
        if len(recent) < 3:
            return "Healthy"
        failures = sum(not item.success for item in recent)
        consecutive = 0
        for item in reversed(recent):
            if item.success:
                break
            consecutive += 1
        if consecutive >= 5 or failures / len(recent) >= .7:
            return "Unavailable"
        if failures / len(recent) >= .25:
            return "Degraded"
        return "Healthy"

    def _persist_transition(self, old: str, new: str, error_code: str) -> None:
        try:
            from server.database import get_db, now, source_health_events
            with get_db().engine.begin() as conn:
                conn.execute(insert(source_health_events).values(
                    id=uuid.uuid4().hex, source_name=self.source,
                    event_type="status_transition", status=new,
                    details_json={"from": old, "to": new,
                                  "error_code": error_code}, created_at=now()))
        except Exception:
            # Health instrumentation must never make a source request fail.
            return

    def snapshot(self) -> dict:
        with self._lock:
            samples = list(self._samples)
            status = self._status
        count = len(samples)
        latencies = sorted(item.latency_ms for item in samples)
        successes = sum(item.success for item in samples)
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * .95))] if latencies else 0
        by_error = lambda code: sum(item.error_code == code for item in samples)
        return {"source": self.source, "status": status, "request_count": count,
                "success_count": successes, "failure_count": count - successes,
                "success_rate": round(successes * 100 / count, 1) if count else 100.0,
                "average_latency_ms": round(sum(latencies) / count, 1) if count else 0,
                "p95_latency_ms": round(p95, 1), "rate_limit_count": by_error("rate_limit"),
                "forbidden_count": by_error("forbidden"),
                "server_error_count": by_error("server"),
                "timeout_count": by_error("timeout"),
                "invalid_response_count": sum(item.error_code in
                    {"invalid_response", "invalid_json", "schema_changed"} for item in samples),
                "cache_hits": sum(item.cache_hit for item in samples),
                "dedup_waits": sum(item.dedup_wait for item in samples)}


SOURCE_HEALTH = SourceHealthMonitor()
