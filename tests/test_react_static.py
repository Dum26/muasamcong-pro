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


class ReactStaticTests(unittest.TestCase):
    def test_react_static_opt_in_preserves_api_and_private_routes(self):
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder) / "dist"
            (build / "assets").mkdir(parents=True)
            (build / "index.html").write_text('<html><div id="root">React marker</div></html>', encoding="utf-8")
            (build / "assets" / "index-abc123.js").write_text('const reactMarker=1;', encoding="utf-8")
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" + (Path(folder) / "test.db").as_posix(),
                                       "ENV": "development", "REACT_FRONTEND_ENABLED": "1"}), \
                 patch("web_app.REACT_DIR", build):
                reset_db()
                server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                root = f"http://127.0.0.1:{server.server_port}"
                try:
                    with urlopen(root + "/login") as response:
                        self.assertIn(b"React marker", response.read())
                        self.assertEqual(response.headers["Cache-Control"], "no-cache")
                    with urlopen(root + "/assets/index-abc123.js") as response:
                        self.assertIn(b"reactMarker", response.read())
                        self.assertIn("immutable", response.headers["Cache-Control"])
                        self.assertIn("javascript", response.headers["Content-Type"])
                    for path in ("/app", "/app/search", "/app/archive", "/app/entities/investor/0123456789abcdef0123456789abcdef", "/app/codes", "/app/compare", "/app/reports",
                                 "/app/documents", "/app/automations", "/app/analytics",
                                 "/app/ai", "/app/settings", "/app/admin", "/legacy"):
                        with urlopen(root + path) as redirected:
                            self.assertTrue(redirected.url.endswith("/login"))
                    register = Request(root + "/api/auth/register", data=json.dumps({
                        "email": "react-static@example.test", "password": "safe-long-password-123"}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urlopen(register) as response:
                        cookie = next(value.split(";", 1)[0] for value in
                            response.headers.get_all("Set-Cookie") if value.startswith("msc_auth="))
                    with urlopen(Request(root + "/app/search", headers={"Cookie": cookie})) as response:
                        self.assertIn(b"React marker", response.read())
                    with urlopen(Request(root + "/app/automations", headers={"Cookie": cookie})) as response:
                        self.assertIn(b"React marker", response.read())
                    with self.assertRaises(HTTPError) as forbidden:
                        urlopen(Request(root + "/api/admin/stats", headers={"Cookie": cookie}))
                    self.assertEqual(forbidden.exception.code, 403)
                    forbidden.exception.close()
                    with self.assertRaises(HTTPError) as admin_page:
                        urlopen(Request(root + "/admin", headers={"Cookie": cookie}))
                    self.assertEqual(admin_page.exception.code, 403)
                    admin_page.exception.close()
                    with self.assertRaises(HTTPError) as admin_sync:
                        urlopen(Request(root + "/admin/sync", headers={"Cookie": cookie}))
                    self.assertEqual(admin_sync.exception.code, 403)
                    admin_sync.exception.close()
                    with get_db().engine.begin() as connection:
                        connection.execute(update(users).where(users.c.email == "react-static@example.test").values(role="admin"))
                    with urlopen(Request(root + "/admin/sync", headers={"Cookie": cookie})) as response:
                        self.assertIn(b"React marker", response.read())
                    with urlopen(Request(root + "/legacy", headers={"Cookie": cookie})) as response:
                        self.assertIn(b"<script src=\"/app.js\"", response.read())
                    with urlopen(root + "/api/health") as response:
                        self.assertTrue(json.load(response)["ok"])
                    with self.assertRaises(HTTPError) as missing:
                        urlopen(Request(root + "/api/unknown"))
                    self.assertEqual(missing.exception.code, 401)
                    missing.exception.close()
                finally:
                    server.shutdown(); server.server_close(); thread.join(timeout=2); reset_db()


if __name__ == "__main__":
    unittest.main()
