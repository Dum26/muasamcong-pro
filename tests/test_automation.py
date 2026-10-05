import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, insert, select

from app import ResultRow
from server.automation_conditions import (evaluate_condition, evaluate_group,
    validate_condition, validate_group)
from server.automation_engine import (automation_analytics, delete_rule, duplicate_rule, get_rule,
    list_events, list_rules, list_runs, run_due_automations, run_rule, save_rule,
    set_enabled)
from server.database import (automation_events, background_jobs, followed_tenders,
    get_db, now, reset_db, saved_search_seen, saved_searches, tags,
    tender_source_documents, user_notifications, users)
from server.intelligence import ingest_row


class AutomationConditionTests(unittest.TestCase):
    def test_text_number_date_boolean_and_nested_groups(self):
        entity = {"title": "Mua Thiết Bị Y Tế", "location": "TP.HCM",
                  "package_price": "500000000", "bid_closing_date": "2026-09-30",
                  "is_followed": True}
        nested = validate_group({"logic": "OR", "items": [
            {"logic": "AND", "items": [
                {"field": "title", "operator": "contains", "value": "thiết bị"},
                {"field": "package_price", "operator": "greater_or_equal", "value": "500000000"},
                {"field": "location", "operator": "equals", "value": "tp.hcm"}]},
            {"field": "is_followed", "operator": "is_not", "value": True}]})
        self.assertTrue(evaluate_group(entity, nested))
        self.assertTrue(evaluate_condition(entity, validate_condition({
            "field": "bid_closing_date", "operator": "within_days", "value": 3}),
            today=date(2026, 9, 28)))
        self.assertFalse(evaluate_condition(entity, validate_condition({
            "field": "bid_closing_date", "operator": "before", "value": "2026-09-20"})))
        with self.assertRaises(ValueError):
            validate_condition({"field": "package_price", "operator": "contains", "value": "500"})
        with self.assertRaises(ValueError):
            validate_condition({"field": "title", "operator": "eval", "value": "x"})


class AutomationFlowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
            (Path(self.folder.name) / "automation.db").as_posix(), "ENV": "development"})
        self.env.start()
        reset_db()
        self.a, self.b = "a" * 32, "b" * 32
        with get_db().engine.begin() as conn:
            for user_id in (self.a, self.b):
                conn.execute(insert(users).values(id=user_id, email=user_id + "@example.test",
                    password_hash="test", role="user", created_at=now(), updated_at=now(),
                    last_login_at=None, is_active=True))

    def tearDown(self):
        reset_db()
        self.env.stop()
        self.folder.cleanup()

    def _rule(self, **overrides):
        body = {"name": "Thiết bị y tế TP.HCM", "trigger_type": "NEW_TENDER",
            "run_frequency": "manual", "conditions": {"logic": "AND", "items": [
                {"field": "title", "operator": "contains", "value": "thiết bị"},
                {"field": "location", "operator": "equals", "value": "TP.HCM"},
                {"field": "package_price", "operator": "greater_or_equal",
                 "value": "500000000"}]},
            "actions": [{"type": "FOLLOW_TENDER"},
                        {"type": "SET_PRIORITY", "value": "Cao"},
                        {"type": "ADD_TAG", "value": "Y tế"},
                        {"type": "CREATE_NOTIFICATION"}]}
        return save_rule(self.a, body | overrides)

    def test_preview_run_dedup_and_isolation(self):
        rule = self._rule()
        ingest_row(ResultRow(notify_no="IB2600999999", package_name="Thiết bị y tế",
            location="TP.HCM", package_price="500.000.000 VND",
            investor_name="Bệnh viện A"))
        preview = run_rule(self.a, rule["id"], dry_run=True)
        self.assertEqual(preview["matched_count"], 1)
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(followed_tenders)), 0)
        result = run_rule(self.a, rule["id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["action_count"], 4)
        self.assertEqual([item["id"] for item in list_rules(self.a, last_run="7d")],
                         [rule["id"]])
        repeated = run_rule(self.a, rule["id"])
        self.assertEqual(repeated["action_count"], 0)
        with get_db().engine.connect() as conn:
            follows = conn.execute(select(followed_tenders)).mappings().all()
            self.assertEqual(len(follows), 1)
            self.assertEqual(follows[0]["user_id"], self.a)
            self.assertEqual(follows[0]["priority"], "Cao")
            self.assertEqual(follows[0]["payload"]["tags"], ["Y tế"])
            self.assertEqual(conn.scalar(select(func.count()).select_from(tags)), 1)
            self.assertEqual(conn.scalar(select(func.count()).select_from(user_notifications)), 1)
            self.assertEqual(conn.scalar(select(func.count()).select_from(automation_events)), 4)
        self.assertEqual(len(list_runs(self.a, rule["id"])), 2)
        self.assertEqual(len(list_events(self.a, result["id"])), 4)
        analytics = automation_analytics(self.a)
        self.assertEqual(sum(item["runs"] for item in analytics["trend"]), 2)
        self.assertEqual(sum(item["count"] for item in analytics["actions"]), 4)
        self.assertEqual(automation_analytics(self.b)["trend"], [])
        self.assertEqual(list_rules(self.b), [])
        with self.assertRaises(LookupError):
            run_rule(self.b, rule["id"])
        with self.assertRaises(LookupError):
            list_events(self.b, result["id"])

    def test_pause_duplicate_delete_and_validation(self):
        rule = self._rule()
        self.assertFalse(rule["is_enabled"])
        self.assertTrue(set_enabled(self.a, rule["id"], True)["is_enabled"])
        self.assertFalse(set_enabled(self.a, rule["id"], False)["is_enabled"])
        copy = duplicate_rule(self.a, rule["id"])
        self.assertNotEqual(copy["id"], rule["id"])
        self.assertFalse(copy["is_enabled"])
        self.assertTrue(delete_rule(self.a, rule["id"]))
        self.assertIsNone(get_rule(self.a, rule["id"]))
        self.assertEqual(len(list_rules(self.a)), 1)
        with self.assertRaises(ValueError):
            self._rule(actions=[{"type": "EMAIL", "value": "x@example.test"}])

    def test_manual_rules_stay_out_of_scheduler_and_edit_resets_scan(self):
        rule = self._rule(is_enabled=True)
        self.assertIsNone(rule["next_run_at"])
        self.assertEqual(run_due_automations()["rules"], 0)
        with self.assertRaises(ValueError):
            self._rule(trigger_type="MANUAL_RUN", run_frequency="hourly")
        ingest_row(ResultRow(notify_no="IB2600999998", package_name="Thiết bị y tế",
            location="TP.HCM", package_price="500.000.000 VND"))
        run_rule(self.a, rule["id"])
        self.assertIsNotNone(get_rule(self.a, rule["id"])["last_run_at"])
        original = get_rule(self.a, rule["id"])
        updated = save_rule(self.a, {"name": original["name"],
            "trigger_type": original["trigger_type"], "run_frequency": "manual",
            "conditions": original["conditions_json"],
            "actions": [{"type": "CREATE_NOTIFICATION"}]}, rule["id"])
        self.assertIsNone(updated["last_run_at"])
        self.assertIsNone(updated["next_run_at"])

    def test_new_document_trigger_uses_source_document_event(self):
        rule = self._rule(trigger_type="NEW_DOCUMENT",
            conditions={"logic": "AND", "items": []},
            actions=[{"type": "CREATE_NOTIFICATION"}])
        ingest_row(ResultRow(notify_no="IB2600999997", package_name="Gói tài liệu"))
        with get_db().engine.begin() as conn:
            conn.execute(insert(tender_source_documents).values(id="d" * 32,
                tender_code="IB2600999997", document_name="Hồ sơ mời thầu",
                source_url="https://example.test/document/1", document_group_id="g" * 32,
                version=1, first_seen_at=now(), last_seen_at=now()))
        self.assertEqual(run_rule(self.a, rule["id"])["action_count"], 1)
        self.assertEqual(run_rule(self.a, rule["id"])["action_count"], 0)

    def test_document_check_action_queues_once(self):
        rule = self._rule(conditions={"logic": "AND", "items": []},
            actions=[{"type": "QUEUE_DOCUMENT_CHECK"}])
        ingest_row(ResultRow(notify_no="IB2600999994", package_name="Gói cần kiểm tra"))
        self.assertEqual(run_rule(self.a, rule["id"])["action_count"], 1)
        self.assertEqual(run_rule(self.a, rule["id"])["action_count"], 0)
        with get_db().engine.connect() as conn:
            queued = conn.execute(select(background_jobs)).mappings().all()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["entity_id"], "IB2600999994")
        self.assertEqual(queued[0]["status"], "pending")

    def test_large_kqlcnt_batch_advances_cursor_without_starvation(self):
        rule = self._rule(trigger_type="KQLCNT_AVAILABLE",
            run_frequency="hourly", is_enabled=True,
            conditions={"logic": "AND", "items": []},
            actions=[{"type": "CREATE_NOTIFICATION"}])
        for index in range(3):
            ingest_row(ResultRow(notify_no=f"IB260088880{index}",
                package_name=f"Gói {index}", winner=f"Nhà thầu {index}"))
        with patch("server.automation_engine.MAX_CANDIDATES", 2):
            first = run_rule(self.a, rule["id"])
            self.assertEqual(first["status"], "partial")
            self.assertTrue(first["truncated"])
            self.assertEqual(first["action_count"], 2)
            self.assertIsNotNone(get_rule(self.a, rule["id"])["cursor_json"])
            second = run_rule(self.a, rule["id"])
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["action_count"], 1)
        self.assertIsNone(get_rule(self.a, rule["id"])["cursor_json"])
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(user_notifications)), 3)

    def test_saved_search_trigger_is_limited_to_owner(self):
        rule = self._rule(trigger_type="SAVED_SEARCH_MATCH",
            conditions={"logic": "AND", "items": [{"field": "saved_search",
                "operator": "equals", "value": "Y tế"}]},
            actions=[{"type": "CREATE_NOTIFICATION"}])
        ingest_row(ResultRow(notify_no="IB2600999996", package_name="Gói y tế"))
        with get_db().engine.begin() as conn:
            for user_id, search_id in [(self.a, "c" * 32), (self.b, "e" * 32)]:
                conn.execute(insert(saved_searches).values(id=search_id,
                    user_id=user_id, name="Y tế", query="y tế", filters={},
                    is_watch_enabled=True, pinned=False, created_at=now(),
                    updated_at=now()))
                conn.execute(insert(saved_search_seen).values(search_id=search_id,
                    tender_code="IB2600999996"))
        self.assertEqual(run_rule(self.a, rule["id"])["action_count"], 1)
        self.assertEqual(run_rule(self.a, rule["id"])["action_count"], 0)

    def test_one_failed_action_does_not_erase_successful_action(self):
        rule = self._rule(conditions={"logic": "AND", "items": []},
            actions=[{"type": "FOLLOW_TENDER"}, {"type": "ADD_TAG", "value": "Y tế"}])
        self.assertEqual([item["id"] for item in list_rules(self.a, status="never")],
                         [rule["id"]])
        ingest_row(ResultRow(notify_no="IB2600999995", package_name="Gói y tế"))
        from server.automation_actions import execute_action as real_action

        def partly_failing(conn, user_id, entity, action, rule_name):
            if action["type"] == "ADD_TAG":
                raise ValueError("Tag không hợp lệ trong lượt này.")
            return real_action(conn, user_id, entity, action, rule_name)

        with patch("server.automation_engine.execute_action", side_effect=partly_failing):
            result = run_rule(self.a, rule["id"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["action_count"], 1)
        events = list_events(self.a, result["id"])
        self.assertEqual([event["status"] for event in events], ["completed", "failed"])
        self.assertEqual([item["id"] for item in list_rules(self.a, status="error")],
                         [rule["id"]])
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(func.count()).select_from(followed_tenders)), 1)
        retry = run_rule(self.a, rule["id"])
        self.assertEqual(retry["action_count"], 1)
        self.assertEqual(list_rules(self.a, status="error"), [])


if __name__ == "__main__":
    unittest.main()
