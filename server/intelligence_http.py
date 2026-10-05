"""Authenticated HTTP routes for the public-data intelligence workspace."""
from __future__ import annotations

import re
import time
import logging
from http import HTTPStatus
from urllib.parse import parse_qs

from server.intelligence import (admin_data_stats, analytics, compare_tenders,
    deadline_center, entity_profile, get_plan, get_tender, list_tenders)
from server.intelligence_jobs import enqueue_tender, job_status, sync_center
from server.tender_source import refresh_tender
from server.search_engine import (record_search_metric, search as unified_search,
                                  search_metrics)

TENDER = re.compile(r"^/api/intelligence/tenders/(IB[0-9A-Z-]{6,32})$")
REFRESH = re.compile(r"^/api/intelligence/tenders/(IB[0-9A-Z-]{6,32})/refresh$")
PLAN = re.compile(r"^/api/intelligence/plans/(PL[0-9A-Z]{6,30})$")
ENTITY = re.compile(r"^/api/intelligence/entities/(investor|contractor|procurer)/([0-9a-f]{32})$")
JOB = re.compile(r"^/api/intelligence/jobs/([0-9a-f]{32})$")


def _param(query: dict, key: str, default: str = "") -> str:
    return str((query.get(key) or [default])[0])[:500]


def handle_get(handler, parsed) -> bool:
    path = parsed.path
    if not path.startswith("/api/intelligence/"):
        return False
    query = parse_qs(parsed.query)
    try:
        if path == "/api/intelligence/admin/search-metrics":
            if handler._current_user()["role"] != "admin":
                handler._json({"error": "Không có quyền quản trị."}, HTTPStatus.FORBIDDEN)
            else:
                handler._json(search_metrics(int(_param(query, "days", "14"))))
            return True
        if path in {"/api/intelligence/search", "/api/intelligence/suggest"}:
            suggestions = path.endswith("/suggest")
            started = time.monotonic()
            result = unified_search(q=_param(query, "q"),
                page=1 if suggestions else int(_param(query, "page", "1")),
                page_size=10 if suggestions else int(_param(query, "page_size", "25")),
                kind=_param(query, "kind"), status=_param(query, "status"),
                location=_param(query, "location"), investor=_param(query, "investor"),
                procurer=_param(query, "procurer"), contractor=_param(query, "contractor"),
                from_date=_param(query, "from"), to_date=_param(query, "to"),
                deadline_from=_param(query, "deadline_from"),
                deadline_to=_param(query, "deadline_to"),
                price_min=_param(query, "price_min"), price_max=_param(query, "price_max"),
                selection_method=_param(query, "selection_method"),
                contract_type=_param(query, "contract_type"),
                results_only=_param(query, "results") == "1",
                sort=_param(query, "sort", "relevance"),
                order=_param(query, "order", "desc"),
                force_refresh=_param(query, "refresh") == "1")
            handler._json(result)
            if not suggestions:
                try:
                    record_search_metric(_param(query, "kind"),
                        int((time.monotonic() - started) * 1000), result)
                except Exception:
                    logging.exception("Could not aggregate local search metric")
            return True
        if path == "/api/intelligence/tenders":
            handler._json(list_tenders(page=int(_param(query, "page", "1")),
                page_size=int(_param(query, "page_size", "50")),
                query=_param(query, "q"), status=_param(query, "status"),
                investor_id=_param(query, "investor_id"),
                contractor_id=_param(query, "contractor_id"),
                from_date=_param(query, "from"), to_date=_param(query, "to"),
                sort=_param(query, "sort", "published"),
                descending=_param(query, "order", "desc") != "asc",
                results_only=_param(query, "results") == "1"))
            return True
        if path == "/api/intelligence/analytics":
            handler._json(analytics(_param(query, "period", "month"),
                                    _param(query, "from"), _param(query, "to")))
            return True
        if path == "/api/intelligence/deadlines":
            handler._json(deadline_center(int(_param(query, "days", "30")),
                int(_param(query, "page", "1")), int(_param(query, "page_size", "50"))))
            return True
        if path == "/api/intelligence/compare":
            handler._json(compare_tenders(query.get("code", [])))
            return True
        if path == "/api/intelligence/admin/sync":
            if handler._current_user()["role"] != "admin":
                handler._json({"error": "Không có quyền quản trị."}, HTTPStatus.FORBIDDEN)
            else:
                handler._json({"data": admin_data_stats(), "jobs": sync_center()})
            return True
        match = TENDER.fullmatch(path)
        if match:
            result = get_tender(match.group(1))
            if result and result["tender"].get("data_health") == "Dữ liệu cũ":
                # Serve the stored detail immediately; the durable queue
                # refreshes it after the response without source I/O here.
                enqueue_tender(match.group(1), priority="high")
                result["refresh_queued"] = True
            handler._json(result or {"error": "Chưa có dữ liệu gói thầu trong kho đã thu thập."},
                HTTPStatus.OK if result else HTTPStatus.NOT_FOUND)
            return True
        match = PLAN.fullmatch(path)
        if match:
            result = get_plan(match.group(1))
            handler._json(result or {"error": "Chưa có dữ liệu KHLCNT trong kho đã thu thập."},
                HTTPStatus.OK if result else HTTPStatus.NOT_FOUND)
            return True
        match = ENTITY.fullmatch(path)
        if match:
            result = entity_profile(match.group(1), match.group(2),
                page=int(_param(query, "page", "1")),
                page_size=int(_param(query, "page_size", "30")),
                query=_param(query, "q"), status=_param(query, "status"),
                from_date=_param(query, "from"), to_date=_param(query, "to"))
            handler._json(result or {"error": "Không có dữ liệu đơn vị này."},
                HTTPStatus.OK if result else HTTPStatus.NOT_FOUND)
            return True
        match = JOB.fullmatch(path)
        if match:
            result = job_status(match.group(1))
            handler._json(result or {"error": "Không tìm thấy job."},
                HTTPStatus.OK if result else HTTPStatus.NOT_FOUND)
            return True
    except (ValueError, TypeError) as exc:
        handler._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True
    except LookupError as exc:
        handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        return True
    return False


def handle_post(handler, path: str, body: dict) -> bool:
    match = REFRESH.fullmatch(path)
    if match:
        code = match.group(1)
        try:
            result = refresh_tender(code, force=body.get("force") is True)
            handler._json(result)
        except (LookupError, ValueError) as exc:
            handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except Exception:
            # Preserve the failed source lookup as a retryable persistent job.
            job = enqueue_tender(code)
            handler._json({"error": "Không lấy được nguồn e-GP. Đã xếp hàng thử lại.",
                           "retry_job_id": job["id"]}, HTTPStatus.BAD_GATEWAY)
        return True
    return False
