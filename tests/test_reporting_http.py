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

from app import ResultRow
from server.database import reset_db
from server.intelligence import ingest_row
from web_app import WebHandler


class ReportingHttpTests(unittest.TestCase):
    def test_auth_ownership_preview_export_and_routes(self):
        folder = tempfile.TemporaryDirectory()
        env = patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
            (Path(folder.name) / "http.db").as_posix(), "ENV": "development", "PORT": "0"})
        env.start()
        reset_db()
        ingest_row(ResultRow(notify_no="IB2600123456", package_name="Gói A",
            investor_name="Bệnh viện A", public_date="11/09/2026"))
        server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        root = f"http://127.0.0.1:{server.server_port}"

        def call(path, cookie="", body=None):
            request = Request(root + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"Cookie": cookie, "Content-Type": "application/json"})
            return urlopen(request)

        def signup(email):
            with call("/api/auth/register", body={"email": email,
                "password": "long-password-123"}) as response:
                return next(value.split(";", 1)[0] for value in response.headers.get_all("Set-Cookie")
                            if value.startswith("msc_auth="))

        try:
            with self.assertRaises(HTTPError) as denied:
                call("/api/analytics/overview")
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()
            first, second = signup("bi-a@example.test"), signup("bi-b@example.test")
            with call("/app/analytics/tenders", first) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"bi.js", response.read())
            with call("/api/analytics/overview?from=2026-09-11&to=2026-09-11", first) as response:
                self.assertEqual(json.load(response)["kpis"]["tenders"], 1)
            spec = {"dataset": "tenders", "columns": ["tender_code", "title"]}
            with call("/api/reports/preview", first, {"spec": spec}) as response:
                self.assertEqual(json.load(response)["total"], 1)
            with call("/api/reports", first, {"name": "Báo cáo A", "spec": spec}) as response:
                report_id = json.load(response)["id"]
            with call("/api/reports", second) as response:
                self.assertEqual(json.load(response)["items"], [])
            with self.assertRaises(HTTPError) as denied_report:
                call("/api/reports/" + report_id + "/run", second, {})
            self.assertEqual(denied_report.exception.code, 404)
            denied_report.exception.close()
            with call("/api/reports/" + report_id + "/run", first, {}) as response:
                self.assertEqual(json.load(response)["total"], 1)
            with call("/api/reports/export", first, {"report_id": report_id,
                "format": "csv"}) as response:
                self.assertTrue(response.headers["Content-Type"].startswith("text/csv"))
                self.assertIn(b"tender_code", response.read())
            with call("/api/downloads", first) as response:
                file_url = json.load(response)["items"][0]["url"]
            with call(file_url, first) as response:
                self.assertTrue(response.headers["Content-Type"].startswith("text/csv"))
            with self.assertRaises(HTTPError) as denied_file:
                call(file_url, second)
            self.assertEqual(denied_file.exception.code, 404)
            denied_file.exception.close()
            layout = [{"type": "kpi", "title": "Số gói", "spec": {
                "dataset": "tenders", "group_by": "all",
                "metrics": [{"op": "count", "field": "*"}]}}]
            with call("/api/dashboards", first, {"name": "Bảng A", "layout": layout}) as response:
                dashboard_id = json.load(response)["id"]
            with call("/api/dashboards/" + dashboard_id + "/run", first, {}) as response:
                self.assertEqual(json.load(response)["widgets"][0]["data"]["items"][0]["count_rows"], 1)
            with self.assertRaises(HTTPError) as denied_dashboard:
                call("/api/dashboards/" + dashboard_id, second)
            self.assertEqual(denied_dashboard.exception.code, 404)
            denied_dashboard.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
            reset_db()
            env.stop()
            folder.cleanup()
