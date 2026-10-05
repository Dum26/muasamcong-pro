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

from app import ResultRow
from server.database import get_db, reset_db, users
from server.intelligence import ingest_row
from web_app import WebHandler


class AutomationHttpTests(unittest.TestCase):
    def test_auth_ownership_dry_run_and_scheduler_secret(self):
        folder = tempfile.TemporaryDirectory()
        secret = "test-job-secret-with-at-least-thirty-two-chars"
        env = patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
            (Path(folder.name) / "automation-http.db").as_posix(),
            "ENV": "development", "JOB_SECRET": secret})
        env.start()
        reset_db()
        server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        root = f"http://127.0.0.1:{server.server_port}"

        def call(path, cookie="", body=None, headers=None):
            request = Request(root + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"Cookie": cookie, "Content-Type": "application/json", **(headers or {})})
            return urlopen(request)

        def signup(email):
            with call("/api/auth/register", body={"email": email,
                "password": "long-password-123"}) as response:
                return next(value.split(";", 1)[0] for value in response.headers.get_all("Set-Cookie")
                            if value.startswith("msc_auth="))

        try:
            with self.assertRaises(HTTPError) as denied:
                call("/api/automations")
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()
            first, second = signup("auto-a@example.test"), signup("auto-b@example.test")
            with call("/app/automations", first) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"automation.js", response.read())
            draft = {"name": "Y tế", "trigger_type": "NEW_TENDER",
                "run_frequency": "manual", "conditions": {"logic": "AND", "items": [
                    {"field": "title", "operator": "contains", "value": "y tế"}]},
                "actions": [{"type": "FOLLOW_TENDER"}]}
            with call("/api/automations", first, draft) as response:
                rule_id = json.load(response)["id"]
            ingest_row(ResultRow(notify_no="IB2600777000", package_name="Thiết bị y tế"))
            with call("/api/automations/preview", first, draft) as response:
                self.assertEqual(json.load(response)["matched_count"], 1)
            with call("/api/automations", second) as response:
                self.assertEqual(json.load(response)["items"], [])
            with self.assertRaises(HTTPError) as denied_rule:
                call("/api/automations/" + rule_id, second)
            self.assertEqual(denied_rule.exception.code, 404)
            denied_rule.exception.close()
            with call("/api/automations/" + rule_id + "/test", first, {}) as response:
                self.assertTrue(json.load(response)["dry_run"])
            with call("/api/automations/" + rule_id + "/run", first, {}) as response:
                self.assertEqual(json.load(response)["action_count"], 1)
            with call("/api/automations/" + rule_id + "/enable", first, {}) as response:
                self.assertTrue(json.load(response)["is_enabled"])
            with call("/api/automations/" + rule_id + "/pause", first, {}) as response:
                self.assertFalse(json.load(response)["is_enabled"])
            with call("/api/automations/" + rule_id + "/runs", first) as response:
                self.assertEqual(len(json.load(response)["items"]), 1)
            with call("/api/automations/analytics?days=14", first) as response:
                analytics = json.load(response)
            self.assertEqual(analytics["trend"][0]["runs"], 1)
            self.assertEqual(analytics["actions"][0]["action"], "FOLLOW_TENDER")
            with self.assertRaises(HTTPError) as denied_job:
                call("/internal/jobs/run-automations", body={},
                    headers={"X-Job-Secret": "wrong"})
            self.assertEqual(denied_job.exception.code, 403)
            denied_job.exception.close()
            with call("/internal/jobs/run-automations", body={},
                    headers={"X-Job-Secret": secret}) as response:
                self.assertEqual(json.load(response)["rules"], 0)
            with get_db().engine.begin() as conn:
                conn.execute(update(users).where(users.c.email == "auto-a@example.test")
                    .values(role="admin"))
            with call("/api/admin/stats", first) as response:
                stats = json.load(response)
            self.assertIn("automation_average_duration_ms", stats)
            self.assertEqual(stats["automation_top_triggers"][0]["trigger"], "NEW_TENDER")
            with call("/api/automations/" + rule_id + "/delete", first, {}) as response:
                self.assertTrue(json.load(response)["ok"])
            with self.assertRaises(HTTPError) as deleted:
                call("/api/automations/" + rule_id, first)
            self.assertEqual(deleted.exception.code, 404)
            deleted.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
            reset_db()
            env.stop()
            folder.cleanup()


if __name__ == "__main__":
    unittest.main()
