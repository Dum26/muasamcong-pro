import gzip
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import event, insert

from server.auth import register
from server.database import (document_text, documents, get_db, now, pool_options,
                             reset_db, users)
from server.document_center import catalog
from server.performance import route_key, snapshot
from server.reporting import export_sync_max_rows
from web_app import WebHandler


class PerformanceTests(unittest.TestCase):
    def test_pool_bounds_and_route_labels(self):
        with patch.dict(os.environ, {"DB_POOL_SIZE": "100", "DB_MAX_OVERFLOW": "-5",
                                  "DB_POOL_TIMEOUT": "bad"}):
            self.assertEqual(pool_options("postgresql://host/db"),
                             {"pool_size": 20, "max_overflow": 0, "pool_timeout": 10,
                              "pool_recycle": 1800})
            self.assertEqual(pool_options("sqlite:///local.db"), {})
        self.assertEqual(route_key("/api/quality/" + "a" * 32 + "?secret=x"),
                         "/api/quality/:id")
        with patch.dict(os.environ, {"EXPORT_SYNC_MAX_ROWS": "999999"}):
            self.assertEqual(export_sync_max_rows(), 5000)

    def test_catalog_search_query_count_stays_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
                    (Path(folder) / "perf.db").as_posix()}):
                reset_db()
                owner = register("perf@example.test", "safe-long-password-123")["id"]
                with get_db().engine.begin() as conn:
                    for index in range(12):
                        document_id = f"{index+1:032x}"
                        conn.execute(insert(documents).values(id=document_id, user_id=owner,
                            filename=f"file{index}.txt", original_filename=f"file{index}.txt",
                            mime_type="text/plain", size=10, sha256="a" * 64,
                            storage_key=f"test/{index}", status="ready",
                            created_at=now(), updated_at=now()))
                        conn.execute(insert(document_text).values(id=f"{index+100:032x}",
                            document_id=document_id, source_id="body", label="Body",
                            text="needle", created_at=now()))
                count = 0
                def before(*_args):
                    nonlocal count
                    count += 1
                event.listen(get_db().engine, "before_cursor_execute", before)
                try:
                    result = catalog(owner, source="upload", query="needle", page_size=100)
                finally:
                    event.remove(get_db().engine, "before_cursor_execute", before)
                self.assertEqual(result["total"], 12)
                self.assertLessEqual(count, 3)
                reset_db()

    def test_http_readiness_metrics_and_static_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
                    (Path(folder) / "perf-http.db").as_posix(), "ENV": "development"}):
                reset_db()
                admin = register("admin-perf@example.test", "safe-long-password-123")
                with get_db().engine.begin() as conn:
                    conn.execute(users.update().where(users.c.id == admin["id"]).values(role="admin"))
                server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                root = f"http://127.0.0.1:{server.server_port}"
                try:
                    with urlopen(root + "/ready") as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(json.load(response)["status"], "ready")
                    with urlopen(Request(root + "/performance.js",
                            headers={"Accept-Encoding": "gzip"})) as response:
                        etag = response.headers["ETag"]
                        self.assertEqual(response.headers["Content-Encoding"], "gzip")
                        self.assertIn(b"performance", gzip.decompress(response.read()))
                    with self.assertRaises(HTTPError) as cached:
                        urlopen(Request(root + "/performance.js",
                            headers={"If-None-Match": etag}))
                    self.assertEqual(cached.exception.code, 304)
                    cached.exception.close()
                    with self.assertRaises(HTTPError) as denied:
                        urlopen(root + "/api/admin/performance")
                    self.assertEqual(denied.exception.code, 401)
                    denied.exception.close()
                    with self.assertRaises(HTTPError) as denied_status:
                        urlopen(root + "/api/admin/production-status")
                    self.assertEqual(denied_status.exception.code, 401)
                    denied_status.exception.close()
                    request = Request(root + "/api/auth/login",
                        data=json.dumps({"email": "admin-perf@example.test",
                                         "password": "safe-long-password-123"}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urlopen(request) as response:
                        cookie = next(value.split(";", 1)[0] for value in
                            response.headers.get_all("Set-Cookie") if value.startswith("msc_auth="))
                    with urlopen(Request(root + "/api/admin/performance",
                            headers={"Cookie": cookie})) as response:
                        self.assertGreaterEqual(json.load(response)["request_count"], 3)
                    with urlopen(Request(root + "/api/admin/production-status",
                            headers={"Cookie": cookie})) as response:
                        status = json.load(response)
                        self.assertEqual(status["database"], "ready")
                        self.assertEqual(status["storage"], "local")
                        self.assertNotIn("DATABASE_URL", status)
                    with urlopen(Request(root + "/admin/performance",
                            headers={"Cookie": cookie})) as response:
                        self.assertEqual(response.status, 200)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
                    reset_db()
