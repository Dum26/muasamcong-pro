"""Admin-only HTTP surface for Data Sync Engine 4.5."""
from __future__ import annotations

import re
from http import HTTPStatus

from server.data_sync import (get_run, process_sync, retry_run, start_sync,
                              set_source_enabled, sync_overview)
from server.intelligence_jobs import cancel_job, cleanup_jobs, enqueue_tender, retry_job

RUN = re.compile(r"^/api/data-sync/runs/([0-9a-f]{32})$")
RUN_ACTION = re.compile(r"^/api/data-sync/runs/([0-9a-f]{32})/(process|retry)$")
SOURCE_ACTION = re.compile(r"^/api/data-sync/sources/([a-z0-9-]{1,32})/(enable|pause)$")
JOB_ACTION = re.compile(r"^/api/data-sync/jobs/([0-9a-f]{32})/(retry|cancel)$")


def _admin(handler) -> dict:
    user = handler._current_user()
    if user["role"] != "admin":
        raise PermissionError("Không có quyền quản trị đồng bộ dữ liệu.")
    return user


def _error(handler, exc: Exception) -> None:
    status = (HTTPStatus.FORBIDDEN if isinstance(exc, PermissionError) else
              HTTPStatus.NOT_FOUND if isinstance(exc, LookupError) else
              HTTPStatus.BAD_REQUEST)
    handler._json({"error": str(exc)}, status)


def handle_get(handler, path: str) -> bool:
    if not path.startswith("/api/data-sync"):
        return False
    try:
        _admin(handler)
        if path == "/api/data-sync":
            handler._json(sync_overview())
            return True
        if path == "/api/data-sync/metrics":
            handler._json(sync_overview()["metrics"])
            return True
        match = RUN.fullmatch(path)
        if match:
            run = get_run(match.group(1))
            if not run:
                raise LookupError("Không tìm thấy lượt đồng bộ.")
            handler._json(run)
            return True
    except (PermissionError, LookupError, ValueError, TypeError) as exc:
        _error(handler, exc)
        return True
    return False


def handle_post(handler, path: str, body: dict) -> bool:
    if not path.startswith("/api/data-sync"):
        return False
    try:
        user = _admin(handler)
        if path == "/api/data-sync/runs":
            codes = body.get("codes")
            if codes is not None and not isinstance(codes, list):
                raise ValueError("Danh sách mã đồng bộ không hợp lệ.")
            handler._json(start_sync(requested_by=user["id"], trigger="manual",
                mode=str(body.get("mode") or "stale"), codes=codes,
                limit=body.get("limit", 100)), HTTPStatus.CREATED)
            return True
        if path == "/api/data-sync/process":
            handler._json(process_sync(limit=body.get("limit")))
            return True
        if path == "/api/data-sync/cleanup":
            handler._json(cleanup_jobs(body.get("completed_days")))
            return True
        if path == "/api/data-sync/force":
            code = str(body.get("entity_id") or "")
            handler._json(enqueue_tender(code, priority="high"), HTTPStatus.CREATED)
            return True
        match = JOB_ACTION.fullmatch(path)
        if match:
            job_id, action = match.groups()
            handler._json(retry_job(job_id) if action == "retry" else cancel_job(job_id))
            return True
        match = RUN_ACTION.fullmatch(path)
        if match:
            run_id, action = match.groups()
            if action == "process":
                handler._json(process_sync(run_id=run_id, limit=body.get("limit")))
            else:
                handler._json(retry_run(run_id, user["id"]), HTTPStatus.CREATED)
            return True
        match = SOURCE_ACTION.fullmatch(path)
        if match:
            source_id, action = match.groups()
            handler._json(set_source_enabled(source_id, action == "enable", user["id"]))
            return True
    except (PermissionError, LookupError, ValueError, TypeError) as exc:
        _error(handler, exc)
        return True
    return False
