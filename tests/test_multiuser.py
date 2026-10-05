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

from sqlalchemy import insert, select, update

from server.database import get_db, reset_db, user_notifications, users, now
from web_app import WebHandler


class MultiUserTests(unittest.TestCase):
    def test_auth_private_data_and_admin_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            db_url = "sqlite:///" + (Path(folder) / "users.db").as_posix()
            with patch.dict(os.environ, {"DATABASE_URL": db_url, "PORT": "0", "ENV": "development",
                                              "JOB_SECRET": "test-job-secret-longer-than-32-characters"}):
                server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                root = f"http://127.0.0.1:{server.server_port}"

                def call(path, cookie="", body=None, headers=None):
                    request = Request(root + path, data=json.dumps(body).encode() if body is not None else None,
                                      headers={"Cookie": cookie, "Content-Type": "application/json", **(headers or {})})
                    return urlopen(request)

                def signup(email):
                    with call("/api/auth/register", body={"email": email,
                                                          "password": "safe-long-password-123"}) as response:
                        user = json.load(response)["user"]
                        cookie = next(value.split(";", 1)[0] for value in response.headers.get_all("Set-Cookie")
                                      if value.startswith("msc_auth="))
                        return user, cookie

                try:
                    with call("/") as response:
                        self.assertIn("Lọc dữ liệu mua sắm công", response.read().decode())
                    with self.assertRaises(HTTPError) as private_template:
                        call("/admin.html")
                    self.assertEqual(private_template.exception.code, 404)
                    private_template.exception.close()
                    with call("/app") as response:
                        self.assertTrue(response.url.endswith("/login"))
                    with call("/app/search") as response:
                        self.assertTrue(response.url.endswith("/login"))
                    user_a, cookie_a = signup("a@example.test")
                    with call("/app/search", cookie_a) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers.get("X-Robots-Tag"), "noindex, nofollow")
                    user_b, cookie_b = signup("b@example.test")
                    with get_db().engine.connect() as conn:
                        stored = conn.execute(select(users.c.password_hash).where(users.c.id == user_a["id"])).scalar()
                    self.assertNotIn("safe-long-password-123", stored)
                    self.assertTrue(stored.startswith("pbkdf2_sha256$"))

                    with call("/api/watchlist", cookie_a, {"action": "add", "code": "IBTESTA1", "name": "Gói A"}):
                        pass
                    with call("/api/watchlist", cookie_a, {"action": "edit", "code": "IBTESTA1",
                                                           "note": "Ghi chú riêng", "tags": ["Quan trọng"],
                                                           "priority": "Khẩn cấp"}) as response:
                        item = json.load(response)["items"][0]
                        self.assertEqual(item["note"], "Ghi chú riêng")
                        self.assertEqual(item["priority"], "Khẩn cấp")
                    with call("/api/watchlist", cookie_b) as response:
                        self.assertEqual(json.load(response)["items"], [])
                    with self.assertRaises(HTTPError) as denied_edit:
                        call("/api/watchlist", cookie_b, {"action": "edit", "code": "IBTESTA1", "note": "Sai"})
                    denied_edit.exception.close()
                    with call("/api/watchlist", cookie_a) as response:
                        self.assertEqual(json.load(response)["items"][0]["note"], "Ghi chú riêng")

                    params = {"mode": "Thông báo mời thầu", "keyword": "thuốc"}
                    with call("/api/presets", cookie_a, {"action": "save", "name": "Thuốc", "params": params}) as response:
                        saved = json.load(response)["presets"][0]
                    with call("/api/presets", cookie_a, {"action": "watch", "id": saved["id"], "enabled": True}) as response:
                        self.assertTrue(json.load(response)["presets"][0]["is_watch_enabled"])
                    with call("/api/presets", cookie_b) as response:
                        self.assertEqual(json.load(response)["presets"], [])
                    with call("/api/history", cookie_a, {"params": params}):
                        pass
                    with call("/api/history", cookie_b) as response:
                        self.assertEqual(json.load(response)["items"], [])

                    with get_db().engine.begin() as conn:
                        conn.execute(insert(user_notifications).values(id="a" * 32, user_id=user_a["id"],
                            type="system", title="Thông báo A", message="Riêng A", tender_code=None,
                            is_read=False, created_at=now()))
                    with call("/api/notifications", cookie_b) as response:
                        self.assertEqual(json.load(response)["items"], [])
                    with call("/api/notifications", cookie_a, {"action": "read-all"}):
                        pass
                    with call("/api/notifications", cookie_a) as response:
                        self.assertTrue(json.load(response)["items"][0]["is_read"])

                    with self.assertRaises(HTTPError) as denied_admin:
                        call("/api/admin/stats", cookie_b)
                    self.assertEqual(denied_admin.exception.code, 403)
                    denied_admin.exception.close()
                    with get_db().engine.begin() as conn:
                        conn.execute(update(users).where(users.c.id == user_a["id"]).values(role="admin"))
                    with call("/api/admin/stats", cookie_a) as response:
                        self.assertEqual(json.load(response)["total_users"], 2)
                    with call("/api/admin/ai-stats", cookie_a) as response:
                        ai_stats = json.load(response)
                        self.assertIn("extraction_failures", ai_stats)
                        self.assertIn("average_processing_ms", ai_stats)
                        self.assertIn("by_user", ai_stats)
                    with self.assertRaises(HTTPError) as denied_job:
                        call("/internal/jobs/run-saved-searches", cookie_a, {})
                    self.assertEqual(denied_job.exception.code, 403)
                    denied_job.exception.close()
                    with patch("server.background_jobs.run_saved_searches", return_value={
                            "status": "done", "searches": 0, "new_results": 0}):
                        with call("/internal/jobs/run-saved-searches", body={}, headers={
                                "X-Job-Secret": "test-job-secret-longer-than-32-characters"}) as response:
                            self.assertEqual(json.load(response)["status"], "done")
                    with self.assertRaises(HTTPError) as invalid_json:
                        request = Request(root + "/api/history", data=b"[]", headers={
                            "Cookie": cookie_a, "Content-Type": "application/json"})
                        urlopen(request)
                    self.assertEqual(invalid_json.exception.code, 400)
                    invalid_json.exception.close()
                    with call("/health") as response:
                        self.assertEqual(json.load(response)["status"], "ok")
                    with call("/api/auth/logout", cookie_a, {}):
                        pass
                    with self.assertRaises(HTTPError) as logged_out:
                        call("/api/watchlist", cookie_a)
                    self.assertEqual(logged_out.exception.code, 401)
                    logged_out.exception.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
                    reset_db()


if __name__ == "__main__":
    unittest.main()
