import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import insert, select, update

from server.auth import register
from server.data_quality.normalization import normalized_text
from server.data_quality.service import (list_duplicates, list_issues, process_scan_batch,
    queue_scan, review_issue, summary, fix_safe_whitespace, revert_safe_fix,
    issue_detail, merge_duplicate)
from server.data_quality.validators import validate_tender, validate_document, validate_plan
from server.database import (contractors, data_quality_issues, get_db, now, reset_db,
    entity_aliases, entity_merges, investors, plans, source_health_events,
    tender_snapshots, tender_source_documents, tenders)


class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" +
            (Path(self.folder.name) / "quality.db").as_posix(),
            "DATA_QUALITY_BATCH_SIZE": "10", "STALE_TENDER_DAYS": "14"})
        self.env.start()
        reset_db()
        self.admin = register("quality@example.test", "safe-long-password-123")["id"]

    def tearDown(self):
        reset_db()
        self.env.stop()
        self.folder.cleanup()

    def tender(self, code="IB2600123456", **fields):
        row = dict(tender_code=code, title="", first_seen_at=now(), last_seen_at=now(),
                   sync_status="stale")
        row.update(fields)
        with get_db().engine.begin() as conn:
            conn.execute(insert(tenders).values(**row))

    def scan_all(self):
        queue_scan("full")
        for _ in range(20):
            result = process_scan_batch()
            if result["status"] == "completed":
                return result
        self.fail("Quality scan did not finish")

    def test_validation_dedup_and_auto_resolution(self):
        self.tender(publish_date="2026-09-20T09:00:00+07:00",
                    bid_closing_date="2026-09-19T09:00:00+07:00",
                    package_price=-1)
        self.scan_all()
        rules = {item["rule_code"] for item in list_issues()["items"]}
        self.assertEqual(summary()["tenders_with_valid_price"], 0)
        self.assertTrue({"TENDER_MISSING_TITLE", "TENDER_INVALID_PRICE",
                         "TENDER_DEADLINE_BEFORE_PUBLISH"}.issubset(rules))
        count = summary()["open"]
        self.scan_all()
        self.assertEqual(summary()["open"], count)
        with get_db().engine.begin() as conn:
            conn.execute(update(tenders).where(tenders.c.tender_code == "IB2600123456")
                .values(title="Gói đã sửa", package_price=100,
                        bid_closing_date="2026-09-21T09:00:00+07:00"))
        self.scan_all()
        self.assertEqual(summary()["open"], count - 3)
        self.assertGreaterEqual(summary()["resolved"], 3)

    def test_review_is_audited_and_source_is_untouched(self):
        self.tender()
        self.scan_all()
        item = list_issues()["items"][0]
        self.assertEqual(issue_detail(item["id"])["issue"]["id"], item["id"])
        result = review_issue(item["id"], "ignore", self.admin)
        self.assertEqual(result["status"], "ignored")
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(tenders.c.title)), "")
        self.scan_all()
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(data_quality_issues.c.status).where(
                data_quality_issues.c.id == item["id"])), "ignored")

    def test_duplicate_candidate_requires_strong_identifier(self):
        stamp = now()
        with get_db().engine.begin() as conn:
            for index, name in enumerate(("Công ty A", "Cong ty A")):
                conn.execute(insert(contractors).values(id=f"{index+1:032x}", name=name,
                    normalized_name=normalized_text(name), identity_key=f"key-{index}",
                    tax_code="0123456789", first_seen_at=stamp, last_seen_at=stamp))
        self.scan_all()
        self.assertEqual(list_duplicates()["total"], 1)
        self.scan_all()
        self.assertEqual(list_duplicates()["total"], 1)

    def test_admin_approved_whitespace_fix_is_reversible(self):
        self.tender(title="  Gói   thiết bị  ")
        self.scan_all()
        issue = next(item for item in list_issues()["items"]
                     if item["rule_code"] == "TENDER_EXTRA_WHITESPACE")
        change = fix_safe_whitespace(issue["id"], self.admin)
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(tenders.c.title)), "Gói thiết bị")
        self.assertTrue(revert_safe_fix(change["fix_id"], self.admin)["restored"])
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(tenders.c.title)), "  Gói   thiết bị  ")

    def test_pure_rules_cover_invalid_code_date_encoding_and_partial(self):
        issues = validate_tender({"tender_code": "bad", "title": "\ufffd",
            "publish_date": "not-a-date", "investor_name": None,
            "procuring_entity_name": None})
        codes = {issue["rule_code"] for issue in issues}
        self.assertTrue({"TENDER_INVALID_CODE", "TENDER_INVALID_DATE",
                         "INVALID_ENCODING", "PARTIAL_DATA"}.issubset(codes))
        self.assertEqual(normalized_text(" Công   ty  A "), normalized_text("Công ty A"))

    def test_stale_and_document_hash_validation(self):
        current = datetime(2026, 9, 30, tzinfo=timezone.utc)
        tender_rules = {item["rule_code"] for item in validate_tender({
            "tender_code": "IB2600123456", "title": "Gói thầu",
            "last_success_at": "2026-09-01T00:00:00+00:00"}, current=current)}
        document_rules = {item["rule_code"] for item in validate_document({
            "content_hash": "not-sha256", "status": "failed",
            "last_seen_at": "2026-08-01T00:00:00+00:00"}, current=current)}
        self.assertIn("TENDER_STALE", tender_rules)
        self.assertTrue({"DOCUMENT_INVALID_HASH", "DOCUMENT_FAILED",
                         "DOCUMENT_STALE"}.issubset(document_rules))

    def test_plan_validation_scan_and_score(self):
        from server.data_quality.service import entity_status
        with get_db().engine.begin() as conn:
            conn.execute(insert(plans).values(plan_code="PL2600123456", title="",
                package_price=-10, publish_date="invalid", first_seen_at=now(), last_seen_at=now()))
        self.scan_all()
        codes = {item["rule_code"] for item in list_issues(entity_type="plan")["items"]}
        self.assertTrue({"PLAN_MISSING_TITLE", "PLAN_INVALID_PRICE", "PLAN_INVALID_DATE"}.issubset(codes))
        self.assertEqual(entity_status("plan", "PL2600123456")["status"], "error")
        self.assertIn("PLAN_INVALID_CODE", {item["rule_code"] for item in
            validate_plan({"plan_code": "bad", "title": "Kế hoạch"})})

    def test_manual_merge_preserves_source_and_reassigns_relations(self):
        stamp = now()
        left, right = "1" * 32, "2" * 32
        with get_db().engine.begin() as conn:
            for entity_id, name in ((left, "Bệnh viện A"), (right, "Benh vien A")):
                conn.execute(insert(investors).values(id=entity_id, name=name,
                    normalized_name=normalized_text(name), search_text=normalized_text(name),
                    identifier="0123456789", first_seen_at=stamp, last_seen_at=stamp))
            conn.execute(insert(plans).values(plan_code="PL2600123456", title="Kế hoạch",
                investor_id=right, first_seen_at=stamp, last_seen_at=stamp))
            conn.execute(insert(tenders).values(tender_code="IB2600123456", title="Gói",
                investor_id=right, first_seen_at=stamp, last_seen_at=stamp))
        self.scan_all()
        candidate = next(item for item in list_duplicates()["items"] if item["entity_type"] == "investor")
        result = merge_duplicate(candidate["id"], left, self.admin)
        self.assertEqual(result["target_id"], left)
        with get_db().engine.connect() as conn:
            self.assertEqual(conn.scalar(select(plans.c.investor_id)), left)
            self.assertEqual(conn.scalar(select(tenders.c.investor_id)), left)
            self.assertEqual(conn.scalar(select(investors.c.name).where(investors.c.id == right)), "Benh vien A")
            self.assertEqual(conn.scalar(select(entity_merges.c.source_id)), right)
            self.assertEqual(conn.scalar(select(entity_aliases.c.alias)), "Benh vien A")
        from server.intelligence import _entity
        with get_db().engine.begin() as conn:
            self.assertEqual(_entity(conn, investors, "Benh vien A", now()), left)
        from server.search_engine import search
        matches = search(q="Benh vien A", kind="investor")
        self.assertEqual(matches["total"], 1)
        self.assertEqual(matches["items"][0]["code"], left)
        with self.assertRaises(LookupError):
            merge_duplicate(candidate["id"], right, self.admin)

    def test_source_schema_alert_resolves_after_recovery(self):
        with get_db().engine.begin() as conn:
            conn.execute(insert(source_health_events).values(id="a" * 32,
                source_name="egp-public", event_type="status_transition",
                status="Unavailable", details_json={"error_code": "schema_changed"},
                created_at=now()))
        self.scan_all()
        self.assertIn("SOURCE_SCHEMA_CHANGE", {row["rule_code"] for row in
            list_issues(entity_type="source")["items"]})
        with get_db().engine.begin() as conn:
            conn.execute(insert(source_health_events).values(id="b" * 32,
                source_name="egp-public", event_type="status_transition",
                status="Healthy", details_json={"error_code": ""},
                created_at=now()))
        self.scan_all()
        self.assertEqual(list_issues(entity_type="source")["total"], 0)

    def test_cache_snapshot_conflict_is_evidence_based(self):
        self.tender(title="Gói", package_price=200, raw_hash="a" * 64)
        with get_db().engine.begin() as conn:
            conn.execute(insert(tender_snapshots).values(id="d" * 32,
                tender_code="IB2600123456", snapshot_json={"package_price": "100.00"},
                snapshot_hash="a" * 64, version=1, created_at=now()))
        self.scan_all()
        issues = [item for item in list_issues()["items"] if item["rule_code"] == "SOURCE_CONFLICT"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["field_name"], "package_price")
        with get_db().engine.begin() as conn:
            conn.execute(update(tenders).values(package_price=100))
        self.scan_all()
        self.assertFalse(any(item["rule_code"] == "SOURCE_CONFLICT" for item in list_issues()["items"]))

    def test_merge_rejects_identifier_mismatch(self):
        stamp = now()
        from server.database import duplicate_candidates
        with get_db().engine.begin() as conn:
            for index, tax in ((1, "111"), (2, "222")):
                conn.execute(insert(contractors).values(id=f"{index:032x}", name=f"Công ty {index}",
                    normalized_name=f"company {index}", identity_key=f"tax:{tax}",
                    tax_code=tax, first_seen_at=stamp, last_seen_at=stamp))
            conn.execute(insert(duplicate_candidates).values(id="c" * 32,
                entity_type="contractor", entity_id_a=f"{1:032x}",
                entity_id_b=f"{2:032x}", confidence=.99,
                reason_json={}, status="pending", created_at=stamp))
        with self.assertRaises(ValueError):
            merge_duplicate("c" * 32, f"{1:032x}", self.admin)


if __name__ == "__main__":
    unittest.main()
