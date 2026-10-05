"""Durable Data Sync 4.5 orchestration over the existing tender refresh queue."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, exists, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from server.database import (audit_logs, background_jobs, followed_tenders, get_db, now,
    saved_searches,
    source_health_events,
    sync_checkpoints, sync_run_items, sync_runs, sync_sources, tenders)
from server.intelligence import clean_code
from server.intelligence_jobs import (enqueue_followed, enqueue_saved_search,
    enqueue_tender, run_pending)
from server.config import source_settings

DEFAULT_SOURCE_ID = "egp-public"
ACTIVE_RUNS = {"queued", "running"}
ACTIVE_JOBS = {"pending", "queued", "retry", "retrying", "running"}
MODES = {"stale", "failed", "codes"}
TRIGGERS = {"manual", "scheduler", "automation"}


def _id() -> str:
    return uuid.uuid4().hex


def ensure_default_source() -> dict:
    """Create the public e-GP source once without storing credentials."""
    with get_db().engine.connect() as conn:
        current = conn.execute(select(sync_sources).where(
            sync_sources.c.id == DEFAULT_SOURCE_ID)).mappings().first()
    if current:
        return dict(current)
    stamp = now()
    try:
        with get_db().engine.begin() as conn:
            conn.execute(insert(sync_sources).values(id=DEFAULT_SOURCE_ID,
                name="Hệ thống mạng đấu thầu quốc gia (e-GP)", kind="egp-public",
                is_enabled=True, schedule_minutes=30,
                config_json={"stale_hours": 6, "batch_size": 20},
                last_run_at=None, next_run_at=stamp,
                created_at=stamp, updated_at=stamp))
    except IntegrityError:
        pass
    with get_db().engine.connect() as conn:
        return dict(conn.execute(select(sync_sources).where(
            sync_sources.c.id == DEFAULT_SOURCE_ID)).mappings().one())


def _candidate_codes(mode: str, codes: list[str] | None, limit: int,
                     stale_hours: int) -> list[str]:
    if mode == "codes":
        cleaned = [clean_code(code) for code in (codes or [])]
        return list(dict.fromkeys(code for code in cleaned if code))[:limit]
    with get_db().engine.connect() as conn:
        query = select(tenders.c.tender_code)
        if mode == "failed":
            query = query.where(tenders.c.sync_error.is_not(None))
        else:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=stale_hours)).isoformat(
                timespec="seconds")
            query = query.where(or_(tenders.c.last_synced_at.is_(None),
                                    tenders.c.last_synced_at < cutoff))
        followed = exists(select(followed_tenders.c.id).where(
            followed_tenders.c.tender_code == tenders.c.tender_code))
        rows = conn.execute(query.order_by(case((followed, 0), else_=1),
            tenders.c.last_synced_at.asc(),
            tenders.c.tender_code).limit(limit)).scalars().all()
    return list(rows)


def _active_run(source_id: str) -> dict | None:
    with get_db().engine.connect() as conn:
        row = conn.execute(select(sync_runs).where(
            sync_runs.c.source_id == source_id,
            sync_runs.c.status.in_(ACTIVE_RUNS))
            .order_by(sync_runs.c.created_at.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def start_sync(*, requested_by: str | None = None, trigger: str = "manual",
               mode: str = "stale", codes: list[str] | None = None,
               limit: int = 100, source_id: str = DEFAULT_SOURCE_ID) -> dict:
    if trigger not in TRIGGERS:
        raise ValueError("Nguồn kích hoạt đồng bộ không hợp lệ.")
    if mode not in MODES:
        raise ValueError("Chế độ đồng bộ không hợp lệ.")
    limit = max(1, min(int(limit), 500))
    source = ensure_default_source()
    if source_id != source["id"]:
        raise LookupError("Không tìm thấy nguồn đồng bộ.")
    if not source["is_enabled"]:
        raise ValueError("Nguồn đồng bộ đang tạm dừng.")
    active = _active_run(source_id)
    if active:
        return active | {"reused": True}
    stale_hours = max(1, min(int((source.get("config_json") or {}).get(
        "stale_hours", 6)), 168))
    selected = _candidate_codes(mode, codes, limit, stale_hours)
    run_id, stamp = _id(), now()
    with get_db().engine.begin() as conn:
        # Serialize run creation on PostgreSQL; SQLite writes are serialized by the engine.
        conn.execute(select(sync_sources.c.id).where(sync_sources.c.id == source_id)
                     .with_for_update()).first()
        existing = conn.execute(select(sync_runs).where(
            sync_runs.c.source_id == source_id,
            sync_runs.c.status.in_(ACTIVE_RUNS)).limit(1)).mappings().first()
        if existing:
            return dict(existing) | {"reused": True}
        conn.execute(insert(sync_runs).values(id=run_id, source_id=source_id,
            requested_by=requested_by, trigger=trigger, mode=mode,
            status="queued" if selected else "completed",
            discovered_count=len(selected), queued_count=0, processed_count=0,
            success_count=0, failed_count=0, cursor_json=None,
            error_message=None, started_at=stamp if selected else None,
            finished_at=None if selected else stamp, created_at=stamp))
        if not selected:
            next_at = (datetime.now(timezone.utc) + timedelta(
                minutes=max(5, source["schedule_minutes"]))).isoformat(timespec="seconds")
            conn.execute(update(sync_sources).where(sync_sources.c.id == source_id)
                .values(last_run_at=stamp, next_run_at=next_at, updated_at=stamp))
            _write_checkpoint(conn, source_id, success=True,
                              cursor={"last_entity_id": ""}, error=None)
        if requested_by:
            conn.execute(insert(audit_logs).values(id=_id(), user_id=requested_by,
                action="data_sync_started", entity_type="sync_run",
                entity_id=run_id, created_at=stamp))
    queued = []
    try:
        with get_db().engine.connect() as conn:
            followed_codes = set(conn.execute(select(followed_tenders.c.tender_code).where(
                followed_tenders.c.tender_code.in_(selected))).scalars().all())
        for code in selected:
            job = enqueue_tender(code, priority=(
                "high" if trigger in {"manual", "automation"} or code in followed_codes
                else "normal"))
            queued.append({"id": _id(), "run_id": run_id, "job_id": job["id"],
                "entity_type": "tender", "entity_id": code,
                "status": job["status"], "attempts": job.get("attempts", 0),
                "error_message": job.get("last_error"),
                "created_at": stamp, "updated_at": stamp})
        if queued:
            with get_db().engine.begin() as conn:
                conn.execute(insert(sync_run_items), queued)
                conn.execute(update(sync_runs).where(sync_runs.c.id == run_id).values(
                    status="running", queued_count=len(queued)))
    except Exception as exc:
        with get_db().engine.begin() as conn:
            conn.execute(update(sync_runs).where(sync_runs.c.id == run_id).values(
                status="failed", error_message=str(exc)[:300], finished_at=now()))
        raise
    return get_run(run_id) or {"id": run_id}


def get_run(run_id: str) -> dict | None:
    if len(run_id) != 32 or any(char not in "0123456789abcdef" for char in run_id):
        return None
    with get_db().engine.connect() as conn:
        run = conn.execute(select(sync_runs).where(sync_runs.c.id == run_id)).mappings().first()
        if not run:
            return None
        items = conn.execute(select(sync_run_items).where(
            sync_run_items.c.run_id == run_id).order_by(sync_run_items.c.created_at)
            .limit(500)).mappings().all()
    return dict(run) | {"items": [dict(item) for item in items]}


def _write_checkpoint(conn, source_id: str, *, success: bool,
                      cursor: dict | None, error: str | None) -> None:
    existing = conn.scalar(select(sync_checkpoints.c.source_id).where(
        sync_checkpoints.c.source_id == source_id,
        sync_checkpoints.c.stream == "tenders"))
    values = {"cursor_json": cursor, "last_success_at": now() if success else None,
              "last_error": error, "updated_at": now()}
    if existing:
        update_values = {"cursor_json": cursor, "last_error": error,
                         "updated_at": values["updated_at"]}
        if success:
            update_values["last_success_at"] = values["last_success_at"]
        conn.execute(update(sync_checkpoints).where(
            sync_checkpoints.c.source_id == source_id,
            sync_checkpoints.c.stream == "tenders").values(**update_values))
    else:
        conn.execute(insert(sync_checkpoints).values(source_id=source_id,
            stream="tenders", **values))


def reconcile_runs(run_id: str = "") -> list[dict]:
    with get_db().engine.connect() as conn:
        conditions = [sync_runs.c.status.in_(ACTIVE_RUNS)]
        if run_id:
            conditions.append(sync_runs.c.id == run_id)
        runs = conn.execute(select(sync_runs).where(*conditions)
            .order_by(sync_runs.c.created_at)).mappings().all()
    updated = []
    for raw_run in runs:
        run = dict(raw_run)
        with get_db().engine.begin() as conn:
            items = conn.execute(select(sync_run_items).where(
                sync_run_items.c.run_id == run["id"])).mappings().all()
            job_ids = [item["job_id"] for item in items if item["job_id"]]
            jobs = {row["id"]: row for row in (conn.execute(select(background_jobs)
                .where(background_jobs.c.id.in_(job_ids))).mappings().all() if job_ids else [])}
            for item in items:
                job = jobs.get(item["job_id"])
                if not job:
                    continue
                conn.execute(update(sync_run_items).where(sync_run_items.c.id == item["id"])
                    .values(status=job["status"], attempts=job["attempts"],
                            error_message=job["last_error"], updated_at=now()))
            statuses = [jobs[item["job_id"]]["status"] for item in items
                        if item["job_id"] in jobs]
            success = statuses.count("completed")
            failed = statuses.count("failed")
            processed = success + failed
            active = any(status in ACTIVE_JOBS for status in statuses)
            values = {"processed_count": processed, "success_count": success,
                      "failed_count": failed}
            if not active and len(statuses) >= run["queued_count"]:
                final = "completed" if not failed else "failed" if not success else "partial"
                error = f"{failed} mục đồng bộ lỗi." if failed else None
                cursor = {"last_entity_id": max((item["entity_id"] for item in items),
                                                 default="")}
                values |= {"status": final, "finished_at": now(),
                           "error_message": error, "cursor_json": cursor}
                source = conn.execute(select(sync_sources).where(
                    sync_sources.c.id == run["source_id"])).mappings().one()
                next_at = (datetime.now(timezone.utc) + timedelta(
                    minutes=max(5, source["schedule_minutes"]))).isoformat(timespec="seconds")
                conn.execute(update(sync_sources).where(sync_sources.c.id == run["source_id"])
                    .values(last_run_at=now(), next_run_at=next_at, updated_at=now()))
                _write_checkpoint(conn, run["source_id"], success=not failed,
                                  cursor=cursor, error=error)
            conn.execute(update(sync_runs).where(sync_runs.c.id == run["id"]).values(**values))
        current = get_run(run["id"])
        if current:
            updated.append(current)
    return updated


def process_sync(*, run_id: str = "", limit: int | None = None) -> dict:
    if run_id and get_run(run_id) is None:
        raise LookupError("Không tìm thấy lượt đồng bộ.")
    batch_limit = source_settings()["sync_batch_size"] if limit is None else int(limit)
    queue_result = run_pending(max(1, min(batch_limit, 20)))
    runs = reconcile_runs(run_id)
    return {"queue": queue_result, "runs": runs}


def retry_run(run_id: str, requested_by: str | None = None) -> dict:
    run = get_run(run_id)
    if not run:
        raise LookupError("Không tìm thấy lượt đồng bộ.")
    if run["status"] not in {"failed", "partial"}:
        raise ValueError("Chỉ có thể thử lại lượt đồng bộ đang lỗi.")
    codes = [item["entity_id"] for item in run["items"] if item["status"] == "failed"]
    return start_sync(requested_by=requested_by, trigger="manual", mode="codes",
                      codes=codes, limit=max(1, len(codes)), source_id=run["source_id"])


def scheduler_tick(limit: int | None = None) -> dict:
    limit = source_settings()["sync_batch_size"] if limit is None else int(limit)
    source = ensure_default_source()
    stamp = now()
    started = None
    if source["is_enabled"] and (not source["next_run_at"] or source["next_run_at"] <= stamp):
        started = start_sync(trigger="scheduler", mode="stale",
                             limit=max(1, min(limit * 4, 100)))
    scheduled = {"followed": 0, "saved_searches": 0}
    if source["is_enabled"]:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(
            timespec="seconds")
        with get_db().engine.connect() as conn:
            followed_ids = conn.execute(select(followed_tenders.c.id).where(
                or_(followed_tenders.c.last_checked_at.is_(None),
                    followed_tenders.c.last_checked_at < cutoff))
                .order_by(followed_tenders.c.last_checked_at.asc()).limit(limit)).scalars().all()
            search_ids = conn.execute(select(saved_searches.c.id).where(
                saved_searches.c.is_watch_enabled.is_(True),
                or_(saved_searches.c.last_run_at.is_(None),
                    saved_searches.c.last_run_at < cutoff))
                .order_by(saved_searches.c.last_run_at.asc()).limit(limit)).scalars().all()
        for followed_id in followed_ids:
            enqueue_followed(followed_id)
        for search_id in search_ids:
            enqueue_saved_search(search_id)
        scheduled = {"followed": len(followed_ids), "saved_searches": len(search_ids)}
    processed = process_sync(limit=limit)
    return {"status": "done", "started": started, "scheduled": scheduled, **processed}


def sync_overview() -> dict:
    ensure_default_source()
    with get_db().engine.connect() as conn:
        sources = conn.execute(select(sync_sources).order_by(sync_sources.c.name)).mappings().all()
        runs = conn.execute(select(sync_runs).order_by(sync_runs.c.created_at.desc())
            .limit(50)).mappings().all()
        checkpoints = conn.execute(select(sync_checkpoints)).mappings().all()
        queue = conn.execute(select(background_jobs.c.job_type,
            background_jobs.c.status, func.count().label("count"))
            .group_by(background_jobs.c.job_type, background_jobs.c.status)).mappings().all()
        health_events = conn.execute(select(source_health_events)
            .order_by(source_health_events.c.created_at.desc()).limit(20)).mappings().all()
    from server.intelligence_jobs import sync_center
    from server.source.request_manager import get_request_manager
    return {"sources": [dict(row) for row in sources],
            "runs": [dict(row) for row in runs],
            "checkpoints": [dict(row) for row in checkpoints],
            "queue": [dict(row) for row in queue],
            "health_events": [dict(row) for row in health_events],
            "jobs": sync_center()["recent"],
            "metrics": get_request_manager().metrics()}


def set_source_enabled(source_id: str, enabled: bool,
                       requested_by: str | None = None) -> dict:
    ensure_default_source()
    with get_db().engine.begin() as conn:
        source = conn.execute(select(sync_sources).where(
            sync_sources.c.id == source_id)).mappings().first()
        if not source:
            raise LookupError("Không tìm thấy nguồn đồng bộ.")
        conn.execute(update(sync_sources).where(sync_sources.c.id == source_id).values(
            is_enabled=enabled, next_run_at=now() if enabled else None, updated_at=now()))
        if requested_by:
            conn.execute(insert(audit_logs).values(id=_id(), user_id=requested_by,
                action="data_sync_source_enabled" if enabled else "data_sync_source_paused",
                entity_type="sync_source", entity_id=source_id, created_at=now()))
    with get_db().engine.connect() as conn:
        return dict(conn.execute(select(sync_sources).where(
            sync_sources.c.id == source_id)).mappings().one())
