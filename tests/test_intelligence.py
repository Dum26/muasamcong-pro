import os
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import func, select, update

from app import ResultRow
from server.database import (contractors, get_db, investors, reset_db,
    tender_changes, tender_events, tender_snapshots, tenders)
from server.intelligence import (analytics, clean_code, compare_tenders, get_plan,
    get_tender, ingest_row, list_tenders, normalize_name, parse_money,
    entity_profile, discover_documents)
from server.intelligence_jobs import enqueue_tender, job_status, run_pending
from server.tender_source import refresh_tender
from web_app import WebHandler


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
            (Path(self.folder.name) / "intelligence.db").as_posix(), "ENV": "development"})
        self.env.start()
        reset_db()

    def tearDown(self):
        reset_db()
        self.env.stop()
        self.folder.cleanup()

    def test_unified_search_normalization_ranking_filters_and_pagination(self):
        from server.search_engine import search
        ingest_row(ResultRow(notify_no="IB2600123456", plan_no="2600123456",
            plan_name="Kế hoạch lựa chọn nhà thầu", package_name="Bệnh viện Chợ Rẫy",
            investor_name="Bệnh viện A", public_date="11/09/2026",
            bid_close_date="24/09/2026 09:00", package_price="500.000.000 VND"))
        ingest_row(ResultRow(notify_no="IB2600123457", package_name="Bệnh viện B",
            public_date="12/09/2026", package_price="100.000.000 VND"))
        self.assertEqual(search(q="benh vien cho ray")["items"][0]["code"], "IB2600123456")
        self.assertEqual(search(q="benh vien cho rey", kind="tender")["items"][0]["rank"], 6)
        self.assertEqual(search(q="ib2600123456")["items"][0]["rank"], 0)
        self.assertTrue(search(q="ib2600123456")["cache_hit"])
        self.assertFalse(search(q="ib2600123456", force_refresh=True)["cache_hit"])
        self.assertEqual(search(q="ke hoach lua chon nha thau", kind="plan")["total"], 1)
        self.assertEqual(search(q="benh vien", kind="investor")["total"], 1)
        self.assertEqual(search(kind="tender", price_min="500000000")["total"], 1)
        self.assertEqual(search(kind="tender", from_date="2026-09-12")["total"], 1)
        self.assertEqual(search(q='investor:"Bệnh viện A" after:2026-09-01', kind="tender")["total"], 1)
        self.assertEqual(search(q="price:>500000000", kind="tender")["total"], 1)
        self.assertEqual(search(q="before:not-a-date", kind="tender")["total"], 0)
        self.assertEqual(search(kind="tender", sort="published", order="asc")["items"][0]["code"], "IB2600123456")
        self.assertEqual(search(q="khong ton tai")["total"], 0)
        self.assertEqual(search(kind="tender", page=2, page_size=10)["items"], [])
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        import server.search_engine as engine
        engine.invalidate_search_cache()
        with patch.object(engine, "_search_uncached", wraps=engine._search_uncached) as worker:
            with ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(lambda _: engine.search(q="khong ton tai", kind="tender"), range(5)))
            self.assertEqual(worker.call_count, 1)
        self.assertEqual(search(q="benh vien", kind="tender")["total"], 2)
        ingest_row(ResultRow(notify_no="IB2600123458", package_name="Bệnh viện C"))
        self.assertEqual(search(q="benh vien", kind="tender")["total"], 3)
        from server.search_engine import record_search_metric, search_metrics
        record_search_metric("tender", 12, {"total": 0, "cache_hit": True})
        metrics = search_metrics()
        self.assertEqual(metrics["searches"], 1)
        self.assertEqual(metrics["zero_result_rate"], 1)
        self.assertEqual(metrics["cache_hit_rate"], 1)
        with self.assertRaises(ValueError):
            search(sort="DROP TABLE tenders")

    def test_canonical_record_snapshots_changes_and_real_timeline(self):
        row = ResultRow(notify_no="IB2600123456-00", plan_no="2600123456",
            plan_name="Kế hoạch thuốc", package_name="Gói thuốc", investor_name=" Bệnh viện  A ",
            procuring_entity_name="Bên mời thầu A", package_price="1.200.000 VND",
            public_date="11/09/2026", bid_close_date="24/09/2026 09:00",
            tender_status="Chưa đóng thầu")
        first = ingest_row(row)
        self.assertEqual(first["tender_code"], "IB2600123456")
        self.assertTrue(first["changed"])
        second = ingest_row(row)
        self.assertFalse(second["changed"])
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(tenders)), 1)
            self.assertEqual(conn.scalar(select(func.count()).select_from(tender_snapshots)), 1)
            self.assertEqual(conn.scalar(select(func.count()).select_from(investors)), 1)
            events = conn.execute(select(tender_events.c.event_type)).scalars().all()
        self.assertEqual(set(events), {"published", "deadline"})
        row.bid_close_date = "28/09/2026 09:00"
        changed = ingest_row(row)
        self.assertEqual([item["field_name"] for item in changed["changes"]], ["bid_closing_date"])
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(tender_snapshots)), 2)
            self.assertEqual(conn.scalar(select(func.count()).select_from(tender_changes)), 1)
            self.assertEqual(conn.scalar(select(func.count()).select_from(tender_events)), 4)
        self.assertEqual(get_tender("IB2600123456")["tender"]["bid_closing_date"],
                         "2026-09-28T09:00:00")
        self.assertNotIn("missing_deadline", get_tender("IB2600123456")["tender"]["quality_flags"])
        self.assertEqual(get_plan("PL2600123456")["package_count"], 1)
        self.assertEqual(list_tenders(query='investor:"Bệnh viện A"')["total"], 1)
        self.assertEqual(analytics("month")["series"][0]["tenders"], 1)

    def test_entity_normalization_and_money_are_conservative(self):
        self.assertEqual(normalize_name("  CÔNG TY   A "), normalize_name("công ty a"))
        self.assertNotEqual(normalize_name("Công ty A"), normalize_name("Công ty B"))
        self.assertEqual(clean_code("IB2600123456-00"), "IB2600123456")
        self.assertEqual(parse_money("1.200.000 VND"), 1200000)
        self.assertIsNone(parse_money("1,2 tỷ"))
        row = ResultRow(notify_no="IB2600123456", winner="Công ty A")
        ingest_row(row)
        row.notify_no = "IB2600123457"
        row.winner = "  CÔNG TY   A "
        ingest_row(row)
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(contractors)), 1)

    def test_profiles_compare_and_source_document_validation(self):
        first = ResultRow(notify_no="IB2600123456", package_name="Gói A",
            investor_name="Bệnh viện A", winner="Công ty X", package_price="2.000 VND",
            winning_price="1.600 VND", public_date="11/09/2026")
        second = ResultRow(notify_no="IB2600123457", package_name="Gói B",
            investor_name="Bệnh viện A", public_date="12/09/2026")
        ingest_row(first, source_record={"attachments": [
            {"fileName": "HSMT.pdf", "fileUrl": "https://muasamcong.mpi.gov.vn/docs/1"},
            {"fileName": "Bad.pdf", "fileUrl": "https://example.com/docs/1"}]})
        ingest_row(second)
        self.assertEqual(len(get_tender("IB2600123456")["documents"]), 1)
        self.assertEqual(len(discover_documents({"fileName": "x", "fileUrl": "http://muasamcong.mpi.gov.vn/x"})), 0)
        self.assertEqual(compare_tenders(["IB2600123456", "IB2600123457"])["items"][0]["saving_rate"], "20.00")
        investor_id = get_tender("IB2600123456")["tender"]["investor_id"]
        self.assertEqual(entity_profile("investor", investor_id)["total"], 2)
        self.assertEqual(list_tenders(from_date="2026-09-12")["total"], 1)

    def test_refresh_uses_cache_and_queue_retries_are_persistent(self):
        class Source:
            calls = 0
            def get_tender(self, code):
                self.calls += 1
                return {"notifyNo": code, "bidName": "Gói nguồn", "publicDate": "2026-09-11"}, None, None
        source = Source()
        first = refresh_tender("IB2600123456", source=source)
        self.assertFalse(first["cached"])
        second = refresh_tender("IB2600123456", source=source)
        self.assertTrue(second["cached"])
        self.assertEqual(source.calls, 1)
        job = enqueue_tender("IB2600123456")
        self.assertEqual(enqueue_tender("IB2600123456")["id"], job["id"])
        with patch("server.intelligence_jobs.refresh_tender", side_effect=OSError("offline")):
            self.assertEqual(run_pending()["failed"], 1)
        self.assertEqual(job_status(job["id"])["status"], "retry")
        self.assertEqual(job_status(job["id"])["attempts"], 1)

    def test_intelligence_http_routes_are_authenticated_and_bookmarkable(self):
        ingest_row(ResultRow(notify_no="IB2600123456", plan_no="2600123456",
            package_name="Gói thuốc", investor_name="Bệnh viện A",
            public_date="11/09/2026"))
        server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        root = f"http://127.0.0.1:{server.server_port}"

        def call(path, cookie="", body=None):
            return urlopen(Request(root + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"Cookie": cookie, "Content-Type": "application/json"}))

        try:
            with self.assertRaises(HTTPError) as denied:
                call("/api/intelligence/tenders")
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()
            with call("/api/auth/register", body={"email": "intel@example.test",
                "password": "long-password-123"}) as response:
                cookie = next(value.split(";", 1)[0] for value in response.headers.get_all("Set-Cookie")
                              if value.startswith("msc_auth="))
            with call("/api/intelligence/tenders?page=1&page_size=1", cookie) as response:
                self.assertEqual(json.load(response)["total"], 1)
            with call("/api/intelligence/search?q=benh+vien&page_size=25", cookie) as response:
                self.assertGreaterEqual(json.load(response)["total"], 1)
            with call("/api/intelligence/suggest?q=IB2600123456", cookie) as response:
                self.assertEqual(json.load(response)["items"][0]["code"], "IB2600123456")
            with patch("web_app.RATE_LIMITER.allow", return_value=False):
                with self.assertRaises(HTTPError) as limited:
                    call("/api/intelligence/search?q=benh", cookie)
                self.assertEqual(limited.exception.code, 429)
                limited.exception.close()
            local_params = {"mode": "Kho dữ liệu", "keyword": "benh vien", "kind": "tender",
                            "sort": "relevance", "page_size": "25"}
            with call("/api/history", cookie, {"params": local_params}) as response:
                self.assertEqual(json.load(response)["items"][0]["mode"], "Kho dữ liệu")
            with call("/api/history", cookie, {"action": "complete", "params": local_params,
                                               "result_count": 1}) as response:
                self.assertEqual(json.load(response)["items"][0]["result_count"], 1)
            with call("/api/presets", cookie, {"action": "save", "name": "Bệnh viện",
                                               "params": local_params}) as response:
                self.assertEqual(json.load(response)["presets"][0]["params"]["mode"], "Kho dữ liệu")
            with self.assertRaises(HTTPError) as invalid_sort:
                call("/api/intelligence/search?sort=unsafe", cookie)
            self.assertEqual(invalid_sort.exception.code, 400)
            invalid_sort.exception.close()
            with call("/api/intelligence/tenders/IB2600123456", cookie) as response:
                self.assertEqual(json.load(response)["tender"]["title"], "Gói thuốc")
            with get_db().engine.begin() as conn:
                conn.execute(update(tenders).where(
                    tenders.c.tender_code == "IB2600123456").values(
                    last_synced_at="2020-01-01T00:00:00+00:00"))
            with call("/api/intelligence/tenders/IB2600123456", cookie) as response:
                self.assertTrue(json.load(response)["refresh_queued"])
            self.assertEqual(enqueue_tender("IB2600123456")["status"], "queued")
            with call("/api/intelligence/plans/PL2600123456", cookie) as response:
                self.assertEqual(json.load(response)["package_count"], 1)
            with self.assertRaises(HTTPError) as denied_admin:
                call("/api/intelligence/admin/sync", cookie)
            self.assertEqual(denied_admin.exception.code, 403)
            denied_admin.exception.close()
            with self.assertRaises(HTTPError) as denied_metrics:
                call("/api/intelligence/admin/search-metrics", cookie)
            self.assertEqual(denied_metrics.exception.code, 403)
            denied_metrics.exception.close()
            with call("/app/tenders/IB2600123456", cookie) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"intelligence.js", response.read())
            with call("/app/search?q=benh+vien", cookie) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"search-engine.js", response.read())
            with call("/search-engine.js") as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"searchLocal", response.read())
            with call("/intelligence.css") as response:
                self.assertIn(b"intel-workspace", response.read())
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
