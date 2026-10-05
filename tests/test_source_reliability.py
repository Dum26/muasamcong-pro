import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from server.source.errors import CircuitOpenError, InvalidJsonError, SourceTimeoutError
from server.source.health import SOURCE_HEALTH, SourceHealthMonitor
from server.source.request_manager import SourceRequestManager, cache_key


class FakeResponse:
    def __init__(self, status=200, data=None, headers=None, invalid=False):
        self.status_code = status
        self._data = data
        self.headers = headers or {"Content-Type": "application/json"}
        self.invalid = invalid

    def json(self):
        if self.invalid:
            raise ValueError("invalid json")
        return self._data


class SequenceSession:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def request(self, *_args, **_kwargs):
        self.calls += 1
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def close(self):
        pass


class SourceReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.health_patch = patch.object(SOURCE_HEALTH, "_persist_transition")
        self.health_patch.start()
        self.addCleanup(self.health_patch.stop)

    def manager(self, session, sleeps=None):
        sleeps = sleeps if sleeps is not None else []
        with patch.dict("os.environ", {"SOURCE_REQUESTS_PER_SECOND": "20",
                                        "SOURCE_MAX_RETRIES": "2"}):
            return SourceRequestManager(session, sleeper=sleeps.append, rng=lambda: 0)

    def test_retry_500_then_success_and_retry_after(self):
        sleeps = []
        session = SequenceSession([FakeResponse(500), FakeResponse(200, {"ok": True})])
        result = self.manager(session, sleeps).request_json(
            "POST", "https://example.test", operation="search", payload={"q": "x"})
        self.assertEqual(result.data, {"ok": True})
        self.assertEqual(session.calls, 2)
        self.assertIn(1, sleeps)

        sleeps = []
        session = SequenceSession([FakeResponse(429, headers={
            "Content-Type": "application/json", "Retry-After": "3"}),
            FakeResponse(200, {"ok": True})])
        self.manager(session, sleeps).request_json(
            "GET", "https://example.test", operation="detail")
        self.assertIn(3.0, sleeps)

    def test_timeout_stops_after_configured_attempts(self):
        session = SequenceSession([requests.Timeout(), requests.Timeout(),
                                   requests.Timeout()])
        with self.assertRaises(SourceTimeoutError):
            self.manager(session).request_json(
                "GET", "https://example.test", operation="detail")
        self.assertEqual(session.calls, 3)

    def test_invalid_json_is_permanent(self):
        session = SequenceSession([FakeResponse(200, invalid=True)])
        with self.assertRaises(InvalidJsonError):
            self.manager(session).request_json(
                "GET", "https://example.test", operation="detail")
        self.assertEqual(session.calls, 1)

    def test_cache_force_refresh_and_deterministic_key(self):
        session = SequenceSession([FakeResponse(200, {"version": 1}),
                                   FakeResponse(200, {"version": 2})])
        manager = self.manager(session)
        first = manager.request_json("POST", "https://example.test", operation="search",
                                     payload={"a": 1, "b": 2}, ttl=60)
        cached = manager.request_json("POST", "https://example.test", operation="search",
                                      payload={"b": 2, "a": 1}, ttl=60)
        forced = manager.request_json("POST", "https://example.test", operation="search",
                                      payload={"a": 1, "b": 2}, ttl=60, force=True)
        self.assertEqual((first.data, cached.data, forced.data),
                         ({"version": 1}, {"version": 1}, {"version": 2}))
        self.assertEqual(session.calls, 2)
        self.assertEqual(cache_key("search", {"a": 1, "b": 2}),
                         cache_key("search", {"b": 2, "a": 1}))

    def test_concurrent_duplicate_requests_share_one_fetch(self):
        entered, release = threading.Event(), threading.Event()

        class BlockingSession(SequenceSession):
            def request(self, *_args, **_kwargs):
                self.calls += 1
                entered.set()
                release.wait(2)
                return FakeResponse(200, {"shared": True})

        session = BlockingSession([])
        manager = self.manager(session)
        results = []
        call = lambda: results.append(manager.request_json(
            "GET", "https://example.test", operation="tender", payload="IB1", ttl=60).data)
        first = threading.Thread(target=call)
        second = threading.Thread(target=call)
        first.start(); entered.wait(1); second.start(); time.sleep(.03); release.set()
        first.join(2); second.join(2)
        self.assertEqual(session.calls, 1)
        self.assertEqual(results, [{"shared": True}, {"shared": True}])

    def test_health_transitions_and_recovers(self):
        monitor = SourceHealthMonitor(max_samples=20)
        with patch.object(monitor, "_persist_transition"):
            for _ in range(5):
                monitor.record(success=False, latency_ms=20, error_code="server")
            self.assertEqual(monitor.snapshot()["status"], "Unavailable")
            for _ in range(20):
                monitor.record(success=True, latency_ms=10)
            self.assertEqual(monitor.snapshot()["status"], "Healthy")

    def test_circuit_opens_and_half_open_recovers(self):
        session = SequenceSession([FakeResponse(500), FakeResponse(500),
                                   FakeResponse(200, {"recovered": True})])
        manager = self.manager(session)
        manager.settings["max_retries"] = 0
        manager.settings["circuit_failure_threshold"] = 2
        for _ in range(2):
            with self.assertRaises(Exception):
                manager.request_json("GET", "https://example.test", operation="health")
        self.assertEqual(manager.circuit_status(), "OPEN")
        with self.assertRaises(CircuitOpenError):
            manager.request_json("GET", "https://example.test", operation="health")
        self.assertEqual(session.calls, 2)
        manager._opened_at -= manager.settings["circuit_cooldown_seconds"]
        self.assertEqual(manager.circuit_status(), "HALF_OPEN")
        self.assertEqual(manager.request_json("GET", "https://example.test",
            operation="health").data, {"recovered": True})
        self.assertEqual(manager.circuit_status(), "CLOSED")

    def test_stale_cache_is_explicit_when_source_fails(self):
        session = SequenceSession([FakeResponse(500)])
        manager = self.manager(session)
        manager.settings["max_retries"] = 0
        key = cache_key("tender", "IB2600123456")
        manager.cache.set(key, ({"code": "IB2600123456"}, "2026-09-01T00:00:00Z"), 1)
        manager.cache._items[key].expires_at = time.monotonic() - 1
        result = manager.request_json("GET", "https://example.test", operation="tender",
            payload="IB2600123456", ttl=1)
        self.assertTrue(result.cached and result.stale)
        self.assertEqual(result.status, "stale")
        self.assertEqual(result.last_success_at, "2026-09-01T00:00:00Z")

    def test_database_throttle_shares_slots_between_managers(self):
        from server.database import reset_db
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {
                "DATABASE_URL": "sqlite:///" + (Path(folder) / "throttle.db").as_posix(),
                "ENV": "development", "SOURCE_REQUESTS_PER_SECOND": "1"}):
            reset_db()
            delays = []
            first = SourceRequestManager(sleeper=delays.append)
            second = SourceRequestManager(sleeper=delays.append)
            try:
                with patch("server.source.request_manager.production", return_value=True):
                    first._throttle()
                    second._throttle()
                self.assertTrue(any(delay > .5 for delay in delays))
            finally:
                first.session.close()
                second.session.close()
                reset_db()


if __name__ == "__main__":
    unittest.main()
