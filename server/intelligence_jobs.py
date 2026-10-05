"""Persistent, bounded source refresh queue for Scheduler or manual retries."""
from __future__ import annotations

import logging
import os
import re
import socket
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, delete, func, insert, or_, select, text, update

from server.database import (background_jobs, followed_tenders, get_db, now,
    saved_searches, sync_run_items, tenders)
from server.intelligence import clean_code
from server.tender_source import refresh_tender
from server.config import production, source_settings
from server.source.errors import SourceError

PRIORITIES = {"high", "normal", "low"}
ACTIVE_STATUSES = {"pending", "queued", "retry", "retrying", "running"}
JOB_TYPES = {"refresh-tender": "tender", "sync-followed": "followed_tender",
             "sync-saved-search": "saved_search"}
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def enqueue_tender(code: str, *, priority: str = "normal") -> dict:
    code = clean_code(code)
    if not re.fullmatch(r"IB[A-Z0-9._-]{4,48}", code):
        raise ValueError("Mã TBMT không hợp lệ.")
    return _enqueue("refresh-tender", code, priority)


def enqueue_followed(followed_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", followed_id):
        raise ValueError("Mã gói theo dõi không hợp lệ.")
    with get_db().engine.connect() as conn:
        if not conn.scalar(select(followed_tenders.c.id).where(
                followed_tenders.c.id == followed_id)):
            raise LookupError("Không tìm thấy gói đang theo dõi.")
    return _enqueue("sync-followed", followed_id, "high")


def enqueue_saved_search(search_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", search_id):
        raise ValueError("Mã bộ lọc đã lưu không hợp lệ.")
    with get_db().engine.connect() as conn:
        if not conn.scalar(select(saved_searches.c.id).where(
                saved_searches.c.id == search_id,
                saved_searches.c.is_watch_enabled.is_(True))):
            raise LookupError("Không tìm thấy bộ lọc đang theo dõi.")
    return _enqueue("sync-saved-search", search_id, "normal")


def _enqueue(job_type: str, entity_id: str, priority: str) -> dict:
    if job_type not in JOB_TYPES:
        raise ValueError("Loại job đồng bộ không hợp lệ.")
    if priority not in PRIORITIES:
        raise ValueError("Mức ưu tiên đồng bộ không hợp lệ.")
    with get_db().engine.begin() as conn:
        if production():
            # Serialize the check/insert pair across Cloud Run workers.
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                         {"key": f"{job_type}:{entity_id}"})
        existing = conn.execute(select(background_jobs).where(
            background_jobs.c.job_type == job_type,
            background_jobs.c.entity_id == entity_id,
            background_jobs.c.status.in_(ACTIVE_STATUSES))
            .order_by(background_jobs.c.created_at.desc()).limit(1)).mappings().first()
        if existing:
            return dict(existing)
        item = dict(id=uuid.uuid4().hex, job_type=job_type,
            entity_type=JOB_TYPES[job_type], entity_id=entity_id,
            status="queued", priority=priority, attempts=0,
            max_attempts=source_settings()["max_retries"], last_error=None,
            next_retry_at=None, locked_at=None, locked_by=None,
            created_at=now(), started_at=None, finished_at=None)
        conn.execute(insert(background_jobs).values(**item))
    return item


def job_status(job_id: str) -> dict | None:
    if len(job_id) != 32 or any(char not in "0123456789abcdef" for char in job_id):
        return None
    with get_db().engine.connect() as conn:
        row = conn.execute(select(background_jobs).where(
            background_jobs.c.id == job_id)).mappings().first()
    return dict(row) if row else None


def run_pending(limit: int = 5, *, job_types: set[str] | None = None) -> dict:
    limit = max(1, min(int(limit), source_settings()["sync_batch_size"]))
    if job_types is not None and (not job_types or not job_types <= JOB_TYPES.keys()):
        raise ValueError("Loại job đồng bộ không hợp lệ.")
    stamp = now()
    expired = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")
    with get_db().engine.begin() as conn:
        conn.execute(update(background_jobs).where(
            background_jobs.c.status == "running", background_jobs.c.started_at < expired,
            background_jobs.c.attempts < background_jobs.c.max_attempts).values(
                status="retry", next_retry_at=stamp, locked_at=None, locked_by=None,
                last_error="Job bị gián đoạn; đang thử lại."))
        conn.execute(update(background_jobs).where(
            background_jobs.c.status == "running", background_jobs.c.started_at < expired,
            background_jobs.c.attempts >= background_jobs.c.max_attempts).values(
                status="failed", finished_at=stamp, locked_at=None, locked_by=None,
                last_error="Job bị gián đoạn quá số lần thử."))
    with get_db().engine.connect() as conn:
        query = select(background_jobs.c.id, background_jobs.c.job_type,
            background_jobs.c.entity_id).where(
                   background_jobs.c.job_type.in_(job_types or JOB_TYPES.keys()),
                   background_jobs.c.status.in_(["pending", "queued", "retry", "retrying"]),
                   or_(background_jobs.c.next_retry_at.is_(None),
                       background_jobs.c.next_retry_at <= stamp))
        rows = conn.execute(query.order_by(case((background_jobs.c.priority == "high", 0),
                           (background_jobs.c.priority == "normal", 1), else_=2),
                      background_jobs.c.created_at).limit(limit)).all()
    success = failed = 0
    outcomes = []
    for job_id, job_type, entity_id in rows:
        with get_db().engine.begin() as conn:
            claimed = conn.execute(update(background_jobs).where(
                background_jobs.c.id == job_id,
                background_jobs.c.status.in_(["pending", "queued", "retry", "retrying"]))
                .values(status="running", attempts=background_jobs.c.attempts + 1,
                        started_at=now(), next_retry_at=None, locked_at=now(),
                        locked_by=WORKER_ID)).rowcount
        if not claimed:
            continue
        try:
            if job_type == "refresh-tender":
                refresh_tender(entity_id, force=True)
                outcome = {}
            elif job_type == "sync-followed":
                from server.background_jobs import sync_followed_item
                outcome = sync_followed_item(entity_id)
            else:
                from server.background_jobs import sync_saved_search_item
                outcome = sync_saved_search_item(entity_id)
            with get_db().engine.begin() as conn:
                conn.execute(update(background_jobs).where(background_jobs.c.id == job_id)
                    .values(status="completed", finished_at=now(), last_error=None,
                            locked_at=None, locked_by=None))
            success += 1
            outcomes.append({"job_id": job_id, "job_type": job_type,
                             "entity_id": entity_id, "status": "completed", **outcome})
        except Exception as exc:
            logging.exception("Sync failed type=%s entity=%s job=%s",
                              job_type, entity_id, job_id)
            with get_db().engine.begin() as conn:
                job = conn.execute(select(background_jobs.c.attempts,
                    background_jobs.c.max_attempts).where(
                    background_jobs.c.id == job_id)).one()
                attempts, max_attempts = job
                retry = attempts < max_attempts and (
                    not isinstance(exc, SourceError) or exc.transient)
                delay = min(3600, 60 * 2 ** max(0, attempts - 1))
                next_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(
                    timespec="seconds") if retry else None
                conn.execute(update(background_jobs).where(background_jobs.c.id == job_id)
                    .values(status="retry" if retry else "failed", last_error=str(exc)[:300],
                            next_retry_at=next_at, finished_at=None if retry else now(),
                            locked_at=None, locked_by=None))
                if job_type == "refresh-tender":
                    conn.execute(update(tenders).where(tenders.c.tender_code == entity_id)
                        .values(sync_error=str(exc)[:300], last_error_at=now(),
                                sync_status="failed", sync_error_code=getattr(exc, "code", "source_error")))
            failed += 1
            outcomes.append({"job_id": job_id, "job_type": job_type,
                             "entity_id": entity_id, "status": "failed"})
    return {"status": "done", "processed": success, "failed": failed,
            "outcomes": outcomes}


def sync_center() -> dict:
    with get_db().engine.connect() as conn:
        counts = conn.execute(select(background_jobs.c.job_type, background_jobs.c.status,
            func.count().label("count")).group_by(background_jobs.c.job_type,
            background_jobs.c.status)).mappings().all()
        recent = conn.execute(select(background_jobs).order_by(
            background_jobs.c.created_at.desc()).limit(50)).mappings().all()
    return {"counts": [dict(row) for row in counts],
            "recent": [dict(row) for row in recent]}


def retry_job(job_id: str) -> dict:
    with get_db().engine.connect() as conn:
        row = conn.execute(select(background_jobs).where(
            background_jobs.c.id == job_id)).mappings().first()
        if not row:
            raise LookupError("Không tìm thấy job đồng bộ.")
        if row["status"] not in {"failed", "cancelled"}:
            raise ValueError("Chỉ có thể thử lại job lỗi hoặc đã hủy.")
    # Preserve the failed job for sync_run_items/history. A retry is a new job.
    if row["job_type"] == "refresh-tender":
        return enqueue_tender(row["entity_id"], priority="high")
    if row["job_type"] == "sync-followed":
        return enqueue_followed(row["entity_id"])
    return enqueue_saved_search(row["entity_id"])


def cancel_job(job_id: str) -> dict:
    with get_db().engine.begin() as conn:
        row = conn.execute(select(background_jobs).where(
            background_jobs.c.id == job_id)).mappings().first()
        if not row:
            raise LookupError("Không tìm thấy job đồng bộ.")
        if row["status"] not in {"pending", "queued", "retry", "retrying"}:
            raise ValueError("Chỉ có thể hủy job đang chờ.")
        conn.execute(update(background_jobs).where(background_jobs.c.id == job_id).values(
            status="cancelled", finished_at=now(), locked_at=None, locked_by=None))
    return job_status(job_id) or {}


def cleanup_jobs(completed_days: int | None = None) -> dict:
    settings = source_settings()
    days = completed_days or settings["completed_job_retention_days"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat(
        timespec="seconds")
    with get_db().engine.begin() as conn:
        removed = conn.execute(delete(background_jobs).where(
            background_jobs.c.status == "completed",
            background_jobs.c.finished_at < cutoff,
            ~background_jobs.c.id.in_(select(sync_run_items.c.job_id).where(
                sync_run_items.c.job_id.is_not(None))))).rowcount
    return {"removed": removed, "cutoff": cutoff}
