import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import insert

from app import ResultRow
from server.bi_analytics import overview
from server.database import get_db, reset_db, tenders, users, now
from server.intelligence import ingest_row
from server.reporting import (delete_dashboard, export_report, get_dashboard, get_report,
    list_dashboards, list_reports, preview_report, run_dashboard, run_saved_report,
    save_dashboard, save_report, set_default_dashboard, validate_spec)


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
            (Path(self.folder.name) / "reporting.db").as_posix(), "ENV": "development"})
        self.env.start()
        reset_db()
        with get_db().engine.begin() as conn:
            for user_id in ("a" * 32, "b" * 32):
                conn.execute(insert(users).values(id=user_id, email=user_id + "@example.test",
                    password_hash="test", role="user", created_at=now(), updated_at=now(),
                    last_login_at=None, is_active=True))
        self.a, self.b = "a" * 32, "b" * 32
        ingest_row(ResultRow(notify_no="IB2600123456", package_name="Gói thuốc",
            investor_name="Bệnh viện A", location="Hà Nội", package_price="2.000 VND",
            winning_price="1.600 VND", winner="Nhà thầu A", public_date="11/09/2026"))
        ingest_row(ResultRow(notify_no="IB2600123457", package_name="=EVIL()",
            investor_name="Bệnh viện B", location="Huế", package_price="3.000 VND",
            public_date="12/09/2026"))

    def tearDown(self):
        reset_db()
        self.env.stop()
        self.folder.cleanup()

    def test_aggregation_filters_and_coverage(self):
        result = overview({"from": "2026-09-11", "to": "2026-09-11"})
        self.assertEqual(result["kpis"]["tenders"], 1)
        self.assertEqual(result["kpis"]["saving_count"], 1)
        self.assertEqual(result["kpis"]["saving_rate"], "20.00")
        self.assertEqual(result["source"]["priced_count"], 1)
        self.assertEqual(result["dimensions"]["location"][0]["value"], "Hà Nội")
        self.assertEqual(result["comparison"]["previous"]["values"]["tenders"], 0)
        self.assertEqual(overview({"location": "Huế"})["kpis"]["tenders"], 1)
        self.assertIsNone(overview({"location": "Huế"})["khlcnt"]["count"])
        self.assertEqual(overview({"price_min": "2000", "price_max": "2000"})["kpis"]["tenders"], 1)
        self.assertEqual(overview({}, results_only=True)["kpis"]["tenders"], 1)
        self.assertEqual(overview({}, results_only=True)["dimensions"]["location"][0]["count"], 1)
        self.assertIsNone(overview({"location": "Huế"})["trend"][0]["winning_value"])

    def test_report_whitelist_grouping_pagination_and_export_safety(self):
        spec = {"dataset": "tenders", "columns": ["tender_code", "title"],
            "filters": [{"field": "publish_date", "operator": "between",
                         "value": ["2026-09-11", "2026-09-12"]}],
            "sort": {"field": "tender_code", "direction": "asc"}}
        result = preview_report(spec, page_size=1)
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["items"]), 1)
        grouped = preview_report({"dataset": "tenders", "group_by": "month:publish_date",
            "metrics": [{"op": "count", "field": "*"},
                        {"op": "sum", "field": "package_price"}]})
        self.assertEqual(grouped["items"][0]["count_rows"], 2)
        self.assertEqual(grouped["items"][0]["sum_package_price"], "5000.00")
        with self.assertRaises(ValueError):
            validate_spec({"dataset": "tenders", "columns": ["password_hash"]})
        with self.assertRaises(ValueError):
            validate_spec({"dataset": "tenders", "metrics": [{"op": "sum", "field": "title"}]})
        with self.assertRaises(ValueError):
            validate_spec({"dataset": "tenders", "filters": [{"field": "title;DROP TABLE",
                "operator": "equals", "value": "x"}]})
        csv_bytes, filename = export_report(spec, "csv")
        self.assertTrue(filename.endswith(".csv"))
        rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
        self.assertIn("'=EVIL()", [row[1] for row in rows[1:]])
        xlsx_bytes, _ = export_report(spec, "xlsx")
        self.assertTrue(xlsx_bytes.startswith(b"PK"))

    def test_report_and_dashboard_ownership(self):
        spec = {"dataset": "tenders", "columns": ["tender_code", "title"]}
        saved = save_report(self.a, {"name": "Báo cáo A", "spec": spec})
        self.assertEqual(len(list_reports(self.a)), 1)
        self.assertEqual(list_reports(self.b), [])
        self.assertIsNone(get_report(self.b, saved["id"]))
        self.assertEqual(run_saved_report(self.a, saved["id"])["total"], 2)
        with self.assertRaises(LookupError):
            run_saved_report(self.b, saved["id"])
        dashboard = save_dashboard(self.a, {"name": "Bảng của tôi", "layout": [
            {"type": "kpi", "title": "Số gói", "spec": {"dataset": "tenders",
                "group_by": "status", "metrics": [{"op": "count", "field": "*"}]}}]})
        self.assertEqual(len(run_dashboard(self.a, dashboard["id"])["widgets"]), 1)
        self.assertIsNone(get_dashboard(self.b, dashboard["id"]))
        self.assertEqual(list_dashboards(self.b), [])
        with self.assertRaises(LookupError):
            set_default_dashboard(self.b, dashboard["id"])
        self.assertTrue(set_default_dashboard(self.a, dashboard["id"])["is_default"])
        self.assertFalse(delete_dashboard(self.b, dashboard["id"]))

    def test_large_result_is_paginated_on_server(self):
        with get_db().engine.begin() as conn:
            conn.execute(insert(tenders), [{"tender_code": f"IB2601{number:06d}",
                "title": "Gói kiểm thử", "first_seen_at": now(), "last_seen_at": now()}
                for number in range(240)])
        result = preview_report({"dataset": "tenders",
            "columns": ["tender_code", "title"]}, page=2, page_size=10000)
        self.assertEqual(result["total"], 242)
        self.assertEqual(result["page_size"], 100)
        self.assertEqual(len(result["items"]), 100)
