"""User-scoped adapters preserving the existing web API response shapes."""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, insert, select, update

from server.database import (download_files, download_history, followed_tenders, get_db, now,
                      saved_searches, search_history, tags, tender_change_history,
                      tender_tags, user_notes, user_notifications)
from web_app import QueryHistoryStore, WatchlistStore


def _id() -> str:
    return uuid.uuid4().hex


class UserWatchlistStore(WatchlistStore):
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.lock = threading.RLock()

    def read(self) -> list[dict]:
        with get_db().engine.connect() as conn:
            rows = conn.execute(select(followed_tenders.c.payload)
                                .where(followed_tenders.c.user_id == self.user_id)
                                .order_by(followed_tenders.c.updated_at.desc())).all()
        return [self._normalize(dict(row.payload)) for row in rows]

    def _write(self, items: list[dict]) -> list[dict]:
        items = items[:500]
        stamp = now()
        with get_db().engine.begin() as conn:
            old_changes = {(row.tender_code, row.field_name, row.old_value,
                            row.new_value, row.detected_at) for row in conn.execute(
                select(tender_change_history.c.tender_code, tender_change_history.c.field_name,
                       tender_change_history.c.old_value, tender_change_history.c.new_value,
                       tender_change_history.c.detected_at)
                .where(tender_change_history.c.user_id == self.user_id))}
            followed_ids = select(followed_tenders.c.id).where(followed_tenders.c.user_id == self.user_id)
            conn.execute(delete(tender_tags).where(tender_tags.c.tender_id.in_(followed_ids)))
            conn.execute(delete(tags).where(tags.c.user_id == self.user_id))
            conn.execute(delete(followed_tenders).where(followed_tenders.c.user_id == self.user_id))
            conn.execute(delete(user_notes).where(user_notes.c.user_id == self.user_id))
            for item in items:
                code = str(item.get("code") or "")[:50]
                tender_id = _id()
                snapshot = item.get("snapshot") or {}
                conn.execute(insert(followed_tenders).values(
                    id=tender_id, user_id=self.user_id, tender_code=code,
                    tender_type="TBMT" if code.startswith("IB") else "KHLCNT",
                    title=str(item.get("name") or "")[:1000],
                    investor=str(item.get("investor") or "")[:500],
                    status=str(snapshot.get("tender_status") or "")[:160],
                    deadline=str(item.get("deadline") or "")[:60],
                    priority=str(item.get("priority") or "Trung bình")[:20],
                    internal_status=str(item.get("workflow_status") or "Mới")[:40],
                    payload=item, created_at=item.get("created_at") or stamp,
                    updated_at=stamp, last_checked_at=item.get("last_checked") or None))
                note = str(item.get("note") or "")[:5000]
                if note:
                    conn.execute(insert(user_notes).values(id=_id(), user_id=self.user_id,
                        tender_code=code, note=note, created_at=stamp, updated_at=stamp))
                for name in dict.fromkeys(str(tag).strip()[:30] for tag in item.get("tags", []) if str(tag).strip()):
                    existing = conn.execute(select(tags.c.id).where(tags.c.user_id == self.user_id,
                                                                    tags.c.name == name)).scalar()
                    tag_id = existing or _id()
                    if not existing:
                        conn.execute(insert(tags).values(id=tag_id, user_id=self.user_id, name=name))
                    conn.execute(insert(tender_tags).values(tender_id=tender_id, tag_id=tag_id))
                for change in item.get("changes", [])[:100]:
                    key = (code, str(change.get("field") or ""), str(change.get("from") or ""),
                           str(change.get("to") or ""), str(change.get("time") or ""))
                    if key in old_changes:
                        continue
                    old_changes.add(key)
                    conn.execute(insert(tender_change_history).values(
                        id=_id(), user_id=self.user_id, tender_code=code, field_name=key[1],
                        old_value=key[2], new_value=key[3], detected_at=key[4] or stamp))
                    category = ("deadline_changed" if key[1] == "bid_close_date" else
                                "result_available" if key[1] == "winner" else "tender_changed")
                    conn.execute(insert(user_notifications).values(
                        id=_id(), user_id=self.user_id, type=category,
                        title=f"{code} có cập nhật", message=f"{change.get('label') or key[1]}: {key[2]} → {key[3]}",
                        tender_code=code, is_read=False, created_at=stamp))
        return items


