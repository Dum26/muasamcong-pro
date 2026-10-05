"""Durable, bounded data-quality scans and admin review actions."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, func, insert, or_, select, update

from server.data_quality.rules import RULES, settings
from server.data_quality.validators import validate_document, validate_plan, validate_tender
from server.database import (audit_logs, contractors, data_quality_issues, data_quality_runs,
    data_fix_log, duplicate_candidates, entity_aliases, entity_merges, get_db, investors, now, plans, procuring_entities,
    source_health_events, tender_source_documents, tenders)
from server.database import tender_snapshots
from server.data_quality.normalization import safe_display_text
from server.data_quality.normalization import normalized_text

ACTIVE = ("open", "reviewing")
TABLES = (("tender", tenders, "tender_code"),
          ("plan", plans, "plan_code"),
          ("document", tender_source_documents, "id"))


def _identity(entity_type: str, entity_id: str, rule_code: str, field: str | None) -> str:
    return hashlib.sha256("\0".join((entity_type, entity_id, rule_code, field or "")).encode()).hexdigest()


def _sync_issues(conn, entity_type: str, entity_id: str, observed: list[dict], stamp: str) -> tuple[int, int]:
    keys = set()
    found = resolved = 0
    for issue in observed:
        if issue["rule_code"] not in RULES:
            raise ValueError("Unknown quality rule")
        key = _identity(entity_type, entity_id, issue["rule_code"], issue.get("field_name"))
        keys.add(key)
        old = conn.execute(select(data_quality_issues).where(
            data_quality_issues.c.identity_key == key)).mappings().first()
        if old:
            status = old["status"] if old["status"] in {"ignored", "reviewing"} else "open"
            conn.execute(update(data_quality_issues).where(data_quality_issues.c.id == old["id"])
                .values(status=status, severity=issue["severity"], message=issue["message"],
                        details_json=issue["details_json"], last_detected_at=stamp,
                        resolved_at=None if status in ACTIVE else old["resolved_at"],
                        updated_at=stamp))
        else:
            conn.execute(insert(data_quality_issues).values(id=uuid.uuid4().hex,
                identity_key=key, entity_type=entity_type, entity_id=entity_id,
                field_name=issue.get("field_name"), rule_code=issue["rule_code"],
                severity=issue["severity"], status="open", message=issue["message"],
                details_json=issue["details_json"], detected_at=stamp,
                last_detected_at=stamp, created_at=stamp, updated_at=stamp))
        found += 1
    previous = conn.execute(select(data_quality_issues.c.id, data_quality_issues.c.identity_key)
        .where(data_quality_issues.c.entity_type == entity_type,
               data_quality_issues.c.entity_id == entity_id,
               data_quality_issues.c.status.in_(ACTIVE))).all()
    for issue_id, key in previous:
        if key not in keys:
            conn.execute(update(data_quality_issues).where(data_quality_issues.c.id == issue_id)
                .values(status="auto_resolved", resolved_at=stamp,
                        resolution_type="no_longer_detected", updated_at=stamp))
            resolved += 1
    return found, resolved


def queue_scan(run_type: str = "incremental") -> dict:
    if run_type not in {"incremental", "full"}:
        raise ValueError("Chế độ quét không hợp lệ.")
    if not settings()["enabled"]:
        raise ValueError("Data Quality Engine đang tắt.")
    with get_db().engine.begin() as conn:
        active = conn.execute(select(data_quality_runs).where(
            data_quality_runs.c.status.in_(("queued", "running")))
            .order_by(data_quality_runs.c.created_at).limit(1)).mappings().first()
        if active:
            return dict(active)
        since = conn.scalar(select(func.max(data_quality_runs.c.finished_at)).where(
            data_quality_runs.c.status == "completed")) if run_type == "incremental" else None
        stamp = now()
        record = dict(id=uuid.uuid4().hex, run_type=run_type, status="queued",
            cursor_json={"stage": 0, "last": "", "since": since},
            entities_scanned=0, issues_found=0, issues_resolved=0,
            created_at=stamp, started_at=None, finished_at=None)
        conn.execute(insert(data_quality_runs).values(**record))
        return record


def _tender_extra(conn, row: dict) -> list[dict]:
    issues = []
    for field, table, key in (("khlcnt_code", plans, "plan_code"),
                              ("investor_id", investors, "id"),
                              ("procuring_entity_id", procuring_entities, "id"),
                              ("contractor_id", contractors, "id")):
        value = row.get(field)
        if value and not conn.scalar(select(table.c[key]).where(table.c[key] == value)):
            issues.append({"rule_code": "BROKEN_RELATION", "field_name": field,
                "severity": "critical", "message": f"{field} không có bản ghi liên kết.",
                "details_json": {"referenced_id": str(value)}})
    if row.get("raw_hash"):
        snapshot = conn.execute(select(tender_snapshots.c.snapshot_json,
            tender_snapshots.c.snapshot_hash, tender_snapshots.c.version).where(
            tender_snapshots.c.tender_code == row["tender_code"])
            .order_by(tender_snapshots.c.version.desc()).limit(1)).mappings().first()
        if snapshot and snapshot["snapshot_hash"] == row["raw_hash"]:
            for field in ("package_price", "publish_date", "bid_closing_date", "status"):
                cached = row.get(field)
                observed = (snapshot["snapshot_json"] or {}).get(field)
                if field == "package_price" and cached is not None and observed is not None:
                    try:
                        different = Decimal(str(cached)) != Decimal(str(observed))
                    except (InvalidOperation, ValueError):
                        different = str(cached) != str(observed)
                else:
                    different = str(cached) != str(observed)
                if cached is not None and observed is not None and different:
                    issues.append({"rule_code": "SOURCE_CONFLICT", "field_name": field,
                        "severity": "warning", "message": f"{field} khác snapshot nguồn v{snapshot['version']}.",
                        "details_json": {"cache": str(cached), "snapshot": str(observed),
                                         "snapshot_version": snapshot["version"]}})
    return issues


def _document_extra(conn, row: dict) -> list[dict]:
    issues = []
    if not conn.scalar(select(tenders.c.tender_code).where(
            tenders.c.tender_code == row["tender_code"])):
        issues.append({"rule_code": "DOCUMENT_ORPHAN", "field_name": "tender_code",
            "severity": "error", "message": "Không có gói thầu liên quan.",
            "details_json": {"tender_code": row["tender_code"]}})
    digest = row.get("content_hash")
    if digest and conn.scalar(select(func.count()).select_from(tender_source_documents).where(
            tender_source_documents.c.tender_code == row["tender_code"],
            tender_source_documents.c.content_hash == digest)) > 1:
        issues.append({"rule_code": "DOCUMENT_DUPLICATE", "field_name": "content_hash",
            "severity": "info", "message": "Nhiều file cùng gói có cùng SHA-256; cần kiểm tra nguồn.",
            "details_json": {"sha256": digest}})
    return issues


def _plan_extra(conn, row: dict) -> list[dict]:
    investor_id = row.get("investor_id")
    if investor_id and not conn.scalar(select(investors.c.id).where(investors.c.id == investor_id)):
        return [{"rule_code": "PLAN_BROKEN_RELATION", "field_name": "investor_id",
                 "severity": "critical", "message": "Chủ đầu tư liên kết không tồn tại.",
                 "details_json": {"referenced_id": investor_id}}]
    return []


def _candidate_pairs(conn, table, kind: str, identifier: str) -> int:
    rows = conn.execute(select(table.c.id, table.c.name, table.c[identifier], table.c.address)
        .where(table.c[identifier].is_not(None), table.c[identifier] != "")
        .order_by(table.c[identifier], table.c.id).limit(10000)).mappings().all()
    by_identifier: dict[str, list[dict]] = {}
    for row in rows:
        if conn.scalar(select(entity_merges.c.id).where(entity_merges.c.entity_type == kind,
                entity_merges.c.source_id == row["id"])):
            continue
        by_identifier.setdefault(str(row[identifier]).strip().casefold(), []).append(row)
    created = 0
    for key, group in by_identifier.items():
        if len(group) < 2 or not key:
            continue
        if settings()["duplicate_confidence"] > .99:
            continue
        for left in group[:20]:
            for right in group[:20]:
                if left["id"] >= right["id"]:
                    continue
                exists = conn.scalar(select(duplicate_candidates.c.id).where(
                    duplicate_candidates.c.entity_type == kind,
                    duplicate_candidates.c.entity_id_a == left["id"],
                    duplicate_candidates.c.entity_id_b == right["id"]))
                if not exists:
                    conn.execute(insert(duplicate_candidates).values(id=uuid.uuid4().hex,
                        entity_type=kind, entity_id_a=left["id"], entity_id_b=right["id"],
                        confidence=.99, reason_json={"matching_field": identifier,
                            "identifier": key}, status="pending", created_at=now()))
                    created += 1
    return created


def _scan_source_health(conn, stamp: str) -> tuple[int, int]:
    sources = conn.execute(select(source_health_events.c.source_name).distinct()).scalars().all()
    found = resolved = 0
    for source in sources:
        latest = conn.execute(select(source_health_events).where(
            source_health_events.c.source_name == source)
            .order_by(source_health_events.c.created_at.desc(), source_health_events.c.id.desc())
            .limit(1)).mappings().first()
        details = latest["details_json"] or {}
        code = details.get("error_code", "")
        observed = []
        if latest["status"] in {"Degraded", "Unavailable"}:
            rule = "SOURCE_SCHEMA_CHANGE" if code in {"schema_changed", "invalid_json", "invalid_response"} else "SOURCE_DEGRADED"
            observed.append({"rule_code": rule, "field_name": "status",
                "severity": RULES[rule].severity,
                "message": "Nguồn có thể đổi cấu trúc phản hồi." if rule == "SOURCE_SCHEMA_CHANGE" else
                    "Nguồn dữ liệu đang suy giảm; cần kiểm tra đồng bộ.",
                "details_json": {"status": latest["status"], "error_code": code,
                                 "event_id": latest["id"]}})
        a, b = _sync_issues(conn, "source", source, observed, stamp)
        found += a
        resolved += b
    return found, resolved


def process_scan_batch() -> dict:
    """Run at most one bounded batch; safe for Cloud Scheduler and Cloud Run."""
    if not settings()["enabled"]:
        return {"status": "disabled"}
    batch_size = settings()["batch_size"]
    with get_db().engine.begin() as conn:
        run = conn.execute(select(data_quality_runs).where(
            data_quality_runs.c.status.in_(("queued", "running")))
            .order_by(data_quality_runs.c.created_at).limit(1)
            .with_for_update(skip_locked=True)).mappings().first()
        if not run:
            return {"status": "idle"}
        cursor = dict(run["cursor_json"] or {})
        stage = int(cursor.get("stage", 0))
        stamp = now()
        if stage >= len(TABLES):
            source_found, source_resolved = _scan_source_health(conn, stamp)
            _candidate_pairs(conn, contractors, "contractor", "tax_code")
            _candidate_pairs(conn, investors, "investor", "identifier")
            _candidate_pairs(conn, procuring_entities, "procuring_entity", "identifier")
            conn.execute(update(data_quality_runs).where(data_quality_runs.c.id == run["id"])
                .values(status="completed", finished_at=stamp,
                    issues_found=run["issues_found"] + source_found,
                    issues_resolved=run["issues_resolved"] + source_resolved))
            return {"id": run["id"], "status": "completed"}
        kind, table, key = TABLES[stage]
        conditions = [table.c[key] > cursor.get("last", "")]
        if run["run_type"] == "incremental" and cursor.get("since"):
            conditions.append(table.c.last_seen_at >= cursor["since"])
        rows = conn.execute(select(table).where(*conditions)
            .order_by(table.c[key]).limit(batch_size)).mappings().all()
        found = resolved = 0
        for raw in rows:
            row = dict(raw)
            observed = (validate_tender(row) + _tender_extra(conn, row) if kind == "tender"
                        else validate_plan(row) + _plan_extra(conn, row) if kind == "plan"
                        else validate_document(row) + _document_extra(conn, row))
            a, b = _sync_issues(conn, kind, str(row[key]), observed, stamp)
            found += a
            resolved += b
        if len(rows) < batch_size:
            cursor.update(stage=stage + 1, last="")
        else:
            cursor["last"] = str(rows[-1][key])
        conn.execute(update(data_quality_runs).where(data_quality_runs.c.id == run["id"])
            .values(status="running", started_at=run["started_at"] or stamp,
                cursor_json=cursor, entities_scanned=run["entities_scanned"] + len(rows),
                issues_found=run["issues_found"] + found,
                issues_resolved=run["issues_resolved"] + resolved))
        return {"id": run["id"], "status": "running", "stage": kind,
                "scanned": len(rows), "issues_found": found, "issues_resolved": resolved}


def summary() -> dict:
    with get_db().engine.connect() as conn:
        count = lambda *where: conn.scalar(select(func.count()).select_from(data_quality_issues).where(*where)) or 0
        latest = conn.execute(select(data_quality_runs).order_by(
            data_quality_runs.c.created_at.desc()).limit(1)).mappings().first()
        total_entities = sum((conn.scalar(select(func.count()).select_from(table)) or 0)
                             for _, table, _ in TABLES)
        tender_total = conn.scalar(select(func.count()).select_from(tenders)) or 0
        priced_tenders = conn.scalar(select(func.count()).select_from(tenders).where(
            tenders.c.package_price.is_not(None), tenders.c.package_price >= 0)) or 0
        affected = conn.scalar(select(func.count(func.distinct(
            data_quality_issues.c.entity_type + ":" + data_quality_issues.c.entity_id))).where(
            data_quality_issues.c.status.in_(ACTIVE))) or 0
        full_scan = conn.scalar(select(func.max(data_quality_runs.c.finished_at)).where(
            data_quality_runs.c.run_type == "full", data_quality_runs.c.status == "completed"))
        return {"open": count(data_quality_issues.c.status.in_(ACTIVE)),
                "critical": count(data_quality_issues.c.status.in_(ACTIVE), data_quality_issues.c.severity == "critical"),
                "warnings": count(data_quality_issues.c.status.in_(ACTIVE), data_quality_issues.c.severity == "warning"),
                "resolved": count(data_quality_issues.c.status.in_(("resolved", "auto_resolved"))),
                "new_24h": count(data_quality_issues.c.detected_at >=
                    (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds"),
                    data_quality_issues.c.status.in_(ACTIVE)),
                "stale": count(data_quality_issues.c.status.in_(ACTIVE),
                    data_quality_issues.c.rule_code.in_(("TENDER_STALE", "PLAN_STALE", "DOCUMENT_STALE"))),
                "source_alerts": count(data_quality_issues.c.status.in_(ACTIVE),
                    data_quality_issues.c.rule_code.in_(("SOURCE_SCHEMA_CHANGE", "SOURCE_DEGRADED"))),
                "broken_relations": count(data_quality_issues.c.status.in_(ACTIVE),
                    data_quality_issues.c.rule_code.in_(("BROKEN_RELATION", "DOCUMENT_ORPHAN"))),
                "total_entities": total_entities,
                "tenders_with_valid_price": priced_tenders,
                "tender_count": tender_total,
                "records_without_open_issues_pct": (round(100 * max(total_entities - affected, 0) / total_entities)
                    if total_entities and full_scan else None),
                "duplicates_pending": conn.scalar(select(func.count()).select_from(duplicate_candidates)
                    .where(duplicate_candidates.c.status == "pending")) or 0,
                "latest_run": dict(latest) if latest else None}


def run_history(limit: int = 20) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("Giới hạn lịch sử không hợp lệ.")
    with get_db().engine.connect() as conn:
        rows = conn.execute(select(data_quality_runs).order_by(
            data_quality_runs.c.created_at.desc()).limit(limit)).mappings().all()
    return {"items": [dict(row) for row in rows]}


def entity_status(entity_type: str, entity_id: str) -> dict:
    if entity_type not in {"tender", "plan", "document"} or len(entity_id) > 100:
        raise ValueError("Đối tượng không hợp lệ.")
    table, key = {"tender": (tenders, "tender_code"), "plan": (plans, "plan_code"),
                  "document": (tender_source_documents, "id")}[entity_type]
    with get_db().engine.connect() as conn:
        row = conn.execute(select(table).where(table.c[key] == entity_id)).mappings().first()
        if not row:
            raise LookupError("Không tìm thấy dữ liệu.")
        issues = conn.execute(select(data_quality_issues.c.rule_code,
            data_quality_issues.c.severity, data_quality_issues.c.message).where(
            data_quality_issues.c.entity_type == entity_type,
            data_quality_issues.c.entity_id == entity_id,
            data_quality_issues.c.status.in_(ACTIVE)).order_by(
            data_quality_issues.c.severity.desc()).limit(20)).mappings().all()
        full_scan_finished = conn.scalar(select(func.max(data_quality_runs.c.finished_at)).where(
            data_quality_runs.c.status == "completed", data_quality_runs.c.run_type == "full"))
    fields = ("title", "status", "publish_date", "investor_name",
              "procuring_entity_name", "bid_closing_date") if entity_type == "tender" else (
              "title", "investor_name", "publish_date", "source_url") if entity_type == "plan" else (
              "document_name", "source_url", "document_type", "published_at")
    present = sum(bool(row.get(field)) for field in fields)
    completeness = round(100 * present / len(fields))
    checked = bool(issues) or bool(full_scan_finished and
        str(row.get("last_seen_at") or "") <= full_scan_finished)
    validity = max(0, 100 - sum({"critical": 35, "error": 25,
        "warning": 10, "info": 3}.get(item["severity"], 0) for item in issues))
    freshness = 0 if any(item["rule_code"] in {"TENDER_STALE", "PLAN_STALE", "DOCUMENT_STALE"}
                         for item in issues) else 100
    consistency = 50 if any(item["rule_code"] in {"BROKEN_RELATION", "DOCUMENT_DUPLICATE"}
                            for item in issues) else 100
    breakdown = {"completeness": completeness, "validity": validity,
                 "freshness": freshness, "consistency": consistency}
    quality_score = round(sum(breakdown.values()) / 4) if checked else None
    if not checked:
        status = "not_checked"
    elif any(item["severity"] in {"critical", "error"} for item in issues):
        status = "error"
    elif any(item["rule_code"] in {"TENDER_STALE", "PLAN_STALE", "DOCUMENT_STALE"} for item in issues):
        status = "stale"
    elif issues or completeness < 80:
        status = "partial"
    else:
        status = "good"
    return {"entity_type": entity_type, "entity_id": entity_id,
            "status": status, "completeness": completeness,
            "quality_score": quality_score, "score_breakdown": breakdown if checked else None,
            "issue_count": len(issues), "issues": [dict(item) for item in issues]}


def list_issues(*, status: str = "open", severity: str = "", entity_type: str = "",
                rule: str = "", page: int = 1, page_size: int = 50) -> dict:
    if status not in {"open", "reviewing", "ignored", "resolved", "auto_resolved", "all"}:
        raise ValueError("Trạng thái không hợp lệ.")
    if severity and severity not in {"info", "warning", "error", "critical"}:
        raise ValueError("Mức độ không hợp lệ.")
    if entity_type and entity_type not in {"tender", "plan", "document", "source", "contractor", "investor", "procuring_entity"}:
        raise ValueError("Loại dữ liệu không hợp lệ.")
    if rule and rule not in RULES:
        raise ValueError("Mã quy tắc không hợp lệ.")
    if not 1 <= page <= 100000 or not 1 <= page_size <= 100:
        raise ValueError("Trang không hợp lệ.")
    where = []
    if status != "all": where.append(data_quality_issues.c.status == status)
    if severity: where.append(data_quality_issues.c.severity == severity)
    if entity_type: where.append(data_quality_issues.c.entity_type == entity_type)
    if rule: where.append(data_quality_issues.c.rule_code == rule)
    with get_db().engine.connect() as conn:
        total = conn.scalar(select(func.count()).select_from(data_quality_issues).where(*where)) or 0
        rows = conn.execute(select(data_quality_issues).where(*where)
            .order_by(data_quality_issues.c.detected_at.desc(), data_quality_issues.c.id)
            .offset((page-1)*page_size).limit(page_size)).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total,
            "page": page, "has_more": page*page_size < total}


def issue_detail(issue_id: str) -> dict:
    if len(issue_id) != 32:
        raise ValueError("Mã vấn đề không hợp lệ.")
    with get_db().engine.connect() as conn:
        issue = conn.execute(select(data_quality_issues).where(
            data_quality_issues.c.id == issue_id)).mappings().first()
        if not issue:
            raise LookupError("Không tìm thấy vấn đề dữ liệu.")
        table, key = {"tender": (tenders, "tender_code"), "plan": (plans, "plan_code"),
                      "document": (tender_source_documents, "id")}.get(issue["entity_type"], (None, None))
        row = conn.execute(select(table).where(table.c[key] == issue["entity_id"])).mappings().first() if table is not None else None
        field = issue["field_name"]
        current = str(row[field]) if row and field and field in row and row[field] is not None else None
        source_url = row["source_url"] if row and "source_url" in row else None
        snapshots = conn.execute(select(tender_snapshots.c.version,
            tender_snapshots.c.created_at).where(
            tender_snapshots.c.tender_code == issue["entity_id"])
            .order_by(tender_snapshots.c.version.desc()).limit(3)).mappings().all() if issue["entity_type"] == "tender" else []
    return {"issue": dict(issue), "current_value": current,
            "source_url": source_url, "snapshots": [dict(item) for item in snapshots],
            "rule_description": RULES[issue["rule_code"]].description}


def review_issue(issue_id: str, action: str, actor_id: str) -> dict:
    target = {"review": "reviewing", "resolve": "resolved", "ignore": "ignored"}.get(action)
    if not target or len(issue_id) != 32:
        raise ValueError("Thao tác không hợp lệ.")
    with get_db().engine.begin() as conn:
        old = conn.execute(select(data_quality_issues).where(
            data_quality_issues.c.id == issue_id)).mappings().first()
        if not old:
            raise LookupError("Không tìm thấy vấn đề dữ liệu.")
        conn.execute(update(data_quality_issues).where(data_quality_issues.c.id == issue_id)
            .values(status=target, resolution_type=action if action != "review" else None,
                resolved_at=now() if action == "resolve" else None, updated_at=now()))
        conn.execute(insert(audit_logs).values(id=uuid.uuid4().hex, user_id=actor_id,
            action=f"quality_{action}", entity_type=old["entity_type"],
            entity_id=old["entity_id"], created_at=now()))
        return {"id": issue_id, "status": target}


def fix_safe_whitespace(issue_id: str, actor_id: str) -> dict:
    """Admin-approved trim/collapse only; record old value for exact reversal."""
    if len(issue_id) != 32:
        raise ValueError("Mã vấn đề không hợp lệ.")
    from server.search_engine import normalize_search
    with get_db().engine.begin() as conn:
        issue = conn.execute(select(data_quality_issues).where(
            data_quality_issues.c.id == issue_id,
            data_quality_issues.c.rule_code == "TENDER_EXTRA_WHITESPACE",
            data_quality_issues.c.status.in_(ACTIVE))).mappings().first()
        if not issue:
            raise LookupError("Không tìm thấy vấn đề có thể chuẩn hóa.")
        row = conn.execute(select(tenders).where(tenders.c.tender_code == issue["entity_id"])).mappings().first()
        if not row:
            raise LookupError("Không tìm thấy gói thầu.")
        old = row["title"]
        clean = safe_display_text(old)
        if old == clean:
            raise ValueError("Tên gói đã được chuẩn hóa; hãy quét lại.")
        search_text = normalize_search(" ".join(str(clean if field == "title" else row[field] or "")
            for field in ("title", "investor_name", "procuring_entity_name", "winning_contractor", "location")))
        conn.execute(update(tenders).where(tenders.c.tender_code == issue["entity_id"],
            tenders.c.title == old).values(title=clean, search_text=search_text))
        log_id = uuid.uuid4().hex
        conn.execute(insert(data_fix_log).values(id=log_id, entity_type="tender",
            entity_id=issue["entity_id"], field_name="title", old_value=old,
            new_value=clean, rule_code=issue["rule_code"], auto=False,
            actor_id=actor_id, created_at=now()))
        conn.execute(update(data_quality_issues).where(data_quality_issues.c.id == issue_id)
            .values(status="resolved", resolved_at=now(),
                resolution_type="safe_whitespace_fix", updated_at=now()))
        conn.execute(insert(audit_logs).values(id=uuid.uuid4().hex, user_id=actor_id,
            action="quality_safe_fix", entity_type="tender",
            entity_id=issue["entity_id"], created_at=now()))
        return {"issue_id": issue_id, "fix_id": log_id, "old_value": old,
                "new_value": clean}


def revert_safe_fix(fix_id: str, actor_id: str) -> dict:
    if len(fix_id) != 32:
        raise ValueError("Mã thay đổi không hợp lệ.")
    from server.search_engine import normalize_search
    with get_db().engine.begin() as conn:
        fix = conn.execute(select(data_fix_log).where(data_fix_log.c.id == fix_id,
            data_fix_log.c.rule_code == "TENDER_EXTRA_WHITESPACE")).mappings().first()
        if not fix:
            raise LookupError("Không tìm thấy thay đổi có thể hoàn tác.")
        row = conn.execute(select(tenders).where(
            tenders.c.tender_code == fix["entity_id"])).mappings().first()
        if not row or row["title"] != fix["new_value"]:
            raise ValueError("Tên gói đã thay đổi; không thể hoàn tác an toàn.")
        restored = fix["old_value"]
        search_text = normalize_search(" ".join(str(restored if field == "title" else row[field] or "")
            for field in ("title", "investor_name", "procuring_entity_name", "winning_contractor", "location")))
        conn.execute(update(tenders).where(tenders.c.tender_code == fix["entity_id"],
            tenders.c.title == fix["new_value"]).values(title=restored, search_text=search_text))
        conn.execute(insert(data_fix_log).values(id=uuid.uuid4().hex, entity_type="tender",
            entity_id=fix["entity_id"], field_name="title",
            old_value=fix["new_value"], new_value=restored,
            rule_code="TENDER_EXTRA_WHITESPACE_REVERT", auto=False,
            actor_id=actor_id, created_at=now()))
        conn.execute(insert(audit_logs).values(id=uuid.uuid4().hex, user_id=actor_id,
            action="quality_fix_reverted", entity_type="tender",
            entity_id=fix["entity_id"], created_at=now()))
        return {"fix_id": fix_id, "restored": True}


def list_duplicates(page: int = 1) -> dict:
    if not 1 <= page <= 100000:
        raise ValueError("Trang không hợp lệ.")
    with get_db().engine.connect() as conn:
        total = conn.scalar(select(func.count()).select_from(duplicate_candidates)
            .where(duplicate_candidates.c.status == "pending")) or 0
        rows = conn.execute(select(duplicate_candidates).where(
            duplicate_candidates.c.status == "pending")
            .order_by(duplicate_candidates.c.confidence.desc())
            .offset((page-1)*50).limit(50)).mappings().all()
        items = []
        tables = {"contractor": contractors, "investor": investors,
                  "procuring_entity": procuring_entities}
        for raw in rows:
            item = dict(raw)
            table = tables.get(item["entity_type"])
            if table is not None:
                for side in ("a", "b"):
                    entity = conn.execute(select(table.c.id, table.c.name, table.c.address,
                        table.c.tax_code if item["entity_type"] == "contractor"
                        else table.c.identifier).where(
                        table.c.id == item[f"entity_id_{side}"])).mappings().first()
                    item[f"entity_{side}"] = dict(entity) if entity else None
            items.append(item)
    return {"items": items, "total": total}


def review_duplicate(candidate_id: str, action: str, actor_id: str) -> dict:
    if action not in {"not_duplicate", "ignored"} or len(candidate_id) != 32:
        raise ValueError("Thao tác không hợp lệ.")
    with get_db().engine.begin() as conn:
        candidate = conn.execute(select(duplicate_candidates).where(
            duplicate_candidates.c.id == candidate_id)).mappings().first()
        if not candidate:
            raise LookupError("Không tìm thấy cặp nghi trùng.")
        conn.execute(update(duplicate_candidates).where(duplicate_candidates.c.id == candidate_id)
            .values(status=action, reviewed_at=now()))
        conn.execute(insert(audit_logs).values(id=uuid.uuid4().hex, user_id=actor_id,
            action=f"duplicate_{action}", entity_type=candidate["entity_type"],
            entity_id=candidate_id, created_at=now()))
    return {"id": candidate_id, "status": action}


def merge_duplicate(candidate_id: str, target_id: str, actor_id: str) -> dict:
    """Admin-confirmed merge of an exact identifier match; retain source and audit trail."""
    if len(candidate_id) != 32 or len(target_id) != 32:
        raise ValueError("Mã cặp hoặc đích không hợp lệ.")
    tables = {"contractor": (contractors, "tax_code", [(tenders, "contractor_id")]),
              "investor": (investors, "identifier", [(tenders, "investor_id"), (plans, "investor_id")]),
              "procuring_entity": (procuring_entities, "identifier", [(tenders, "procuring_entity_id")])}
    with get_db().engine.begin() as conn:
        candidate = conn.execute(select(duplicate_candidates).where(
            duplicate_candidates.c.id == candidate_id).with_for_update()).mappings().first()
        if not candidate or candidate["status"] != "pending":
            raise LookupError("Cặp nghi trùng không còn chờ xử lý.")
        if target_id not in {candidate["entity_id_a"], candidate["entity_id_b"]}:
            raise ValueError("Đích phải thuộc cặp nghi trùng.")
        table, identifier, relations = tables[candidate["entity_type"]]
        source_id = candidate["entity_id_b"] if target_id == candidate["entity_id_a"] else candidate["entity_id_a"]
        source = conn.execute(select(table).where(table.c.id == source_id).with_for_update()).mappings().first()
        target = conn.execute(select(table).where(table.c.id == target_id).with_for_update()).mappings().first()
        if not source or not target:
            raise LookupError("Không còn đủ dữ liệu để gộp.")
        strong_a = str(source[identifier] or "").strip().casefold()
        strong_b = str(target[identifier] or "").strip().casefold()
        if not strong_a or strong_a != strong_b:
            raise ValueError("Chỉ gộp khi định danh mạnh trùng khớp chính xác.")
        if conn.scalar(select(entity_merges.c.id).where(entity_merges.c.entity_type == candidate["entity_type"],
                entity_merges.c.source_id.in_((source_id, target_id)))):
            raise ValueError("Một pháp nhân trong cặp đã được gộp; hãy quét lại.")
        for relation, field in relations:
            conn.execute(update(relation).where(relation.c[field] == source_id).values({field: target_id}))
        alias = str(source["name"] or "").strip()
        if alias:
            exists = conn.scalar(select(entity_aliases.c.id).where(
                entity_aliases.c.entity_type == candidate["entity_type"],
                entity_aliases.c.entity_id == target_id,
                entity_aliases.c.normalized_alias == normalized_text(alias)))
            if not exists:
                conn.execute(insert(entity_aliases).values(id=uuid.uuid4().hex,
                    entity_type=candidate["entity_type"], entity_id=target_id,
                    alias=alias, normalized_alias=normalized_text(alias),
                    source="manual_merge", created_at=now()))
            from server.search_engine import normalize_search
            alias_search = normalize_search(alias)
            current_search = str(target["search_text"] or "")
            if alias_search and alias_search not in current_search:
                conn.execute(update(table).where(table.c.id == target_id).values(
                    search_text=(current_search + " " + alias_search).strip()))
        merge_id = uuid.uuid4().hex
        conn.execute(insert(entity_merges).values(id=merge_id, entity_type=candidate["entity_type"],
            source_id=source_id, target_id=target_id, candidate_id=candidate_id,
            actor_id=actor_id, source_snapshot_json=dict(source), created_at=now()))
        conn.execute(update(duplicate_candidates).where(duplicate_candidates.c.id == candidate_id)
            .values(status="merged", reviewed_at=now()))
        conn.execute(update(duplicate_candidates).where(
            duplicate_candidates.c.entity_type == candidate["entity_type"],
            duplicate_candidates.c.status == "pending",
            or_(duplicate_candidates.c.entity_id_a == source_id,
                duplicate_candidates.c.entity_id_b == source_id))
            .values(status="ignored", reviewed_at=now()))
        conn.execute(insert(audit_logs).values(id=uuid.uuid4().hex, user_id=actor_id,
            action="duplicate_merged", entity_type=candidate["entity_type"],
            entity_id=source_id, created_at=now()))
    from server.search_engine import invalidate_search_cache
    invalidate_search_cache()
    return {"id": candidate_id, "status": "merged", "source_id": source_id,
            "target_id": target_id, "merge_id": merge_id}
