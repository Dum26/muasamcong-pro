import json
import logging
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server.config import validate_production_config
from server.database import Database, SCHEMA_VERSION, reset_db
from server.production_check import main as production_check_main
from server.logging_config import JsonFormatter
from web_app import WebHandler


class ProductionTests(unittest.TestCase):
    def test_structured_log_redacts_secrets(self):
        with patch.dict(os.environ, {"JOB_SECRET": "private-job-secret-123456789012345",
                "DATABASE_URL": "postgresql+psycopg://user:dbpassword123@host/db"}):
            record = logging.LogRecord("test", logging.ERROR, __file__, 1,
                "job=%s db=%s password=dbpassword123", (
                    os.environ["JOB_SECRET"], os.environ["DATABASE_URL"]), None)
            payload = JsonFormatter().format(record)
            self.assertNotIn("private-job-secret", payload)
            self.assertNotIn("dbpassword123", payload)
            self.assertIn("[REDACTED]", payload)

    def test_readiness_command_never_claims_ready_on_failed_check(self):
        from contextlib import redirect_stdout
        from io import StringIO
        output = StringIO()
        with patch("server.production_check.checks", return_value=[("database", False)]):
            with redirect_stdout(output):
                self.assertEqual(production_check_main(), 1)
        self.assertIn("NOT READY", output.getvalue())
        self.assertNotIn("PRODUCTION READY", output.getvalue())

    def test_production_rejects_unsafe_config(self):
        with patch.dict(os.environ, {"ENV": "production", "K_SERVICE": "",
                "DATABASE_URL": "sqlite:///unsafe.db", "SESSION_SECRET": "x" * 40,
                "JOB_SECRET": "y" * 40, "STORAGE_BACKEND": "gcs", "GCS_BUCKET": "test"}):
            with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
                validate_production_config()
            os.environ["DATABASE_URL"] = "postgresql://user:password@localhost/db"
            os.environ["SESSION_SECRET"] = "short"
            with self.assertRaisesRegex(RuntimeError, "SESSION_SECRET"):
                validate_production_config()
            os.environ["SESSION_SECRET"] = "x" * 40
            os.environ["JOB_SECRET"] = "short"
            with self.assertRaisesRegex(RuntimeError, "JOB_SECRET"):
                validate_production_config()
            os.environ["JOB_SECRET"] = "y" * 40
            os.environ["STORAGE_BACKEND"] = "local"
            with self.assertRaisesRegex(RuntimeError, "GCS"):
                validate_production_config()

    def test_production_startup_requires_migration_without_dropping_data(self):
        with tempfile.TemporaryDirectory() as folder:
            url = "sqlite:///" + (Path(folder) / "schema.db").as_posix()
            with patch("server.database.production", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "run migration"):
                    Database(url)
            db = Database(url, migrate_schema=True)
            self.assertEqual(db.schema_version(), SCHEMA_VERSION)
            db.engine.dispose()
            with patch("server.database.production", return_value=True):
                current = Database(url)
                self.assertTrue(current.health())
                current.engine.dispose()

    def test_csrf_and_generic_error_response(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
                    (Path(folder) / "http.db").as_posix(), "ENV": "development"}):
                reset_db()
                server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                root = f"http://127.0.0.1:{server.server_port}"
                try:
                    request = Request(root + "/api/auth/register",
                        data=json.dumps({"email": "prod-test@example.test",
                                         "password": "safe-long-password-123"}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urlopen(request) as response:
                        cookie = next(value.split(";", 1)[0] for value in
                            response.headers.get_all("Set-Cookie") if value.startswith("msc_auth="))
                    body = json.dumps({"action": "read-all"}).encode()
                    with patch("web_app.production", return_value=True):
                        with self.assertRaises(HTTPError) as blocked:
                            urlopen(Request(root + "/api/notifications", data=body,
                                headers={"Cookie": cookie, "Content-Type": "application/json"}))
                        self.assertEqual(blocked.exception.code, 403)
                        blocked.exception.close()
                        with urlopen(Request(root + "/api/notifications", data=body,
                                headers={"Cookie": cookie, "Content-Type": "application/json",
                                         "Origin": f"https://127.0.0.1:{server.server_port}"})) as response:
                            self.assertEqual(response.status, 200)
                    with patch.object(WebHandler, "_do_GET", side_effect=RuntimeError("private traceback marker")):
                        with self.assertRaises(HTTPError) as failed:
                            urlopen(root + "/health")
                        self.assertEqual(failed.exception.code, 500)
                        payload = failed.exception.read().decode()
                        self.assertIn("internal_error", payload)
                        self.assertNotIn("private traceback marker", payload)
                        self.assertIn("ERR-", payload)
                        failed.exception.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
                    reset_db()