class UserHistoryStore(QueryHistoryStore):
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.lock = threading.RLock()

    def read(self) -> list[dict]:
        with get_db().engine.connect() as conn:
            rows = conn.execute(select(search_history)
                .where(search_history.c.user_id == self.user_id)
                .order_by(search_history.c.created_at.desc()).limit(100)).mappings().all()
        return [{**dict(row["filters"] or {}), "id": row["id"], "name": row["name"],
                 "time": row["created_at"], "result_count": row["result_count"],
                 "pinned": row["pinned"]} for row in rows]

    def _write(self, items: list[dict]) -> list[dict]:
        with get_db().engine.begin() as conn:
            conn.execute(delete(search_history).where(search_history.c.user_id == self.user_id))
            for item in items[:100]:
                params = {key: value for key, value in item.items() if key in {
                    "mode", "keyword", "use_dates", "date_from", "date_to", "status", "pages",
                    "detail", "fast_mode", "remove_duplicates", "bid_form", "location",
                    "kind", "sort", "page_size", "from", "to", "deadline_from", "deadline_to",
                    "investor", "procurer", "contractor", "selection_method", "contract_type",
                    "price_min", "price_max", "results"}}
                conn.execute(insert(search_history).values(
                    id=item.get("id") or _id(), user_id=self.user_id,
                    name=str(item.get("name") or "Tất cả TBMT")[:80],
                    query=str(item.get("keyword") or "")[:1000], filters=params,
                    result_count=item.get("result_count"), pinned=bool(item.get("pinned")),
                    created_at=item.get("time") or now()))
        return items[:100]

    def update(self, body: dict) -> list[dict]:
        if body.get("action") == "clear":
            with get_db().engine.begin() as conn:
                conn.execute(delete(search_history).where(search_history.c.user_id == self.user_id))
            return []
        return super().update(body)


class UserPresetStore:
    FIELDS = {"mode", "keyword", "use_dates", "date_from", "date_to", "status", "pages",
              "detail", "fast_mode", "remove_duplicates", "bid_form", "location",
              "kind", "sort", "page_size", "from", "to", "deadline_from", "deadline_to",
              "investor", "procurer", "contractor", "selection_method", "contract_type",
              "price_min", "price_max", "results"}

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.lock = threading.RLock()

    def read(self) -> list[dict]:
        with get_db().engine.connect() as conn:
            rows = conn.execute(select(saved_searches)
                .where(saved_searches.c.user_id == self.user_id)
                .order_by(saved_searches.c.updated_at.desc()).limit(100)).mappings().all()
        return [{"id": row["id"], "name": row["name"], "params": row["filters"],
                 "pinned": row["pinned"], "is_watch_enabled": row["is_watch_enabled"],
                 "last_run_at": row["last_run_at"]} for row in rows]

    def update(self, body: dict) -> list[dict]:
        action = body.get("action")
        with self.lock, get_db().engine.begin() as conn:
            item = conn.execute(select(saved_searches).where(
                saved_searches.c.user_id == self.user_id,
                saved_searches.c.id == str(body.get("id") or ""))).mappings().first()
            if action == "save":
                name = str(body.get("name") or "").strip()
                params = body.get("params")
                if not 1 <= len(name) <= 80 or not isinstance(params, dict) or params.get("mode") not in {
                    "Thông báo mời thầu", "Kế hoạch lựa chọn nhà thầu", "Kho dữ liệu"}:
                    raise ValueError("Bộ tìm kiếm không hợp lệ.")
                params = {key: value for key, value in params.items() if key in self.FIELDS}
                existing = conn.execute(select(saved_searches).where(
                    saved_searches.c.user_id == self.user_id,
                    saved_searches.c.name == name)).mappings().first()
                if existing:
                    conn.execute(update(saved_searches).where(saved_searches.c.id == existing["id"]).values(
                        query=str(params.get("keyword") or "")[:1000], filters=params, updated_at=now()))
                else:
                    conn.execute(insert(saved_searches).values(
                        id=_id(), user_id=self.user_id, name=name,
                        query=str(params.get("keyword") or "")[:1000], filters=params,
                        is_watch_enabled=False, pinned=False, created_at=now(), updated_at=now()))
            elif action in {"delete", "rename", "pin", "watch"} and item:
                where = saved_searches.c.id == item["id"]
                if action == "delete":
                    conn.execute(delete(saved_searches).where(where))
                elif action == "rename":
                    name = str(body.get("name") or "").strip()
                    if not 1 <= len(name) <= 80:
                        raise ValueError("Tên bộ tìm kiếm không hợp lệ.")
                    conn.execute(update(saved_searches).where(where).values(name=name, updated_at=now()))
                elif action == "pin":
                    conn.execute(update(saved_searches).where(where).values(pinned=bool(body.get("pinned"))))
                else:
                    conn.execute(update(saved_searches).where(where).values(
                        is_watch_enabled=bool(body.get("enabled")), updated_at=now()))
            else:
                raise ValueError("Không tìm thấy bộ tìm kiếm hoặc thao tác không hợp lệ.")
        return self.read()


