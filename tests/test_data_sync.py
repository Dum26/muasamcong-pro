import json
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import delete, func, insert, inspect, select, update

from app import ResultRow
from server.auth import register
from server.database_adapters import user_stores
from server.data_sync import (get_run, process_sync, retry_run, scheduler_tick,
                              set_source_enabled, start_sync, sync_overview)
from server.database import (background_jobs, get_db, now, reset_db,
    schema_migrations, sync_checkpoints, sync_run_items, sync_runs, sync_sources,
    tenders, users, followed_tenders, saved_searches, saved_search_seen, user_notifications)
from server.intelligence import ingest_row
from web_app import WebHandler


class DataSyncFlowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
            (Path(self.folder.name) / "sync.db").as_posix(), "ENV": "development"})
        self.env.start()
        reset_db()

    def tearDown(self):
        reset_db()
        self.env.stop()
        self.folder.cleanup()

    def test_watched_local_search_uses_existing_owner_scoped_notifications(self):
        from server.background_jobs import sync_saved_search_item
        owner = register("local-search-owner@example.test", "safe-long-password-123")
        other = register("local-search-other@example.test", "safe-long-password-123")
        saved = user_stores(owner["id"]).presets.update({"action": "save",
            "name": "Bệnh viện", "params": {"mode": "Kho dữ liệu",
            "keyword": "benh vien", "kind": "tender", "sort": "relevance",
            "price_min": "500000000"}})[0]
        user_stores(owner["id"]).presets.update({"action": "watch", "id": saved["id"],
                                                    "enabled": True})
        ingest_row(ResultRow(notify_no="IB2600777711", package_name="Bệnh viện A",
                             package_price="600.000.000 VND"))
        self.assertEqual(sync_saved_search_item(saved["id"])["new_results"], 0)
        ingest_row(ResultRow(notify_no="IB2600777712", package_name="Bệnh viện B",
                             package_price="700.000.000 VND"))
        self.assertEqual(sync_saved_search_item(saved["id"])["new_results"], 1)
        ingest_row(ResultRow(notify_no="IB2600777713", package_name="Bệnh viện C",
                             package_price="100.000.000 VND"))
        self.assertEqual(sync_saved_search_item(saved["id"])["new_results"], 0)
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(user_notifications)
                .where(user_notifications.c.user_id == owner["id"])), 1)
            self.assertEqual(conn.scalar(select(func.count()).select_from(user_notifications)
                .where(user_notifications.c.user_id == other["id"])), 0)

    def test_watched_local_search_scans_beyond_first_thousand(self):
        from server.background_jobs import sync_saved_search_item
        account = register("many-search-owner@example.test", "safe-long-password-123")
        saved = user_stores(account["id"]).presets.update({"action": "save",
            "name": "Nhiều gói", "params": {"mode": "Kho dữ liệu",
            "keyword": "benh vien", "kind": "tender"}})[0]
        user_stores(account["id"]).presets.update({"action": "watch", "id": saved["id"],
                                                      "enabled": True})
        with get_db().engine.begin() as conn:
            conn.execute(insert(tenders), [{"tender_code": f"IB260099{i:06d}",
                "title": f"Bệnh viện {i}", "search_text": f"benh vien {i}",
                "first_seen_at": now(), "last_seen_at": now()}
                for i in range(1205)])
        self.assertEqual(sync_saved_search_item(saved["id"])["new_results"], 0)
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(saved_search_seen)
                .where(saved_search_seen.c.search_id == saved["id"])), 1205)

    def test_durable_run_queue_dedup_checkpoint_and_reconciliation(self):
        for index in range(2):
            ingest_row(ResultRow(notify_no=f"IB260066660{index}", package_name=f"Gói {index}"))
        run = start_sync(trigger="manual", mode="codes",
            codes=["IB2600666600", "IB2600666601", "IB2600666600"], limit=10)
        self.assertEqual(run["status"], "running")
        self.assertEqual(run["discovered_count"], 2)
        self.assertEqual(run["queued_count"], 2)
        reused = start_sync(trigger="manual", mode="codes", codes=["IB2600666600"])
        self.assertEqual(reused["id"], run["id"])
        self.assertTrue(reused["reused"])
        with patch("server.intelligence_jobs.refresh_tender", return_value={"changed": False}):
            result = process_sync(run_id=run["id"], limit=5)
        self.assertEqual(result["queue"]["processed"], 2)
        finished = get_run(run["id"])
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["success_count"], 2)
        self.assertEqual(len(finished["items"]), 2)
        overview = sync_overview()
        self.assertEqual(overview["sources"][0]["id"], "egp-public")
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(sync_sources)), 1)
            self.assertEqual(conn.scalar(select(func.count()).select_from(sync_runs)), 1)
            self.assertEqual(conn.scalar(select(func.count()).select_from(sync_run_items)), 2)
            checkpoint = conn.execute(select(sync_checkpoints)).mappings().one()
        self.assertIsNotNone(checkpoint["last_success_at"])
        self.assertEqual(checkpoint["cursor_json"]["last_entity_id"], "IB2600666601")

    def test_v6_database_upgrades_to_latest_without_dropping_old_data(self):
        ingest_row(ResultRow(notify_no="IB2600666610", package_name="Dữ liệu cũ"))
        database = get_db()
        with database.engine.begin() as conn:
            sync_run_items.drop(conn, checkfirst=True)
            sync_checkpoints.drop(conn, checkfirst=True)
            sync_runs.drop(conn, checkfirst=True)
            sync_sources.drop(conn, checkfirst=True)
            conn.execute(delete(schema_migrations).where(schema_migrations.c.version >= 7))
        reset_db()
        upgraded = get_db()
        names = set(inspect(upgraded.engine).get_table_names())
        self.assertTrue({"sync_sources", "sync_runs", "sync_run_items",
                         "sync_checkpoints"}.issubset(names))
        with upgraded.engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(tenders)), 1)
            self.assertEqual(conn.scalar(select(func.max(schema_migrations.c.version))), 18)

    def test_empty_scheduler_tick_is_idempotent(self):
        first = scheduler_tick(limit=2)
        self.assertEqual(first["status"], "done")
        self.assertEqual(first["started"]["status"], "completed")
        second = scheduler_tick(limit=2)
        self.assertIsNone(second["started"])
        self.assertFalse(set_source_enabled("egp-public", False)["is_enabled"])
        self.assertIsNone(scheduler_tick(limit=2)["started"])
        self.assertTrue(set_source_enabled("egp-public", True)["is_enabled"])

    def test_scheduler_queues_followed_and_saved_search_without_crossing_users(self):
        account = register("sync-owner@example.test", "safe-long-password-123")
        other = register("sync-other@example.test", "safe-long-password-123")
        user_stores(account["id"]).watchlist.update({
            "action": "add", "code": "IB2600777701", "name": "Gói đang theo dõi"})
        saved = user_stores(account["id"]).presets.update({"action": "save",
            "name": "Thiết bị", "params": {"mode": "Thông báo mời thầu",
            "keyword": "thiết bị"}})[0]
        user_stores(account["id"]).presets.update({
            "action": "watch", "id": saved["id"], "enabled": True})

        def fake_search(job):
            job.rows = [SimpleNamespace(notify_no="IB2600777702", plan_no="")]
            job.state = "done"

        with patch("app.MuaSamCongClient") as client, patch(
                "web_app._run_search", side_effect=fake_search):
            client.return_value.search_notices.return_value = [{
                "notifyNo": "IB2600777701", "bidName": "Gói đang theo dõi"}]
            result = scheduler_tick(limit=3)
        self.assertEqual(result["scheduled"], {"followed": 1, "saved_searches": 1})
        self.assertEqual(result["queue"]["processed"], 2)
        with get_db().engine.connect() as conn:
            jobs = conn.execute(select(background_jobs.c.job_type,
                background_jobs.c.status)).all()
            owner_saved = conn.scalar(select(saved_searches.c.last_run_at).where(
                saved_searches.c.id == saved["id"]))
            other_follows = conn.scalar(select(func.count()).select_from(followed_tenders)
                .where(followed_tenders.c.user_id == other["id"]))
        self.assertEqual({kind for kind, status in jobs if status == "completed"},
                         {"sync-followed", "sync-saved-search"})
        self.assertTrue(owner_saved)
        self.assertEqual(other_follows, 0)

    def test_failed_run_retries_three_times_and_can_be_requeued(self):
        ingest_row(ResultRow(notify_no="IB2600666699", package_name="Gói lỗi tạm thời"))
        run = start_sync(trigger="manual", mode="codes", codes=["IB2600666699"])
        with patch("server.intelligence_jobs.refresh_tender", side_effect=OSError("offline")):
            for attempt in range(3):
                if attempt:
                    with get_db().engine.begin() as conn:
                        conn.execute(update(background_jobs).where(
                            background_jobs.c.entity_id == "IB2600666699",
                            background_jobs.c.status == "retry").values(next_retry_at=now()))
                process_sync(run_id=run["id"], limit=1)
        failed = get_run(run["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["failed_count"], 1)
        retried = retry_run(run["id"])
        self.assertNotEqual(retried["id"], run["id"])
        with patch("server.intelligence_jobs.refresh_tender", return_value={"changed": False}):
            process_sync(run_id=retried["id"], limit=1)
        self.assertEqual(get_run(retried["id"])["status"], "completed")


class DataSyncHttpTests(unittest.TestCase):
    def test_admin_only_api_and_internal_job_secret(self):
        folder = tempfile.TemporaryDirectory()
        secret = "data-sync-secret-with-at-least-32-characters"
        env = patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
            (Path(folder.name) / "sync-http.db").as_posix(), "ENV": "development",
            "JOB_SECRET": secret})
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
            user_cookie = signup("sync-user@example.test")
            admin_cookie = signup("sync-admin@example.test")
            with get_db().engine.begin() as conn:
                conn.execute(update(users).where(users.c.email == "sync-admin@example.test")
                    .values(role="admin"))
            with self.assertRaises(HTTPError) as forbidden:
                call("/api/data-sync", user_cookie)
            self.assertEqual(forbidden.exception.code, 403)
            forbidden.exception.close()
            with call("/api/data-sync", admin_cookie) as response:
                self.assertEqual(json.load(response)["sources"][0]["id"], "egp-public")
            with call("/api/data-sync/metrics", admin_cookie) as response:
                self.assertIn("circuit", json.load(response))
            with call("/api/data-sync/sources/egp-public/pause", admin_cookie, {}) as response:
                self.assertFalse(json.load(response)["is_enabled"])
            with call("/api/data-sync/sources/egp-public/enable", admin_cookie, {}) as response:
                self.assertTrue(json.load(response)["is_enabled"])
            with call("/api/data-sync/runs", admin_cookie,
                    {"mode": "stale", "limit": 10}) as response:
                self.assertEqual(json.load(response)["status"], "completed")
            with self.assertRaises(HTTPError) as denied:
                call("/internal/jobs/run-data-sync", body={},
                     headers={"X-Job-Secret": "wrong"})
            self.assertEqual(denied.exception.code, 403)
            denied.exception.close()
            with call("/internal/jobs/run-data-sync", body={},
                    headers={"X-Job-Secret": secret}) as response:
                self.assertEqual(json.load(response)["status"], "done")
            with call("/internal/jobs/run-sync", body={},
                    headers={"X-Job-Secret": secret}) as response:
                self.assertEqual(json.load(response)["status"], "done")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
            reset_db()
            env.stop()
            folder.cleanup()


if __name__ == "__main__":
    unittest.main()
