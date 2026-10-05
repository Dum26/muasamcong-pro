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

from sqlalchemy import update

from server.database import get_db, reset_db, users
from web_app import WebHandler


class DataQualityHttpTests(unittest.TestCase):
    def test_admin_routes_and_job_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            secret = "data-quality-secret-longer-than-32-characters"
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
                    (Path(folder) / "quality-http.db").as_posix(),
                    "ENV": "development", "JOB_SECRET": secret}):
                reset_db()
                server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                root = f"http://127.0.0.1:{server.server_port}"

                def call(path, cookie="", body=None, headers=None):
                    request = Request(root + path,
                        data=json.dumps(body).encode() if body is not None else None,
                        headers={"Cookie": cookie, "Content-Type": "application/json",
                                 **(headers or {})})
                    return urlopen(request)

                def signup(email):
                    with call("/api/auth/register", body={"email": email,
                            "password": "safe-long-password-123"}) as response:
                        return next(value.split(";", 1)[0] for value in response.headers.get_all("Set-Cookie")
                                    if value.startswith("msc_auth="))

                try:
                    user_cookie = signup("dq-user@example.test")
                    admin_cookie = signup("dq-admin@example.test")
                    with get_db().engine.begin() as conn:
                        conn.execute(update(users).where(users.c.email == "dq-admin@example.test")
                            .values(role="admin"))
                    for path in ("/api/admin/data-quality/summary", "/api/admin/data-quality/runs",
                                 "/admin/data-quality"):
                        with self.assertRaises(HTTPError) as denied:
                            call(path, user_cookie)
                        self.assertEqual(denied.exception.code, 403)
                        denied.exception.close()
                    with self.assertRaises(HTTPError) as denied_scan:
                        call("/api/admin/data-quality/scan", user_cookie, {})
                    self.assertEqual(denied_scan.exception.code, 403)
                    denied_scan.exception.close()
                    with self.assertRaises(HTTPError) as denied_merge:
                        call("/api/admin/data-quality/duplicates/" + "a" * 32 + "/merge",
                             user_cookie, {"target_id": "b" * 32})
                    self.assertEqual(denied_merge.exception.code, 403)
                    denied_merge.exception.close()
                    with call("/admin/data-quality", admin_cookie) as response:
                        self.assertEqual(response.status, 200)
                    with call("/api/admin/data-quality/scan", admin_cookie,
                              {"run_type": "full"}) as response:
                        self.assertEqual(response.status, 202)
                        self.assertEqual(json.load(response)["status"], "queued")
                    with self.assertRaises(HTTPError) as denied_job:
                        call("/internal/jobs/run-data-quality", body={},
                             headers={"X-Job-Secret": "wrong"})
                    self.assertEqual(denied_job.exception.code, 403)
                    denied_job.exception.close()
                    with call("/internal/jobs/run-data-quality", body={},
                              headers={"X-Job-Secret": secret}) as response:
                        self.assertEqual(json.load(response)["status"], "running")
                    with call("/api/admin/data-quality/summary", admin_cookie) as response:
                        self.assertEqual(json.load(response)["latest_run"]["run_type"], "full")
                    with call("/api/admin/data-quality/issues", admin_cookie) as response:
                        self.assertIn("items", json.load(response))
                    with call("/api/admin/data-quality/runs", admin_cookie) as response:
                        self.assertEqual(len(json.load(response)["items"]), 1)
                    with self.assertRaises(HTTPError) as missing:
                        call("/api/data-quality/tenders/IB2600000000", user_cookie)
                    self.assertEqual(missing.exception.code, 404)
                    missing.exception.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
                    reset_db()


if __name__ == "__main__":
    unittest.main()