class UserDownloadArchive:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def read(self) -> list[dict]:
        with get_db().engine.connect() as conn:
            rows = conn.execute(select(download_history)
                .where(download_history.c.user_id == self.user_id)
                .order_by(download_history.c.created_at.desc()).limit(200)).mappings().all()
        return [{"id": row["id"], "name": row["filename"], "kind": row["type"],
                 "status": row["status"], "size": row["size"], "error": row["error"],
                 "time": row["created_at"],
                 "url": f'/api/download-file?id={row["id"]}' if row["status"] == "Hoàn thành" else ""}
                for row in rows]

    def add(self, data: bytes, name: str, kind: str) -> dict:
        if len(data) > 25_000_000:
            raise ValueError("File vượt giới hạn lưu lại 25 MB; vẫn có thể tải trực tiếp.")
        token = _id()
        expiry = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec="seconds")
        with get_db().engine.begin() as conn:
            conn.execute(insert(download_history).values(
                id=token, user_id=self.user_id, filename=Path(name).name[:200],
                type=kind[:50], status="Hoàn thành", size=len(data), error="", created_at=now()))
            conn.execute(insert(download_files).values(download_id=token, data=data, expires_at=expiry))
        return {"id": token, "name": name, "kind": kind, "status": "Hoàn thành",
                "size": len(data), "time": now(), "url": f"/api/download-file?id={token}"}

    def record_error(self, name: str, kind: str, message: str) -> dict:
        token = _id()
        with get_db().engine.begin() as conn:
            conn.execute(insert(download_history).values(
                id=token, user_id=self.user_id, filename=Path(name).name[:200],
                type=kind[:50], status="Lỗi", size=0, error=message[:300], created_at=now()))
        return {"id": token, "name": name, "kind": kind, "status": "Lỗi",
                "size": 0, "error": message[:300], "time": now(), "url": ""}

    def file(self, token: str) -> tuple[bytes, str] | None:
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            return None
        with get_db().engine.connect() as conn:
            row = conn.execute(select(download_history.c.filename, download_files.c.data)
                .join(download_files, download_files.c.download_id == download_history.c.id)
                .where(download_history.c.id == token,
                       download_history.c.user_id == self.user_id,
                       download_files.c.expires_at > now())).first()
        return (row.data, row.filename) if row else None


_STORES: dict[str, object] = {}
_STORES_LOCK = threading.Lock()


def user_stores(user_id: str):
    from types import SimpleNamespace
    from web_app import LotFileStore
    with _STORES_LOCK:
        if user_id not in _STORES:
            _STORES[user_id] = SimpleNamespace(presets=UserPresetStore(user_id),
                watchlist=UserWatchlistStore(user_id), history=UserHistoryStore(user_id),
                downloads=UserDownloadArchive(user_id), lot_files=LotFileStore())
        return _STORES[user_id]
