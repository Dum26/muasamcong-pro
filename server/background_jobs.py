"""Bounded Scheduler-triggered jobs; no infinite in-process scheduling loop."""
from __future__ import annotations

import logging
import threading
import uuid

from sqlalchemy import delete, insert, select, update

from server.database import (download_files, download_history, followed_tenders, get_db,
                      job_runs, now, saved_search_seen, saved_searches, user_notifications)

_RUN_LOCK = threading.Lock()


def _record(kind: str, status: str, details: str = "") -> None:
    with get_db().engine.begin() as conn:
        conn.execute(insert(job_runs).values(id=uuid.uuid4().hex, kind=kind,
                                             status=status, details=details[:1000], created_at=now()))


def sync_followed_item(followed_id: str) -> dict:
    """Refresh one user's follow record; never mix another user's state."""
    from app import MuaSamCongClient, display_plan_no, extract_notify_no, plan_row_from_search
    from dataclasses import asdict
    from server.database_adapters import user_stores
    with get_db().engine.connect() as conn:
        followed = conn.execute(select(followed_tenders).where(
            followed_tenders.c.id == followed_id)).mappings().first()
    if not followed:
        return {"checked": 0, "errors": 0, "skipped": True}
    user_id, code = followed["user_id"], followed["tender_code"]
    client = MuaSamCongClient(force_refresh=True)
    try:
        if code.startswith("IB"):
            records = client.search_notices(code, max_pages=1, page_size=20)
            record = next((item for item in records if extract_notify_no(item).upper() == code), None)
        else:
            records = client.search_plans(code, max_pages=1, page_size=20)
            record = next((item for item in records if display_plan_no(item.get("planNo")) == code), None)
        if record:
            user_stores(user_id).watchlist.sync([{"code": code, **asdict(plan_row_from_search(record))}])
            return {"checked": 1, "errors": 0}
        user_stores(user_id).watchlist.mark_error(code, "Không tìm thấy mã trong lần kiểm tra này.")
        return {"checked": 0, "errors": 1}
    except Exception:
        user_stores(user_id).watchlist.mark_error(code, "Không lấy được dữ liệu.")
        raise
    finally:
        client.s.close()


def sync_saved_search_item(search_id: str) -> dict:
    """Run one watched search and issue notifications only to its owner."""
    from app import display_plan_no
    from web_app import SearchJob, _run_search
    with get_db().engine.connect() as conn:
        saved = conn.execute(select(saved_searches).where(
            saved_searches.c.id == search_id,
            saved_searches.c.is_watch_enabled.is_(True))).mappings().first()
    if not saved:
        return {"searches": 0, "new_results": 0, "skipped": True}
    filters = dict(saved["filters"] or {})
    if filters.get("mode") == "Kho dữ liệu":
        from server.search_engine import search
        query = dict(q=filters.get("keyword", ""), kind=filters.get("kind", ""),
                     sort=filters.get("sort", "relevance"), page_size=1000,
                     internal=True)
        for key in ("status", "location", "investor", "procurer", "contractor",
                    "deadline_from", "deadline_to", "price_min", "price_max",
                    "selection_method", "contract_type"):
            if filters.get(key):
                query[key] = filters[key]
        query["from_date"] = filters.get("from", "")
        query["to_date"] = filters.get("to", "")
        query["results_only"] = filters.get("results") == "1"
        first = search(**query)
        codes = {row["code"] for row in first["items"] if row["kind"] in {"tender", "plan"}}
        for page in range(2, first["total_pages"] + 1):
            codes.update(row["code"] for row in search(**query, page=page)["items"]
                         if row["kind"] in {"tender", "plan"})
    else:
        job = SearchJob(filters, owner=saved["user_id"])
        _run_search(job)
        if job.state != "done":
            raise RuntimeError(job.error or "Search did not finish")
        codes = {row.notify_no or display_plan_no(row.plan_no) for row in job.rows}
    codes.discard("")
    with get_db().engine.begin() as conn:
        seen = set(conn.execute(select(saved_search_seen.c.tender_code)
            .where(saved_search_seen.c.search_id == saved["id"])).scalars())
        fresh = sorted(codes - seen)
        for code in fresh:
            conn.execute(insert(saved_search_seen).values(search_id=saved["id"], tender_code=code))
        new_count = len(fresh) if saved["last_run_at"] else 0
        if new_count:
            conn.execute(insert(user_notifications).values(
                id=uuid.uuid4().hex, user_id=saved["user_id"], type="saved_search_match",
                title=f"Bộ lọc {saved['name']} có kết quả mới",
                message=f"Có {new_count} mã mới khớp bộ lọc đã lưu.",
                tender_code=fresh[0] if new_count == 1 else None,
                is_read=False, created_at=now()))
        conn.execute(update(saved_searches).where(saved_searches.c.id == saved["id"])
                     .values(last_run_at=now()))
    return {"searches": 1, "new_results": new_count}


def check_followed_tenders(limit: int = 30) -> dict:
    from server.intelligence_jobs import enqueue_followed, run_pending
    if not _RUN_LOCK.acquire(blocking=False):
        return {"status": "busy", "checked": 0, "errors": 0}
    try:
        with get_db().engine.connect() as conn:
            ids = conn.execute(select(followed_tenders.c.id)
                .order_by(followed_tenders.c.last_checked_at.asc()).limit(limit)).scalars().all()
        for followed_id in ids:
            enqueue_followed(followed_id)
        result = run_pending(limit, job_types={"sync-followed"}) if ids else {"outcomes": [], "failed": 0}
        checked = sum(item.get("checked", 0) for item in result["outcomes"])
        errors = result["failed"] + sum(item.get("errors", 0) for item in result["outcomes"])
        _record("check-followed-tenders", "done", f"checked={checked}; errors={errors}")
        return {"status": "done", "checked": checked, "errors": errors}
    finally:
        _RUN_LOCK.release()


def run_saved_searches(limit: int = 10) -> dict:
    from server.intelligence_jobs import enqueue_saved_search, run_pending
    if not _RUN_LOCK.acquire(blocking=False):
        return {"status": "busy", "searches": 0, "new_results": 0}
    try:
        with get_db().engine.connect() as conn:
            ids = conn.execute(select(saved_searches.c.id)
                .where(saved_searches.c.is_watch_enabled.is_(True))
                .order_by(saved_searches.c.last_run_at.asc()).limit(limit)).scalars().all()
        for search_id in ids:
            enqueue_saved_search(search_id)
        result = run_pending(limit, job_types={"sync-saved-search"}) if ids else {"outcomes": []}
        processed = sum(item.get("searches", 0) for item in result["outcomes"])
        new_total = sum(item.get("new_results", 0) for item in result["outcomes"])
        _record("run-saved-searches", "done", f"searches={processed}; new={new_total}")
        return {"status": "done", "searches": processed, "new_results": new_total}
    finally:
        _RUN_LOCK.release()


def cleanup_expired_downloads() -> int:
    with get_db().engine.begin() as conn:
        expired = list(conn.execute(select(download_files.c.download_id)
            .where(download_files.c.expires_at <= now())).scalars())
        if expired:
            conn.execute(update(download_history).where(download_history.c.id.in_(expired))
                         .values(status="Hết hạn"))
            conn.execute(delete(download_files).where(download_files.c.download_id.in_(expired)))
    return len(expired)
