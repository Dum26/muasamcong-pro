import os
import json
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from sqlalchemy import update
from server.admin_users import list_accounts, set_account_active
from server.auth import login, register, session_user
from server.database import get_db, reset_db, users


class AdminUsersTests(unittest.TestCase):
    def test_directory_permissions_and_suspension(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"ENV": "development", "K_SERVICE": "",
                    "DATABASE_URL": "sqlite:///" + (Path(folder) / "test.db").as_posix()}):
                reset_db()
                try:
                    admin = register("admin@example.test", "safe-long-password-123")
                    person = register("person@example.test", "safe-long-password-123")
                    with get_db().engine.begin() as conn:
                        conn.execute(update(users).where(users.c.id == admin["id"]).values(role="admin"))
                    with self.assertRaises(PermissionError):
                        list_accounts(person["id"])
                    with self.assertRaises(PermissionError):
                        set_account_active(person["id"], admin["id"], False)
                    with self.assertRaises(ValueError):
                        set_account_active(admin["id"], admin["id"], False)
                    with self.assertRaises(ValueError):
                        set_account_active(admin["id"], person["id"], "false")
                    directory = list_accounts(admin["id"], "PERSON", role="user")
                    self.assertEqual(directory["total"], 1)
                    self.assertNotIn("password_hash", directory["items"][0])
                    self.assertEqual(list_accounts(admin["id"], "%")["total"], 0)
                    _, token = login(person["email"], "safe-long-password-123")
                    set_account_active(admin["id"], person["id"], False)
                    self.assertIsNone(session_user(token))
                    self.assertEqual(list_accounts(admin["id"], status="locked")["total"], 1)
                    with self.assertRaises(ValueError):
                        login(person["email"], "safe-long-password-123")
                    set_account_active(admin["id"], person["id"], True)
                    self.assertIsNone(session_user(token))
                    self.assertEqual(login(person["email"], "safe-long-password-123")[0]["id"], person["id"])
                    from web_app import WebHandler
                    server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    _, admin_token = login(admin["email"], "safe-long-password-123")
                    _, user_token = login(person["email"], "safe-long-password-123")
                    def call(path, cookie="", body=None):
                        return urlopen(Request(f"http://127.0.0.1:{server.server_port}" + path,
                            data=json.dumps(body).encode() if body is not None else None,
                            headers={"Cookie": "msc_auth=" + cookie, "Content-Type": "application/json"}), timeout=5)
                    try:
                        for cookie, expected in [("", 401), (user_token, 403)]:
                            for path, body in [("/api/admin/users", None),
                                    ("/api/admin/users/status", {"id": person["id"], "is_active": False})]:
                                with self.assertRaises(HTTPError) as denied:
                                    call(path, cookie, body)
                                self.assertEqual(denied.exception.code, expected)
                                denied.exception.close()
                        with call("/api/admin/users?page=999", admin_token) as response:
                            directory = json.load(response)
                            self.assertEqual(directory["page"], 1)
                            self.assertEqual(directory["summary"]["total"], 2)
                        with call("/api/admin/users/status", admin_token,
                                {"id": person["id"], "is_active": False}) as response:
                            self.assertTrue(json.load(response)["ok"])
                        self.assertIsNone(session_user(user_token))
                    finally:
                        server.shutdown()
                        server.server_close()
                        thread.join(timeout=5)
                finally:
                    reset_db()


if __name__ == "__main__":
    unittest.main()
