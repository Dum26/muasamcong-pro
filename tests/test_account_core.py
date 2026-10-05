"""Persistence, session and scheduled-change checks without external e-GP calls."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import func, select, update

from server.auth import login, logout, register, session_user
from server.background_jobs import run_saved_searches
from server.config import database_url
from server.database import (get_db, reset_db, saved_searches, schema_migrations,
                      sessions, tender_change_history, user_notifications)
from server.database_adapters import user_stores
from web_app import JobStore, RateLimiter


class AccountCoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///" + (Path(self.folder.name) / "core.db").as_posix(),
            "ENV": "development", "PORT": "0"})
        self.environment.start()
        reset_db()

    def tearDown(self):
        reset_db()
        self.environment.stop()
        self.folder.cleanup()

    def test_auth_and_expired_session(self):
        account = register(" Person@Example.test ", "safe-long-password-123")
        self.assertEqual(account["email"], "person@example.test")
        with self.assertRaises(ValueError):
            register("person@example.test", "safe-long-password-123")
        with self.assertRaises(ValueError):
            login("person@example.test", "wrong-password")
        _, token = login("person@example.test", "safe-long-password-123")
        self.assertEqual(session_user(token)["id"], account["id"])
        with get_db().engine.begin() as conn:
            conn.execute(update(sessions).values(expires_at="2000-01-01T00:00:00+00:00"))
        self.assertIsNone(session_user(token))
        _, token = login("person@example.test", "safe-long-password-123")
        logout(token)
        self.assertIsNone(session_user(token))

    def test_migration_is_idempotent_and_production_requires_postgres(self):
        db = get_db()
        db.migrate()
        db.migrate()
        with db.engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(schema_migrations)), 18)
        with patch.dict(os.environ, {"ENV": "production", "DATABASE_URL": self.environ_database_url()}):
            with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
                database_url()

    def test_account_data_survives_database_reconnect(self):
        account = register("persist@example.test", "safe-long-password-123")
        user_stores(account["id"]).watchlist.update({
            "action": "add", "code": "IBPERSIST1", "name": "Gói được lưu"})
        reset_db()
        self.assertEqual(user_stores(account["id"]).watchlist.read()[0]["code"], "IBPERSIST1")

    def environ_database_url(self):
        return os.environ["DATABASE_URL"]

    def test_watch_changes_and_user_isolation(self):
        a = register("a@example.test", "safe-long-password-123")
        b = register("b@example.test", "safe-long-password-123")
        watch_a, watch_b = user_stores(a["id"]).watchlist, user_stores(b["id"]).watchlist
        watch_a.update({"action": "add", "code": "IBTESTCHANGE", "name": "Gói thử",
                        "row": {"package_name": "Gói thử", "bid_close_date": "2026-10-01 09:00"}})
        self.assertEqual(watch_b.read(), [])
        watch_a.sync([{"code": "IBTESTCHANGE", "package_name": "Gói thử",
                       "bid_close_date": "2026-10-02 09:00"}])
        with get_db().engine.connect() as conn:
            changes = conn.execute(select(tender_change_history)
                .where(tender_change_history.c.user_id == a["id"])).mappings().all()
            alerts = conn.execute(select(user_notifications)
                .where(user_notifications.c.user_id == a["id"])).mappings().all()
        self.assertTrue(any(row["field_name"] == "bid_close_date" for row in changes))
        self.assertTrue(any(row["type"] == "deadline_changed" for row in alerts))
        self.assertFalse(any(row["user_id"] == b["id"] for row in alerts))
        count = len(alerts)
        watch_a.sync([{"code": "IBTESTCHANGE", "package_name": "Gói thử",
                       "bid_close_date": "2026-10-02 09:00"}])
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(user_notifications)
                .where(user_notifications.c.user_id == a["id"])), count)
        watch_a.update({"action": "remove", "code": "IBTESTCHANGE"})
        self.assertEqual(watch_a.read(), [])

    def test_saved_search_notifications_have_baseline_and_deduplicate(self):
        account = register("saved@example.test", "safe-long-password-123")
        presets = user_stores(account["id"]).presets
        saved = presets.update({"action": "save", "name": "Thuốc", "params": {
            "mode": "Thông báo mời thầu", "keyword": "thuốc"}})[0]
        presets.update({"action": "watch", "id": saved["id"], "enabled": True})
        batches = [["IBBASE1"], ["IBBASE1", "IBNEW2"], ["IBBASE1", "IBNEW2"]]

        def fake_search(job):
            job.rows = [SimpleNamespace(notify_no=code, plan_no="") for code in batches.pop(0)]
            job.state = "done"

        with patch("web_app._run_search", side_effect=fake_search):
            self.assertEqual(run_saved_searches()["new_results"], 0)
            self.assertEqual(run_saved_searches()["new_results"], 1)
            self.assertEqual(run_saved_searches()["new_results"], 0)
        with get_db().engine.connect() as conn:
            rows = conn.execute(select(user_notifications).where(
                user_notifications.c.user_id == account["id"])).mappings().all()
            last_run = conn.scalar(select(saved_searches.c.last_run_at).where(
                saved_searches.c.id == saved["id"]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tender_code"], "IBNEW2")
        self.assertTrue(last_run)

    def test_rate_limiter(self):
        limiter = RateLimiter()
        self.assertTrue(limiter.allow("login:a", 2, 60))
        self.assertTrue(limiter.allow("login:a", 2, 60))
        self.assertFalse(limiter.allow("login:a", 2, 60))
        self.assertTrue(limiter.allow("login:b", 2, 60))

    def test_search_cache_is_scoped_to_account(self):
        store = JobStore()
        params = {"mode": "Thông báo mời thầu", "keyword": "thuốc"}
        first = store.create(params, owner="user-a")
        first.update("done", [])
        self.assertIs(store.find_cached(params, owner="user-a"), first)
        self.assertIsNone(store.find_cached(params, owner="user-b"))


if __name__ == "__main__":
    unittest.main()
