"""Whitelisted, user-scoped automation actions. No network or AI side effects."""
from __future__ import annotations

import uuid

from sqlalchemy import delete, insert, select, update

from server.database import (background_jobs, followed_tenders, now, tags,
                             tender_tags, user_notes, user_notifications)

ACTION_TYPES = {"FOLLOW_TENDER", "UNFOLLOW_TENDER", "ADD_TAG", "REMOVE_TAG",
    "SET_PRIORITY", "SET_INTERNAL_STATUS", "CREATE_NOTIFICATION", "ADD_NOTE_TEMPLATE",
    "QUEUE_DOCUMENT_CHECK"}
PRIORITIES = {"Thấp", "Trung bình", "Cao", "Khẩn cấp"}
WORKFLOW = {"Mới", "Đang xem", "Quan tâm", "Đang xử lý", "Hoàn tất", "Bỏ qua"}
PRIORITY_RANK = {name: index for index, name in
                 enumerate(("Thấp", "Trung bình", "Cao", "Khẩn cấp"))}


def validate_actions(raw) -> list[dict]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 8:
        raise ValueError("Chọn từ 1 đến 8 hành động.")
    result = []
    for item in raw:
        if not isinstance(item, dict) or item.get("type") not in ACTION_TYPES:
            raise ValueError("Hành động không được hỗ trợ.")
        kind = item["type"]
        value = str(item.get("value") or "").strip()
        if kind in {"ADD_TAG", "REMOVE_TAG"} and not 1 <= len(value) <= 30:
            raise ValueError("Tag phải có từ 1 đến 30 ký tự.")
        if kind == "SET_PRIORITY" and value not in PRIORITIES:
            raise ValueError("Mức ưu tiên không hợp lệ.")
        if kind == "SET_INTERNAL_STATUS" and value not in WORKFLOW:
            raise ValueError("Trạng thái nội bộ không hợp lệ.")
        if kind == "ADD_NOTE_TEMPLATE" and not 1 <= len(value) <= 500:
            raise ValueError("Mẫu ghi chú phải có từ 1 đến 500 ký tự.")
        if kind not in {"ADD_TAG", "REMOVE_TAG", "SET_PRIORITY", "SET_INTERNAL_STATUS",
                        "ADD_NOTE_TEMPLATE"}:
            value = ""
        result.append({"type": kind, "value": value})
    return result


def _follow(conn, user_id: str, entity: dict) -> tuple[dict, bool]:
    code = entity["tender_code"]
    existing = conn.execute(select(followed_tenders).where(
        followed_tenders.c.user_id == user_id,
        followed_tenders.c.tender_code == code)).mappings().first()
    if existing:
        return dict(existing), False
    stamp = now()
    payload = {"code": code, "name": entity.get("title") or code,
        "investor": entity.get("investor_name") or "",
        "deadline": entity.get("bid_closing_date") or "",
        "url": entity.get("source_url") or "", "priority": "Trung bình",
        "workflow_status": "Mới", "tags": [], "note": "", "pinned": False,
        "changes": [], "has_update": False, "created_at": stamp,
        "snapshot": {"package_name": entity.get("title") or "",
                     "investor_name": entity.get("investor_name") or "",
                     "bid_close_date": entity.get("bid_closing_date") or "",
                     "tender_status": entity.get("status") or "",
                     "source_url": entity.get("source_url") or ""}}
    follow_id = uuid.uuid4().hex
    conn.execute(insert(followed_tenders).values(id=follow_id, user_id=user_id,
        tender_code=code, tender_type="TBMT", title=payload["name"],
        investor=payload["investor"], status=entity.get("status") or "",
        deadline=payload["deadline"], priority="Trung bình",
        internal_status="Mới", payload=payload, created_at=stamp, updated_at=stamp))
    return {"id": follow_id, "payload": payload, "priority": "Trung bình"}, True


