"""Private, scheduler-compatible tender automation; no in-process polling loop."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, insert, or_, select, update, delete
from sqlalchemy.exc import IntegrityError

from server.automation_actions import execute_action, validate_actions
from server.automation_conditions import evaluate_rule, validate_group
from server.database import (audit_logs, automation_events, automation_rules,
    automation_runs, followed_tenders, get_db, now, saved_search_seen,
    saved_searches, tags, tender_changes,
    tender_source_documents, tender_tags, tenders)

TRIGGERS = {
    "NEW_TENDER": "TBMT mới", "TENDER_CHANGED": "Thông tin thay đổi",
    "DEADLINE_APPROACHING": "Sắp đóng thầu", "KQLCNT_AVAILABLE": "Có KQLCNT",
    "STATUS_CHANGED": "Trạng thái thay đổi", "PRICE_CHANGED": "Giá thay đổi",
    "NEW_DOCUMENT": "Tài liệu mới",
    "SAVED_SEARCH_MATCH": "Khớp bộ lọc đã lưu",
    "MANUAL_RUN": "Chạy thủ công",
}
FREQUENCIES = {"manual": None, "hourly": 1, "3h": 3, "6h": 6, "daily": 24}
MAX_CANDIDATES = 1000


def _id() -> str:
    return uuid.uuid4().hex


def _next_run(frequency: str, when: datetime | None = None) -> str | None:
    hours = FREQUENCIES[frequency]
    if hours is None:
        return None
    return ((when or datetime.now(timezone.utc)) + timedelta(hours=hours)).isoformat(timespec="seconds")


def _audit(conn, user_id: str, action: str, rule_id: str) -> None:
    conn.execute(insert(audit_logs).values(id=_id(), user_id=user_id,
        action=action, entity_type="automation_rule", entity_id=rule_id,
        created_at=now()))


def validate_rule(body: dict) -> dict:
    if not isinstance(body, dict):
        raise ValueError("Rule không hợp lệ.")
    name = str(body.get("name") or "").strip()
    if not 1 <= len(name) <= 120:
        raise ValueError("Tên rule phải có từ 1 đến 120 ký tự.")
    trigger = body.get("trigger_type")
    if trigger not in TRIGGERS:
        raise ValueError("Trigger chưa được hỗ trợ.")
    frequency = body.get("run_frequency", "manual")
    if frequency not in FREQUENCIES:
        raise ValueError("Tần suất chạy không hợp lệ.")
    if trigger == "MANUAL_RUN" and frequency != "manual":
        raise ValueError("Rule chạy thủ công không thể đặt lịch tự động.")
    priority = body.get("priority", "normal")
    if priority not in {"low", "normal", "high"}:
        raise ValueError("Độ ưu tiên rule không hợp lệ.")
    conditions = validate_group(body.get("conditions", {"logic": "AND", "items": []}))
    actions = validate_actions(body.get("actions"))
    return {"name": name, "description": str(body.get("description") or "")[:1000],
        "trigger_type": trigger, "conditions_json": conditions,
        "actions_json": actions, "run_frequency": frequency, "priority": priority}


def list_rules(user_id: str, *, q: str = "", status: str = "", trigger: str = "",
               last_run: str = "") -> list[dict]:
    with get_db().engine.connect() as conn:
        latest_status = (select(automation_runs.c.status)
            .where(automation_runs.c.automation_id == automation_rules.c.id,
                   automation_runs.c.user_id == user_id)
            .order_by(automation_runs.c.started_at.desc()).limit(1)
            .correlate(automation_rules).scalar_subquery())
        latest_error = (select(automation_runs.c.error_message)
            .where(automation_runs.c.automation_id == automation_rules.c.id,
                   automation_runs.c.user_id == user_id)
            .order_by(automation_runs.c.started_at.desc()).limit(1)
            .correlate(automation_rules).scalar_subquery())
        conditions = [automation_rules.c.user_id == user_id,
                      automation_rules.c.deleted_at.is_(None)]
        if q:
            conditions.append(automation_rules.c.name.ilike("%" + q[:100].replace("%", "\\%")
                                                           .replace("_", "\\_") + "%", escape="\\"))
        if status in {"active", "paused"}:
            conditions.append(automation_rules.c.is_enabled.is_(status == "active"))
        elif status == "error":
            conditions.append(latest_error.is_not(None))
        elif status == "never":
            conditions.append(automation_rules.c.last_run_at.is_(None))
        if trigger in TRIGGERS:
            conditions.append(automation_rules.c.trigger_type == trigger)
        if last_run in {"today", "7d", "30d"}:
            days = {"today": 0, "7d": 6, "30d": 29}[last_run]
            since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
            conditions.append(automation_rules.c.last_run_at >= since)
        rows = conn.execute(select(automation_rules,
            latest_status.label("last_run_status"), latest_error.label("last_run_error"))
            .where(*conditions)
            .order_by(automation_rules.c.updated_at.desc()).limit(200)).mappings().all()
    return [dict(row) for row in rows]


def get_rule(user_id: str, rule_id: str) -> dict | None:
    with get_db().engine.connect() as conn:
        row = conn.execute(select(automation_rules).where(
            automation_rules.c.id == rule_id,
            automation_rules.c.user_id == user_id,
            automation_rules.c.deleted_at.is_(None))).mappings().first()
    return dict(row) if row else None


def save_rule(user_id: str, body: dict, rule_id: str = "") -> dict:
    values = validate_rule(body)
    current = get_rule(user_id, rule_id) if rule_id else None
    if rule_id and current is None:
        raise LookupError("Không tìm thấy rule của tài khoản này.")
    enabled = body.get("is_enabled", current["is_enabled"] if current else False)
    if not isinstance(enabled, bool):
        raise ValueError("Trạng thái bật/tạm dừng không hợp lệ.")
    stamp = now()
    with get_db().engine.begin() as conn:
        if current:
            reset_scan = any(values[key] != current[key] for key in
                             ("trigger_type", "conditions_json", "actions_json"))
            next_run = (_next_run(values["run_frequency"]) if enabled and
                        (not current["is_enabled"] or values["run_frequency"] != current["run_frequency"])
                        else current["next_run_at"] if enabled else None)
            conn.execute(update(automation_rules).where(
                automation_rules.c.id == rule_id,
                automation_rules.c.user_id == user_id).values(**values,
                    is_enabled=enabled, next_run_at=next_run,
                    cursor_json=None if reset_scan else current["cursor_json"],
                    last_run_at=None if reset_scan else current["last_run_at"],
                    updated_at=stamp))
            _audit(conn, user_id, "automation_updated", rule_id)
        else:
            rule_id = _id()
            conn.execute(insert(automation_rules).values(id=rule_id, user_id=user_id,
                **values, is_enabled=enabled,
                next_run_at=_next_run(values["run_frequency"]) if enabled else None,
                last_run_at=None, lock_until=None, cursor_json=None, deleted_at=None,
                created_at=stamp, updated_at=stamp))
            _audit(conn, user_id, "automation_created", rule_id)
    return get_rule(user_id, rule_id)


def set_enabled(user_id: str, rule_id: str, enabled: bool) -> dict:
    current = get_rule(user_id, rule_id)
    if current is None:
        raise LookupError("Không tìm thấy rule của tài khoản này.")
    with get_db().engine.begin() as conn:
        conn.execute(update(automation_rules).where(automation_rules.c.id == rule_id,
            automation_rules.c.user_id == user_id).values(is_enabled=enabled,
            next_run_at=_next_run(current["run_frequency"]) if enabled else None,
            updated_at=now()))
        _audit(conn, user_id, "automation_enabled" if enabled else "automation_paused", rule_id)
    return get_rule(user_id, rule_id)


def duplicate_rule(user_id: str, rule_id: str) -> dict:
    current = get_rule(user_id, rule_id)
    if current is None:
        raise LookupError("Không tìm thấy rule của tài khoản này.")
    return save_rule(user_id, {"name": current["name"][:108] + " (bản sao)",
        "description": current["description"], "trigger_type": current["trigger_type"],
        "conditions": current["conditions_json"], "actions": current["actions_json"],
        "run_frequency": current["run_frequency"], "priority": current["priority"],
        "is_enabled": False})


def delete_rule(user_id: str, rule_id: str) -> bool:
    with get_db().engine.begin() as conn:
        owned = conn.scalar(select(automation_rules.c.id).where(
            automation_rules.c.id == rule_id,
            automation_rules.c.user_id == user_id))
        if not owned:
            return False
        # Preserve run/event history and hide this definition from the UI.
        conn.execute(update(automation_rules).where(automation_rules.c.id == rule_id,
            automation_rules.c.user_id == user_id).values(is_enabled=False,
            next_run_at=None, deleted_at=now(), updated_at=now()))
        _audit(conn, user_id, "automation_deleted", rule_id)
    return True


def list_runs(user_id: str, rule_id: str = "") -> list[dict]:
    with get_db().engine.connect() as conn:
        conditions = [automation_runs.c.user_id == user_id]
        if rule_id:
            if get_rule(user_id, rule_id) is None:
                raise LookupError("Không tìm thấy rule của tài khoản này.")
            conditions.append(automation_runs.c.automation_id == rule_id)
        rows = conn.execute(select(automation_runs).where(*conditions)
            .order_by(automation_runs.c.started_at.desc()).limit(100)).mappings().all()
    return [dict(row) for row in rows]


def list_events(user_id: str, run_id: str) -> list[dict]:
    with get_db().engine.connect() as conn:
        owned = conn.scalar(select(automation_runs.c.id).where(
            automation_runs.c.id == run_id, automation_runs.c.user_id == user_id))
        if not owned:
            raise LookupError("Không tìm thấy lần chạy của tài khoản này.")
        rows = conn.execute(select(automation_events).where(
            automation_events.c.run_id == run_id,
            automation_events.c.user_id == user_id)
            .order_by(automation_events.c.created_at).limit(500)).mappings().all()
    return [dict(row) for row in rows]


def automation_analytics(user_id: str, days: int = 14) -> dict:
    """Return private aggregate usage metrics without exposing rule definitions."""
    days = max(1, min(int(days), 90))
    since = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
    day = func.substr(automation_runs.c.started_at, 1, 10)
    with get_db().engine.connect() as conn:
        trend = conn.execute(select(day.label("day"),
            func.count().label("runs"),
            func.coalesce(func.sum(automation_runs.c.matched_count), 0).label("matches"),
            func.sum(case((automation_runs.c.error_message.is_not(None), 1), else_=0))
                .label("failures"))
            .where(automation_runs.c.user_id == user_id,
                   automation_runs.c.started_at >= since)
            .group_by(day).order_by(day)).mappings().all()
        actions = conn.execute(select(automation_events.c.action,
            func.count().label("count"))
            .where(automation_events.c.user_id == user_id,
                   automation_events.c.created_at >= since,
                   automation_events.c.status == "completed")
            .group_by(automation_events.c.action)
            .order_by(func.count().desc()).limit(10)).mappings().all()
    return {"days": days, "trend": [dict(row) for row in trend],
            "actions": [dict(row) for row in actions]}


def _simple_sql(group: dict) -> list:
    """Push only safe conjunctions to SQL; complex OR stays in Python."""
    if group["logic"] != "AND":
        return []
    result = []
    for item in group["items"]:
        if "items" in item:
            result.extend(_simple_sql(item))
            continue
        field, op, value = item["field"], item["operator"], item["value"]
        if field not in tenders.c:
            continue
        column = tenders.c[field]
        if op == "equals":
            result.append(column == value)
        elif op == "contains" and field not in {"package_price", "winning_price"}:
            escaped = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            result.append(column.ilike("%" + escaped + "%", escape="\\"))
        elif op == "greater_or_equal" and field in {"package_price", "winning_price"}:
            result.append(column >= value)
        elif op == "less_or_equal" and field in {"package_price", "winning_price"}:
            result.append(column <= value)
    return result


def _candidates(rule: dict, *, dry_run: bool = False) -> tuple[list[tuple[dict, str]], bool]:
    trigger = rule["trigger_type"]
    cutoff = rule["last_run_at"] or rule["created_at"]
    cursor = {} if dry_run else (rule.get("cursor_json") or {})
    conditions = _simple_sql(rule["conditions_json"])
    query = select(tenders)
    if trigger == "NEW_TENDER" and not dry_run:
        # Source timestamps are stored to seconds; >= avoids missing a tender
        # observed in the same second as rule creation or the previous run.
        query = query.where(tenders.c.first_seen_at >= cutoff)
        cursor = rule.get("cursor_json") or {}
        if cursor.get("at") and cursor.get("code"):
            query = query.where(or_(tenders.c.first_seen_at > cursor["at"],
                and_(tenders.c.first_seen_at == cursor["at"],
                     tenders.c.tender_code > cursor["code"])))
    elif trigger == "NEW_DOCUMENT":
        query = query.join(tender_source_documents,
            tender_source_documents.c.tender_code == tenders.c.tender_code)
        if not dry_run:
            query = query.where(tender_source_documents.c.first_seen_at >= cutoff)
            cursor = rule.get("cursor_json") or {}
            if cursor.get("at") and cursor.get("code"):
                query = query.where(or_(
                    tender_source_documents.c.first_seen_at > cursor["at"],
                    and_(tender_source_documents.c.first_seen_at == cursor["at"],
                         tender_source_documents.c.id > cursor["code"])))
        query = query.add_columns(
            tender_source_documents.c.id.label("document_id"),
            tender_source_documents.c.first_seen_at.label("document_seen_at"),
            tender_source_documents.c.document_name.label("document_name"))
    elif trigger == "SAVED_SEARCH_MATCH":
        query = query.join(saved_search_seen,
            saved_search_seen.c.tender_code == tenders.c.tender_code)
        query = query.join(saved_searches,
            saved_searches.c.id == saved_search_seen.c.search_id)
        query = query.where(saved_searches.c.user_id == rule["user_id"])
        cursor = rule.get("cursor_json") or {}
        if not dry_run and cursor.get("at") and cursor.get("code"):
            query = query.where(or_(saved_search_seen.c.search_id > cursor["at"],
                and_(saved_search_seen.c.search_id == cursor["at"],
                     saved_search_seen.c.tender_code > cursor["code"])))
        query = query.add_columns(saved_searches.c.name.label("saved_search"),
            saved_search_seen.c.search_id.label("saved_search_id"))
    elif trigger == "DEADLINE_APPROACHING":
        local_today = datetime.now(timezone(timedelta(hours=7))).date()
        today = local_today.isoformat()
        horizon = (local_today + timedelta(days=30)).isoformat()
        query = query.where(tenders.c.bid_closing_date >= today,
                            tenders.c.bid_closing_date < horizon)
        if cursor.get("at") and cursor.get("code"):
            query = query.where(or_(tenders.c.bid_closing_date > cursor["at"],
                and_(tenders.c.bid_closing_date == cursor["at"],
                     tenders.c.tender_code > cursor["code"])))
    elif trigger == "KQLCNT_AVAILABLE":
        query = query.where(tenders.c.winning_contractor.is_not(None),
                            tenders.c.winning_contractor != "")
        if cursor.get("code"):
            query = query.where(tenders.c.tender_code > cursor["code"])
    elif trigger in {"TENDER_CHANGED", "STATUS_CHANGED", "PRICE_CHANGED"}:
        query = query.join(tender_changes, tender_changes.c.tender_code == tenders.c.tender_code)
        if trigger == "STATUS_CHANGED":
            query = query.where(tender_changes.c.field_name == "status")
        if trigger == "PRICE_CHANGED":
            query = query.where(tender_changes.c.field_name.in_(["package_price", "winning_price"]))
        if not dry_run:
            query = query.where(tender_changes.c.detected_at >= cutoff)
            if cursor.get("at") and cursor.get("code"):
                query = query.where(or_(tender_changes.c.detected_at > cursor["at"],
                    and_(tender_changes.c.detected_at == cursor["at"],
                         tender_changes.c.id > cursor["code"])))
        query = query.add_columns(tender_changes.c.id.label("change_id"),
            tender_changes.c.field_name.label("changed_field"),
            tender_changes.c.detected_at.label("change_seen_at"))
    elif trigger == "MANUAL_RUN" and cursor.get("at") and cursor.get("code"):
        query = query.where(or_(tenders.c.first_seen_at > cursor["at"],
            and_(tenders.c.first_seen_at == cursor["at"],
                 tenders.c.tender_code > cursor["code"])))
    query = query.where(*conditions)
    if trigger == "NEW_DOCUMENT":
        query = query.order_by(tender_source_documents.c.first_seen_at,
                               tender_source_documents.c.id)
    elif trigger == "SAVED_SEARCH_MATCH":
        query = query.order_by(saved_search_seen.c.search_id,
                               saved_search_seen.c.tender_code)
    elif trigger == "DEADLINE_APPROACHING":
        query = query.order_by(tenders.c.bid_closing_date, tenders.c.tender_code)
    elif trigger == "KQLCNT_AVAILABLE":
        query = query.order_by(tenders.c.tender_code)
    elif trigger in {"TENDER_CHANGED", "STATUS_CHANGED", "PRICE_CHANGED"}:
        query = query.order_by(tender_changes.c.detected_at, tender_changes.c.id)
    else:
        query = query.order_by(tenders.c.first_seen_at, tenders.c.tender_code)
    with get_db().engine.connect() as conn:
        rows = conn.execute(query.limit(MAX_CANDIDATES + 1)).mappings().all()
    truncated = len(rows) > MAX_CANDIDATES
    result = []
    for raw in rows[:MAX_CANDIDATES]:
        item = dict(raw)
        event_id = str(item.pop("change_id", "") or item.get("result_date") or
                       item.get("bid_closing_date") or item.get("first_seen_at") or item["tender_code"])
        if trigger == "NEW_TENDER":
            event_id = item.get("first_seen_at") or item["tender_code"]
        if trigger == "NEW_DOCUMENT":
            event_id = item.pop("document_id")
        if trigger == "SAVED_SEARCH_MATCH":
            event_id = item.pop("saved_search_id")
        if trigger == "MANUAL_RUN":
            event_id = "manual"
        if trigger == "KQLCNT_AVAILABLE":
            event_id = str(item.get("result_date") or "") + "|" + str(item.get("winning_contractor") or "")
        result.append((item, event_id))
    return result, truncated


def _cursor_after(trigger: str, rows: list[tuple[dict, str]]) -> dict | None:
    if not rows:
        return None
    entity, event_id = rows[-1]
    if trigger in {"NEW_TENDER", "MANUAL_RUN"}:
        return {"at": entity["first_seen_at"], "code": entity["tender_code"]}
    if trigger == "NEW_DOCUMENT":
        return {"at": entity["document_seen_at"], "code": event_id}
    if trigger == "SAVED_SEARCH_MATCH":
        return {"at": event_id, "code": entity["tender_code"]}
    if trigger == "DEADLINE_APPROACHING":
        return {"at": entity["bid_closing_date"], "code": entity["tender_code"]}
    if trigger == "KQLCNT_AVAILABLE":
        return {"code": entity["tender_code"]}
    if trigger in {"TENDER_CHANGED", "STATUS_CHANGED", "PRICE_CHANGED"}:
        return {"at": entity["change_seen_at"], "code": event_id}
    return None


def _enrich_user_context(user_id: str, rows: list[tuple[dict, str]]) -> None:
    codes = [entity["tender_code"] for entity, _ in rows]
    if not codes:
        return
    with get_db().engine.connect() as conn:
        followed = conn.execute(select(followed_tenders.c.tender_code,
            followed_tenders.c.id).where(followed_tenders.c.user_id == user_id,
            followed_tenders.c.tender_code.in_(codes))).all()
        ids = [row.id for row in followed]
        tag_rows = (conn.execute(select(tender_tags.c.tender_id, tags.c.name)
            .join(tags, tags.c.id == tender_tags.c.tag_id)
            .where(tender_tags.c.tender_id.in_(ids), tags.c.user_id == user_id)).all()
            if ids else [])
    by_id = {row.id: row.tender_code for row in followed}
    tag_map: dict[str, list[str]] = {}
    for row in tag_rows:
        tag_map.setdefault(by_id[row.tender_id], []).append(row.name)
    watched = {row.tender_code for row in followed}
    for entity, _ in rows:
        code = entity["tender_code"]
        entity["is_followed"] = code in watched
        entity["tags"] = tag_map.get(code, [])


def _dedup(rule: dict, entity: dict, event_id: str, position: int) -> str:
    raw = json.dumps([rule["id"], entity["tender_code"], rule["trigger_type"],
                      event_id, position, rule["actions_json"][position]],
                     ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _execute_one(rule: dict, run_id: str, entity: dict, event_id: str,
                 position: int) -> tuple[bool, str]:
    action = rule["actions_json"][position]
    key = _dedup(rule, entity, event_id, position)
    try:
        with get_db().engine.begin() as conn:
            if conn.scalar(select(automation_events.c.id).where(
                    automation_events.c.dedup_key == key)):
                return False, "Đã xử lý trước đó"
            outcome = execute_action(conn, rule["user_id"], entity, action, rule["name"])
            conn.execute(insert(automation_events).values(id=_id(), automation_id=rule["id"],
                run_id=run_id, user_id=rule["user_id"], entity_type="tender",
                entity_id=entity["tender_code"], trigger=rule["trigger_type"],
                action=action["type"], status="completed" if outcome["changed"] else "noop",
                dedup_key=key, details_json={"message": outcome["message"],
                    "event_id": event_id}, created_at=now()))
        return bool(outcome["changed"]), ""
    except IntegrityError:
        return False, "Đã xử lý trước đó"
    except Exception as exc:
        logging.exception("Automation action failed rule=%s tender=%s action=%s",
                          rule["id"], entity["tender_code"], action["type"])
        message = str(exc)[:200] if isinstance(exc, ValueError) else "Không thực hiện được hành động. Hãy thử lại."
        with get_db().engine.begin() as conn:
            conn.execute(insert(automation_events).values(id=_id(), automation_id=rule["id"],
                run_id=run_id, user_id=rule["user_id"], entity_type="tender",
                entity_id=entity["tender_code"], trigger=rule["trigger_type"],
                action=action["type"], status="failed",
                dedup_key=hashlib.sha256((key + run_id).encode()).hexdigest(),
                details_json={"message": message}, created_at=now()))
        return False, message


def preview_rule(user_id: str, body: dict) -> dict:
    """Evaluate an unsaved draft without creating a rule, run or action event."""
    values = validate_rule(body)
    rule = {"id": "preview", "user_id": user_id, "created_at": now(),
            "last_run_at": None, "cursor_json": None, **values}
    rows, truncated = _candidates(rule, dry_run=True)
    _enrich_user_context(user_id, rows)
    matched = [item for item, _ in rows if evaluate_rule(item, rule)]
    return {"dry_run": True, "matched_count": len(matched),
        "scanned_count": len(rows), "truncated": truncated,
        "items": [{"tender_code": item["tender_code"], "title": item["title"]}
                  for item in matched[:50]], "actions": values["actions_json"]}


def run_rule(user_id: str, rule_id: str, *, dry_run: bool = False) -> dict:
    rule = get_rule(user_id, rule_id)
    if rule is None:
        raise LookupError("Không tìm thấy rule của tài khoản này.")
    if dry_run:
        rows, truncated = _candidates(rule, dry_run=True)
        _enrich_user_context(user_id, rows)
        matched = [item for item, _ in rows if evaluate_rule(item, rule)]
        return {"dry_run": True, "matched_count": len(matched),
            "scanned_count": len(rows), "truncated": truncated,
            "items": [{"tender_code": item["tender_code"], "title": item["title"]}
                      for item in matched[:50]], "actions": rule["actions_json"]}
    stamp = now()
    lock_until = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec="seconds")
    with get_db().engine.begin() as conn:
        claimed = conn.execute(update(automation_rules).where(
            automation_rules.c.id == rule_id, automation_rules.c.user_id == user_id,
            or_(automation_rules.c.lock_until.is_(None),
                automation_rules.c.lock_until < stamp)).values(lock_until=lock_until)).rowcount
        if not claimed:
            raise ValueError("Rule đang chạy. Hãy thử lại sau.")
        run_id = _id()
        conn.execute(insert(automation_runs).values(id=run_id, automation_id=rule_id,
            user_id=user_id, started_at=stamp, status="running", matched_count=0,
            action_count=0))
        _audit(conn, user_id, "automation_manual_run", rule_id)
    started = datetime.now(timezone.utc)
    matched_count = action_count = 0
    errors = []
    truncated = False
    rows = []
    try:
        rows, truncated = _candidates(rule)
        _enrich_user_context(user_id, rows)
        for entity, event_id in rows:
            if not evaluate_rule(entity, rule):
                continue
            matched_count += 1
            for position in range(len(rule["actions_json"])):
                changed, error = _execute_one(rule, run_id, entity, event_id, position)
                action_count += int(changed)
                if error and error != "Đã xử lý trước đó":
                    errors.append(error)
    except Exception as exc:
        logging.exception("Automation run failed rule=%s", rule_id)
        errors.append(str(exc)[:200] if isinstance(exc, ValueError)
                      else "Không chạy được rule. Hãy thử lại.")
    finally:
        elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        status = ("failed" if errors and not action_count else
                  "partial" if errors or truncated else "completed")
        with get_db().engine.begin() as conn:
            conn.execute(update(automation_runs).where(automation_runs.c.id == run_id,
                automation_runs.c.user_id == user_id).values(finished_at=now(),
                status=status, matched_count=matched_count, action_count=action_count,
                error_message="; ".join(errors[:3])[:300] if errors else None,
                duration_ms=elapsed))
            # A truncated scan is scheduled soon and keeps its cursor so no
            # unexamined observation is silently marked processed.
            cursor_supported = _cursor_after(rule["trigger_type"], rows) is not None
            next_run = (((datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(timespec="seconds")
                         if truncated and cursor_supported else _next_run(rule["run_frequency"]))
                        if rule["run_frequency"] != "manual" else None)
            cursor = (rule.get("cursor_json") if errors else
                      _cursor_after(rule["trigger_type"], rows) if truncated else None)
            conn.execute(update(automation_rules).where(automation_rules.c.id == rule_id,
                automation_rules.c.user_id == user_id).values(lock_until=None,
                last_run_at=stamp if not truncated and not errors else rule["last_run_at"],
                next_run_at=next_run if rule["is_enabled"] else None,
                cursor_json=cursor))
    return {"id": run_id, "status": status, "matched_count": matched_count,
            "action_count": action_count, "errors": errors[:3], "truncated": truncated}


def run_due_automations(limit: int = 20) -> dict:
    stamp = now()
    priority_order = case((automation_rules.c.priority == "high", 0),
                          (automation_rules.c.priority == "normal", 1), else_=2)
    with get_db().engine.connect() as conn:
        rules = conn.execute(select(automation_rules.c.id, automation_rules.c.user_id)
            .where(automation_rules.c.is_enabled.is_(True),
                   automation_rules.c.next_run_at.is_not(None),
                   automation_rules.c.next_run_at <= stamp)
            .order_by(priority_order, automation_rules.c.next_run_at)
            .limit(max(1, min(limit, 50)))).all()
    done = failed = 0
    for rule_id, user_id in rules:
        try:
            result = run_rule(user_id, rule_id)
            done += 1
            failed += int(bool(result["errors"]))
        except Exception:
            logging.exception("Scheduled automation failed rule=%s", rule_id)
            failed += 1
    return {"status": "done", "rules": done, "failures": failed}
