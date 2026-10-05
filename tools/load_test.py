"""Offline HTTP load smoke test using a temporary SQLite DB and local server only."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from unittest.mock import patch

from app import ResultRow
from server.database import reset_db
from server.intelligence import ingest_row
from web_app import WebHandler

SCENARIOS = ("/health", "/api/intelligence/search?q=IB2600123456",
    "/api/intelligence/search?q=IB2600123456&page=2&page_size=25",
    "/api/intelligence/tenders/IB2600123456", "/api/watchlist",
    "/api/intelligence/analytics", "/api/document-center",
    "/api/notifications", "/api/automations")


def _request(url: str, cookie: str = "", body: dict | None = None) -> tuple[int, float]:
    headers = {"Cookie": cookie}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=json.dumps(body).encode() if body is not None else None,
                      headers=headers)
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=15) as response:
            response.read()
            return response.status, (time.perf_counter() - started) * 1000
    except HTTPError as exc:
        exc.close()
        return exc.code, (time.perf_counter() - started) * 1000
    except (URLError, TimeoutError):
        return 0, (time.perf_counter() - started) * 1000


def _percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered)-1, int(proportion * (len(ordered)-1)))], 2)


def run(levels: tuple[int, ...] = (10, 25, 50, 100), requests_per_level: int = 100) -> list[dict]:
    with tempfile.TemporaryDirectory() as folder:
        env = {"DATABASE_URL": "sqlite:///" + (Path(folder) / "load.db").as_posix(),
               "ENV": "development", "RATE_LIMIT_PER_WINDOW": "100000"}
        with patch.dict(os.environ, env):
            reset_db()
            ingest_row(ResultRow(notify_no="IB2600123456", package_name="Gói kiểm thử local"))
            server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_port}"
            try:
                request = Request(root + "/api/auth/register",
                    data=json.dumps({"email": "load@example.test",
                        "password": "safe-long-password-123"}).encode(),
                    headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=15) as response:
                    cookie = next(value.split(";", 1)[0] for value in
                        response.headers.get_all("Set-Cookie") if value.startswith("msc_auth="))
                results = []
                for concurrency in levels:
                    tasks = [SCENARIOS[index % len(SCENARIOS)]
                             for index in range(max(requests_per_level, concurrency))]
                    started = time.perf_counter()
                    with ThreadPoolExecutor(max_workers=concurrency) as pool:
                        futures = [pool.submit(_request, root + path, cookie) for path in tasks]
                        measurements = [future.result() for future in as_completed(futures)]
                    elapsed = time.perf_counter() - started
                    durations = [duration for _, duration in measurements]
                    failures = sum(status == 0 or status >= 500 for status, _ in measurements)
                    results.append({"concurrency": concurrency, "requests": len(measurements),
                        "p50_ms": round(statistics.median(durations), 2),
                        "p95_ms": _percentile(durations, .95),
                        "p99_ms": _percentile(durations, .99),
                        "rps": round(len(measurements) / elapsed, 2),
                        "error_rate": round(failures / len(measurements), 4),
                        "status_counts": {str(status): sum(s == status for s, _ in measurements)
                                          for status in sorted({s for s, _ in measurements})}})
                return results
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                reset_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--levels", default="10,25,50,100")
    parser.add_argument("--requests", type=int, default=100)
    args = parser.parse_args()
    levels = tuple(int(value) for value in args.levels.split(","))
    if not levels or any(value < 1 or value > 100 for value in levels):
        parser.error("Concurrency must be between 1 and 100.")
    print(json.dumps(run(levels, max(args.requests, 1)), indent=2))