def execute_action(conn, user_id: str, entity: dict, action: dict, rule_name: str) -> dict:
    """Execute one validated action inside the caller's transaction."""
    kind, value, code = action["type"], action["value"], entity["tender_code"]
    if kind == "CREATE_NOTIFICATION":
        conn.execute(insert(user_notifications).values(id=uuid.uuid4().hex,
            user_id=user_id, type="automation", title=f"Automation: {rule_name}"[:200],
            message=f"Rule '{rule_name}' khớp gói {code}: {entity.get('title') or code}"[:1000],
            tender_code=code, is_read=False, created_at=now()))
        return {"changed": True, "message": "Đã tạo thông báo"}
    if kind == "QUEUE_DOCUMENT_CHECK":
        queued = conn.scalar(select(background_jobs.c.id).where(
            background_jobs.c.job_type == "refresh-tender",
            background_jobs.c.entity_type == "tender",
            background_jobs.c.entity_id == code,
            background_jobs.c.status.in_(["pending", "retry", "running"])))
        if queued:
            return {"changed": False, "message": "Đã có trong hàng đợi kiểm tra"}
        conn.execute(insert(background_jobs).values(id=uuid.uuid4().hex,
            job_type="refresh-tender", entity_type="tender", entity_id=code,
            status="pending", attempts=0, last_error=None, next_retry_at=None,
            created_at=now(), started_at=None, finished_at=None))
        return {"changed": True, "message": "Đã đưa vào hàng đợi kiểm tra tài liệu"}
    if kind == "UNFOLLOW_TENDER":
        followed = conn.execute(select(followed_tenders.c.id).where(
            followed_tenders.c.user_id == user_id,
            followed_tenders.c.tender_code == code)).scalar()
        if not followed:
            return {"changed": False, "message": "Chưa theo dõi"}
        conn.execute(delete(tender_tags).where(tender_tags.c.tender_id == followed))
        conn.execute(delete(followed_tenders).where(followed_tenders.c.id == followed,
            followed_tenders.c.user_id == user_id))
        return {"changed": True, "message": "Đã bỏ theo dõi"}
    if kind == "REMOVE_TAG" and not conn.scalar(select(followed_tenders.c.id).where(
            followed_tenders.c.user_id == user_id,
            followed_tenders.c.tender_code == code)):
        return {"changed": False, "message": "Chưa theo dõi nên không có tag"}
    followed, created = _follow(conn, user_id, entity)
    if kind == "FOLLOW_TENDER":
        return {"changed": created, "message": "Đã theo dõi" if created else "Đã theo dõi trước đó"}
    payload = dict(followed["payload"] or {})
    changed = created
    if kind in {"ADD_TAG", "REMOVE_TAG"}:
        current = list(payload.get("tags") or [])
        if kind == "ADD_TAG" and value not in current:
            tag_id = conn.scalar(select(tags.c.id).where(tags.c.user_id == user_id,
                                                        tags.c.name == value))
            if not tag_id:
                tag_id = uuid.uuid4().hex
                conn.execute(insert(tags).values(id=tag_id, user_id=user_id, name=value))
            conn.execute(insert(tender_tags).values(tender_id=followed["id"], tag_id=tag_id))
            current.append(value)
            changed = True
        elif kind == "REMOVE_TAG" and value in current:
            tag_id = conn.scalar(select(tags.c.id).where(tags.c.user_id == user_id,
                                                        tags.c.name == value))
            if tag_id:
                conn.execute(delete(tender_tags).where(tender_tags.c.tender_id == followed["id"],
                                                      tender_tags.c.tag_id == tag_id))
            current.remove(value)
            changed = True
        payload["tags"] = current
    elif kind == "SET_PRIORITY":
        current = followed["priority"]
        if PRIORITY_RANK.get(value, 0) > PRIORITY_RANK.get(current, 0):
            payload["priority"] = value
            changed = True
    elif kind == "SET_INTERNAL_STATUS":
        if payload.get("workflow_status") != value:
            payload["workflow_status"] = value
            changed = True
    elif kind == "ADD_NOTE_TEMPLATE":
        note = value.replace("{rule_name}", rule_name).replace("{tender_code}", code)
        old = conn.scalar(select(user_notes.c.note).where(user_notes.c.user_id == user_id,
            user_notes.c.tender_code == code))
        if note not in (old or ""):
            combined = ((old + "\n\n") if old else "") + note
            if len(combined) > 5000:
                raise ValueError("Ghi chú đã đạt giới hạn 5.000 ký tự.")
            if old is None:
                conn.execute(insert(user_notes).values(id=uuid.uuid4().hex,
                    user_id=user_id, tender_code=code, note=combined,
                    created_at=now(), updated_at=now()))
            else:
                conn.execute(update(user_notes).where(user_notes.c.user_id == user_id,
                    user_notes.c.tender_code == code).values(note=combined, updated_at=now()))
            payload["note"] = combined
            changed = True
    if changed:
        values = {"payload": payload, "updated_at": now()}
        if kind == "SET_PRIORITY":
            values["priority"] = payload["priority"]
        if kind == "SET_INTERNAL_STATUS":
            values["internal_status"] = payload["workflow_status"]
        conn.execute(update(followed_tenders).where(followed_tenders.c.id == followed["id"],
            followed_tenders.c.user_id == user_id).values(**values))
    return {"changed": changed, "message": "Đã cập nhật" if changed else "Không thay đổi"}
