import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import ResultRow
from server.database import reset_db
from web_app import JOBS, WebHandler


class CloudRunHttpTests(unittest.TestCase):
    def test_concurrent_sessions_keep_tracking_and_exports_separate(self):
        workspace = tempfile.TemporaryDirectory()
        server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        origin = f"http://127.0.0.1:{server.server_port}"
        with patch.dict(os.environ, {"PORT": str(server.server_port), "SITE_URL": origin,
                                          "DATABASE_URL": "sqlite:///" + workspace.name.replace("\\", "/") + "/test.db"}):
            thread.start()

            def call(path, cookie="", body=None):
                data = json.dumps(body).encode() if body is not None else None
                request = Request(origin + path, data=data,
                                  headers={"Cookie": cookie, "Content-Type": "application/json"})
                return urlopen(request)

            try:
                with call("/api/auth/register", body={"email":"user-a@example.test","password":"long-password-a-123"}) as response:
                    user_a = json.load(response)["user"]
                    cookie_a = next(value.split(";",1)[0] for value in response.headers.get_all("Set-Cookie") if value.startswith("msc_auth="))
                with call("/api/auth/register", body={"email":"user-b@example.test","password":"long-password-b-123"}) as response:
                    cookie_b = next(value.split(";",1)[0] for value in response.headers.get_all("Set-Cookie") if value.startswith("msc_auth="))
                self.assertNotEqual(cookie_a, cookie_b)
                with call("/app", cookie_a) as response:
                    self.assertIn("cloud-service", response.read().decode())

                def follow(cookie, code):
                    with call("/api/watchlist", cookie, {"action": "add", "code": code, "name": code}) as response:
                        return json.load(response)["items"]

                with ThreadPoolExecutor(max_workers=2) as pool:
                    a = pool.submit(follow, cookie_a, "IBTESTA1")
                    b = pool.submit(follow, cookie_b, "IBTESTB1")
                    self.assertEqual([x["code"] for x in a.result()], ["IBTESTA1"])
                    self.assertEqual([x["code"] for x in b.result()], ["IBTESTB1"])
                with call("/api/watchlist", cookie_a) as response:
                    self.assertEqual([x["code"] for x in json.load(response)["items"]], ["IBTESTA1"])

                job = JOBS.create({"mode": "Thông báo mời thầu"}, owner=user_a["id"])
                job.update("done", [ResultRow(notify_no="IBTESTA1", package_name="Gói thử")])
                payload = {"job_id": job.id, "indices": "all"}
                with call("/api/export", cookie_a, payload) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("spreadsheetml.sheet", response.headers["Content-Type"])
                    self.assertTrue(response.read().startswith(b"PK"))
                with call("/api/downloads", cookie_a) as response:
                    downloads = json.load(response)["items"]
                    self.assertEqual(len(downloads), 1)
                with call(downloads[0]["url"], cookie_a) as response:
                    self.assertTrue(response.read().startswith(b"PK"))
                with call("/api/downloads", cookie_b) as response:
                    self.assertEqual(json.load(response)["items"], [])
                with self.assertRaises(HTTPError) as forbidden_file:
                    call(downloads[0]["url"], cookie_b)
                self.assertEqual(forbidden_file.exception.code, 404)
                forbidden_file.exception.close()
                for asset in ("/tailwind.css", "/vendor/lucide.min.js"):
                    with call(asset, cookie_a) as response:
                        self.assertEqual(response.status, 200)
                        self.assertGreater(len(response.read()), 1000)
                with patch.dict(os.environ, {"SITE_URL": ""}):
                    run_host = "muasamcong-pro-123.asia-southeast1.run.app"
                    for path, expected in (("/", f'https://{run_host}/'),
                                           ("/sitemap.xml", f'https://{run_host}/loc-du-lieu-mua-sam-cong')):
                        request = Request(origin + path, headers={"Host": run_host, "Cookie": cookie_a})
                        with urlopen(request) as response:
                            self.assertIn(expected, response.read().decode())
                with self.assertRaises(HTTPError) as blocked:
                    call("/api/export", cookie_b, payload)
                self.assertEqual(blocked.exception.code, 400)
                blocked.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                reset_db()
                workspace.cleanup()


if __name__ == "__main__":
    unittest.main()
