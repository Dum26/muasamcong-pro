"""Admin-only Data Quality Center endpoints."""
from __future__ import annotations

import re
from http import HTTPStatus
from urllib.parse import parse_qs

from server.data_quality import service

PREFIX = "/api/admin/data-quality"


def _admin(handler) -> bool:
    if handler._current_user()["role"] != "admin":
        handler._json({"error": "Không có quyền quản trị chất lượng dữ liệu."}, HTTPStatus.FORBIDDEN)
        return False
    return True


def handle_get(handler, parsed) -> bool:
    if not parsed.path.startswith(PREFIX):
        return False
    if not _admin(handler):
        return True
    query = parse_qs(parsed.query)
    value = lambda name, default="": (query.get(name) or [default])[0]
    try:
        if parsed.path == PREFIX + "/summary":
            result = service.summary()
        elif parsed.path == PREFIX + "/issues":
            result = service.list_issues(status=value("status", "open"),
                severity=value("severity"), entity_type=value("entity_type"),
                rule=value("rule"), page=int(value("page", "1")))
        elif parsed.path == PREFIX + "/duplicates":
            result = service.list_duplicates(page=int(value("page", "1")))
        elif parsed.path == PREFIX + "/runs":
            result = service.run_history(limit=int(value("limit", "20")))
        elif re.fullmatch(re.escape(PREFIX) + r"/issues/[0-9a-f]{32}", parsed.path):
            result = service.issue_detail(parsed.path.rsplit("/", 1)[1])
        else:
            handler._json({"error": "Không tìm thấy tài nguyên."}, HTTPStatus.NOT_FOUND)
            return True
        handler._json(result)
    except ValueError as exc:
        handler._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
    except LookupError as exc:
        handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
    return True


def handle_post(handler, path: str, body: dict) -> bool:
    if not path.startswith(PREFIX):
        return False
    if not _admin(handler):
        return True
    try:
        if path == PREFIX + "/scan":
            result = service.queue_scan(str(body.get("run_type") or "incremental"))
            handler._json(result, HTTPStatus.ACCEPTED)
            return True
        if path == PREFIX + "/scan/process":
            handler._json(service.process_scan_batch())
            return True
        safe_fix = re.fullmatch(re.escape(PREFIX) + r"/issues/([0-9a-f]{32})/fix", path)
        if safe_fix:
            handler._json(service.fix_safe_whitespace(safe_fix.group(1),
                handler._current_user()["id"]))
            return True
        revert = re.fullmatch(re.escape(PREFIX) + r"/fixes/([0-9a-f]{32})/revert", path)
        if revert:
            handler._json(service.revert_safe_fix(revert.group(1),
                handler._current_user()["id"]))
            return True
        issue = re.fullmatch(re.escape(PREFIX) + r"/issues/([0-9a-f]{32})/(review|resolve|ignore)", path)
        if issue:
            handler._json(service.review_issue(issue.group(1), issue.group(2),
                handler._current_user()["id"]))
            return True
        candidate = re.fullmatch(re.escape(PREFIX) + r"/duplicates/([0-9a-f]{32})/(not_duplicate|ignore)", path)
        if candidate:
            action = "ignored" if candidate.group(2) == "ignore" else "not_duplicate"
            handler._json(service.review_duplicate(candidate.group(1), action,
                handler._current_user()["id"]))
            return True
        merge = re.fullmatch(re.escape(PREFIX) + r"/duplicates/([0-9a-f]{32})/merge", path)
        if merge:
            handler._json(service.merge_duplicate(merge.group(1),
                str(body.get("target_id") or ""), handler._current_user()["id"]))
            return True
    except ValueError as exc:
        handler._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True
    except LookupError as exc:
        handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        return True
    handler._json({"error": "Không tìm thấy thao tác."}, HTTPStatus.NOT_FOUND)
    return True
