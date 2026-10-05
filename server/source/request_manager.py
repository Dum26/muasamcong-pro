"""Shared HTTP reliability layer: retry, throttle, cache, dedup and circuit breaker."""
from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests
from sqlalchemy import func, select, update

from server.config import production, source_settings
from server.source.cache import MemoryTTLCache
from server.source.errors import (BadRequestError, CircuitOpenError, ForbiddenError, InvalidJsonError,
    InvalidResponseError, NotFoundError, RateLimitError, ServerError,
    SourceConnectionError, SourceError, SourceTimeoutError)
from server.source.health import SOURCE_HEALTH
from server.source.models import SourceResult


def cache_key(operation: str, payload: Any) -> str:
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), default=str)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{operation}:{digest}"


class SourceRequestManager:
    def __init__(self, session: requests.Session | None = None, *, sleeper=time.sleep,
                 clock=time.monotonic, rng=random.random):
        self.settings = source_settings()
        self.session = session or requests.Session()
        self.cache = MemoryTTLCache()
        self._sleep, self._clock, self._rng = sleeper, clock, rng
        self._rate_lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._last_request = 0.0
        self._flight_lock = threading.Lock()
        self._flights: dict[str, threading.Event] = {}
        self._circuit_lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_busy = False
        self.request_count = self.cache_hits = self.dedup_waits = 0

    def _circuit_enter(self) -> None:
        with self._circuit_lock:
            if self._opened_at is None:
                return
            elapsed = self._clock() - self._opened_at
            if elapsed < self.settings["circuit_cooldown_seconds"]:
                raise CircuitOpenError("Nguồn dữ liệu đang tạm ngắt để phục hồi.")
            if self._half_open_busy:
                raise CircuitOpenError("Nguồn dữ liệu đang được kiểm tra phục hồi.")
            self._half_open_busy = True

    def _circuit_result(self, success: bool) -> None:
        with self._circuit_lock:
            if success:
                self._failures, self._opened_at, self._half_open_busy = 0, None, False
                return
            self._half_open_busy = False
            self._failures += 1
            if self._failures >= self.settings["circuit_failure_threshold"]:
                self._opened_at = self._clock()

    def circuit_status(self) -> str:
        with self._circuit_lock:
            if self._opened_at is None:
                return "CLOSED"
            if self._clock() - self._opened_at >= self.settings["circuit_cooldown_seconds"]:
                return "HALF_OPEN"
            return "OPEN"

    def _throttle(self) -> None:
        interval = 1.0 / self.settings["requests_per_second"]
        if production():
            # PostgreSQL row locking allocates one source-wide time slot per
            # request across all Cloud Run instances. Sleep after commit so a
            # waiting worker does not hold the database lock.
            from server.data_sync import DEFAULT_SOURCE_ID, ensure_default_source
            from server.database import get_db, sync_sources
            ensure_default_source()
            with get_db().engine.begin() as conn:
                db_now = conn.scalar(select(func.now()))
                if db_now.tzinfo is None:
                    db_now = db_now.replace(tzinfo=timezone.utc)
                raw = conn.execute(select(sync_sources.c.next_request_at).where(
                    sync_sources.c.id == DEFAULT_SOURCE_ID).with_for_update()).scalar_one()
                reserved = datetime.fromisoformat(raw) if raw else db_now
                if reserved.tzinfo is None:
                    reserved = reserved.replace(tzinfo=timezone.utc)
                slot = max(db_now, reserved)
                conn.execute(update(sync_sources).where(
                    sync_sources.c.id == DEFAULT_SOURCE_ID).values(
                    next_request_at=(slot + timedelta(seconds=interval)).isoformat()))
            delay = max(0.0, (slot - db_now).total_seconds())
            if delay:
                self._sleep(delay)
            return
        with self._rate_lock:
            wait = interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
            self._last_request = self._clock()

    @staticmethod
    def _retry_after(response) -> float | None:
        raw = response.headers.get("Retry-After", "").strip()
        if not raw:
            return None
        try:
            return max(0.0, min(float(raw), 120.0))
        except ValueError:
            try:
                return max(0.0, min((parsedate_to_datetime(raw).timestamp() - time.time()), 120.0))
            except (TypeError, ValueError, OverflowError):
                return None

    @staticmethod
    def _classify(response) -> SourceError | None:
        status = response.status_code
        if 200 <= status < 300:
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and "json" not in content_type:
                return InvalidResponseError("Nguồn dữ liệu không trả nội dung JSON.")
            return None
        if status == 429:
            return RateLimitError("Nguồn dữ liệu đang giới hạn tần suất truy cập.")
        if status in {401, 403}:
            return ForbiddenError("Nguồn dữ liệu từ chối truy cập.")
        if status == 404:
            return NotFoundError("Không tìm thấy dữ liệu trên nguồn.")
        if status == 400:
            return BadRequestError("Nguồn dữ liệu từ chối tham số truy vấn.")
        if status in {500, 502, 503, 504}:
            return ServerError(f"Nguồn dữ liệu lỗi HTTP {status}.")
        return SourceError(f"Nguồn dữ liệu trả HTTP {status}.")

    def request_binary(self, url: str, *, max_bytes: int,
                       timeout: int | None = None) -> tuple[bytes, str]:
        """Bounded explicit file fetch sharing the source throttle and circuit.

        Redirects are rejected: discovery already supplies an approved final
        e-GP URL, and following one could escape the source allowlist.
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "muasamcong.mpi.gov.vn" \
                or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("Đường dẫn tài liệu nguồn không hợp lệ.")
        limit = max(1, int(max_bytes))
        request_timeout = max(2, min(int(timeout or self.settings["timeout_seconds"]), 120))
        self._circuit_enter()
        try:
            for attempt in range(self.settings["max_retries"] + 1):
                self._throttle()
                self.request_count += 1
                try:
                    with self._session_lock:
                        response = self.session.request("GET", url, stream=True,
                            allow_redirects=False, timeout=(min(10, request_timeout), request_timeout))
                    try:
                        if response.status_code in {429, 500, 502, 503, 504}:
                            if attempt < self.settings["max_retries"]:
                                self._sleep(min(2 ** attempt, 8))
                                continue
                            raise ServerError(f"Nguồn file trả HTTP {response.status_code}.")
                        if response.status_code != 200:
                            raise SourceError(f"Nguồn file trả HTTP {response.status_code}.")
                        declared = response.headers.get("Content-Length", "")
                        if declared.isdigit() and int(declared) > limit:
                            raise ValueError("File nguồn vượt giới hạn dung lượng.")
                        chunks, size = [], 0
                        for chunk in response.iter_content(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            size += len(chunk)
                            if size > limit:
                                raise ValueError("File nguồn vượt giới hạn dung lượng.")
                            chunks.append(chunk)
                        self._circuit_result(True)
                        return b"".join(chunks), response.headers.get("Content-Type", "")
                    finally:
                        response.close()
                except (requests.Timeout, requests.ConnectionError) as exc:
                    if attempt >= self.settings["max_retries"]:
                        raise SourceConnectionError("Không kết nối được nguồn file.") from exc
                    self._sleep(min(2 ** attempt, 8))
            raise SourceError("Không tải được file nguồn.")
        except (SourceError, requests.RequestException):
            self._circuit_result(False)
            raise

    def request_json(self, method: str, url: str, *, operation: str,
                     payload: Any = None, ttl: int = 0, force: bool = False,
                     allow_stale: bool = True, headers: dict | None = None,
                     timeout: int | None = None) -> SourceResult:
        key = cache_key(operation, payload if payload is not None else url)
        flight_key = f"{key}:force" if force else key
        if not force and ttl:
            hit = self.cache.get(key)
            if hit:
                self.cache_hits += 1
                data, fetched_at = hit[0]
                return SourceResult(data=data, fetched_at=fetched_at,
                                    last_success_at=fetched_at, cached=True)
        with self._flight_lock:
            event = self._flights.get(flight_key)
            leader = event is None
            if leader:
                event = self._flights[flight_key] = threading.Event()
        if not leader:
            self.dedup_waits += 1
            event.wait(self.settings["timeout_seconds"] * (self.settings["max_retries"] + 1))
            hit = self.cache.get(key, allow_stale=allow_stale)
            if hit:
                self.cache_hits += 1
                data, fetched_at = hit[0]
                return SourceResult(data=data, fetched_at=fetched_at,
                                    last_success_at=fetched_at, cached=True, stale=hit[1])
        started = self._clock()
        request_timeout = max(2, min(int(timeout or self.settings["timeout_seconds"]), 120))
        last_error: SourceError | None = None
        try:
            self._circuit_enter()
            for attempt in range(self.settings["max_retries"] + 1):
                try:
                    self._throttle()
                    self.request_count += 1
                    with self._session_lock:
                        response = self.session.request(method, url, json=payload,
                            headers=headers, timeout=(min(10, request_timeout), request_timeout))
                    error = self._classify(response)
                    if error:
                        raise error
                    try:
                        data = response.json()
                    except (ValueError, json.JSONDecodeError) as exc:
                        raise InvalidJsonError("Nguồn dữ liệu trả JSON không hợp lệ.") from exc
                    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    if ttl:
                        self.cache.set(key, (data, fetched_at), ttl)
                    self._circuit_result(True)
                    elapsed = (self._clock() - started) * 1000
                    SOURCE_HEALTH.record(success=True, latency_ms=elapsed)
                    logging.info("source_request operation=%s status=success duration_ms=%d retry_count=%d",
                                 operation, elapsed, attempt)
                    return SourceResult(data=data, fetched_at=fetched_at,
                                        last_success_at=fetched_at)
                except requests.Timeout as exc:
                    last_error = SourceTimeoutError("Nguồn dữ liệu phản hồi quá thời gian.")
                    last_error.__cause__ = exc
                except requests.ConnectionError as exc:
                    last_error = SourceConnectionError("Không kết nối được nguồn dữ liệu.")
                    last_error.__cause__ = exc
                except SourceError as exc:
                    last_error = exc
                if not last_error.transient or attempt >= self.settings["max_retries"]:
                    break
                delay = min(8.0, 2 ** attempt) + self._rng() * .25
                if isinstance(last_error, RateLimitError) and 'response' in locals():
                    delay = self._retry_after(response) or delay
                self._sleep(delay)
            self._circuit_result(False)
            elapsed = (self._clock() - started) * 1000
            code = getattr(last_error, "code", "source_error")
            SOURCE_HEALTH.record(success=False, latency_ms=elapsed, error_code=code)
            logging.warning("source_request operation=%s status=failed duration_ms=%d error=%s",
                            operation, elapsed, code)
            if allow_stale and ttl:
                stale = self.cache.get(key, allow_stale=True)
                if stale:
                    data, fetched_at = stale[0]
                    return SourceResult(data=data, status="stale", fetched_at=fetched_at,
                        last_success_at=fetched_at, cached=True, stale=True, error={"code": code,
                        "message": str(last_error)})
            raise last_error or SourceError("Không lấy được dữ liệu nguồn.")
        except CircuitOpenError as exc:
            if allow_stale and ttl:
                stale = self.cache.get(key, allow_stale=True)
                if stale:
                    data, fetched_at = stale[0]
                    return SourceResult(data=data, status="stale", fetched_at=fetched_at,
                        last_success_at=fetched_at, cached=True, stale=True,
                        error={"code": exc.code, "message": str(exc)})
            raise
        finally:
            if leader:
                with self._flight_lock:
                    self._flights.pop(flight_key, None)
                    event.set()

    def metrics(self) -> dict:
        total = self.request_count + self.cache_hits
        return SOURCE_HEALTH.snapshot() | {
            "circuit": self.circuit_status(),
            "cache_hits": self.cache_hits,
            "dedup_waits": self.dedup_waits,
            "cache_hit_rate": round(self.cache_hits * 100 / total, 1) if total else 0,
            "dedup_rate": round(self.dedup_waits * 100 / total, 1) if total else 0,
        }


_manager: SourceRequestManager | None = None
_manager_lock = threading.Lock()


def get_request_manager() -> SourceRequestManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = SourceRequestManager()
        return _manager


def reset_request_manager() -> None:
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.session.close()
        _manager = None
