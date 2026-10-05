"""Authenticated BI, report and dashboard routes for the existing HTTP server."""
from __future__ import annotations

import re
from http import HTTPStatus
from urllib.parse import parse_qs

from server.bi_analytics import overview
from server.reporting import (DATASETS, delete_dashboard, delete_report,
    export_report, get_dashboard, get_report, list_dashboards, list_report_runs,
    list_reports, pin_report, preview_report, run_dashboard, run_saved_report,
    save_dashboard, save_report, set_default_dashboard)

REPORT = re.compile(r"^/api/reports/([0-9a-f]{32})$")
REPORT_RUN = re.compile(r"^/api/reports/([0-9a-f]{32})/run$")
REPORT_RUNS = re.compile(r"^/api/reports/([0-9a-f]{32})/runs$")
DASHBOARD = re.compile(r"^/api/dashboards/([0-9a-f]{32})$")
DASHBOARD_RUN = re.compile(r"^/api/dashboards/([0-9a-f]{32})/run$")


def _error(handler, error: Exception) -> None:
    status = HTTPStatus.NOT_FOUND if isinstance(error, LookupError) else HTTPStatus.BAD_REQUEST
    handler._json({"error": str(error)}, status)


def handle_get(handler, parsed) -> bool:
    path = parsed.path
    if not path.startswith(("/api/analytics/", "/api/reports", "/api/dashboards")):
        return False
    user_id = handler._current_user()["id"]
    params = parse_qs(parsed.query)
    one = lambda key, default="": str((params.get(key) or [default])[0])[:320]
    try:
        if path == "/api/analytics/overview":
            filters = {key: one(key) for key in ("from", "to", "status", "location",
                "investor_name", "procuring_entity_name", "winning_contractor",
                "selection_method", "contract_type", "price_min", "price_max") if one(key)}
            handler._json(overview(filters, one("period", "month"),
                results_only=one("results_only") == "1"))
            return True
        if path == "/api/reports/schema":
            handler._json({"datasets": {name: {"fields": list(item.fields),
                "numeric": sorted(item.numeric), "dates": sorted(item.dates),
                "default_columns": list(item.default_columns)}
                for name, item in DATASETS.items()}})
            return True
        if path == "/api/reports":
            handler._json({"items": list_reports(user_id)})
            return True
        if path == "/api/reports/runs":
            handler._json({"items": list_report_runs(user_id)})
            return True
        if path == "/api/dashboards":
            handler._json({"items": list_dashboards(user_id)})
            return True
        match = REPORT.fullmatch(path)
        if match:
            result = get_report(user_id, match.group(1))
            if result is None:
                raise LookupError("Không tìm thấy báo cáo của tài khoản này.")
            handler._json(result)
            return True
        match = REPORT_RUNS.fullmatch(path)
        if match:
            if not get_report(user_id, match.group(1)):
                raise LookupError("Không tìm thấy báo cáo của tài khoản này.")
            handler._json({"items": list_report_runs(user_id, match.group(1))})
            return True
        match = DASHBOARD.fullmatch(path)
        if match:
            result = get_dashboard(user_id, match.group(1))
            if result is None:
                raise LookupError("Không tìm thấy dashboard của tài khoản này.")
            handler._json(result)
            return True
    except (ValueError, TypeError, LookupError) as exc:
        _error(handler, exc)
        return True
    return False


def handle_post(handler, path: str, body: dict) -> bool:
    if not path.startswith(("/api/reports", "/api/dashboards")):
        return False
    user_id = handler._current_user()["id"]
    try:
        if path == "/api/reports/preview":
            handler._json(preview_report(body.get("spec"),
                page=body.get("page", 1), page_size=body.get("page_size", 50)))
            return True
        if path == "/api/reports/export":
            spec = body.get("spec")
            report_name = str(body.get("name") or "")[:120]
            if body.get("report_id"):
                saved = get_report(user_id, str(body["report_id"]))
                if not saved:
                    raise LookupError("Không tìm thấy báo cáo của tài khoản này.")
                spec = saved["spec"]
                report_name = saved["name"]
            kind = str(body.get("format") or "xlsx")
            data, filename = export_report(spec, kind, report_name=report_name,
                generated_by=handler._current_user()["email"])
            handler._stores().downloads.add(data, filename, "Báo cáo " + kind.upper())
            mime = ("text/csv; charset=utf-8" if kind == "csv" else
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            handler._send(data, mime, headers={"Content-Disposition":
                f'attachment; filename="{filename}"', "X-Filename": filename})
            return True
        if path == "/api/reports":
            handler._json(save_report(user_id, body), HTTPStatus.CREATED)
            return True
        if path == "/api/dashboards":
            handler._json(save_dashboard(user_id, body), HTTPStatus.CREATED)
            return True
        match = REPORT_RUN.fullmatch(path)
        if match:
            handler._json(run_saved_report(user_id, match.group(1),
                page=body.get("page", 1), page_size=body.get("page_size", 25)))
            return True
        match = REPORT.fullmatch(path)
        if match:
            action = body.get("action", "update")
            if action == "delete":
                if not delete_report(user_id, match.group(1)):
                    raise LookupError("Không tìm thấy báo cáo của tài khoản này.")
                handler._json({"ok": True})
            elif action == "pin":
                handler._json(pin_report(user_id, match.group(1), body.get("pinned") is True))
            elif action == "duplicate":
                saved = get_report(user_id, match.group(1))
                if not saved:
                    raise LookupError("Không tìm thấy báo cáo của tài khoản này.")
                handler._json(save_report(user_id, {"name": saved["name"] + " (bản sao)",
                    "description": saved["description"], "spec": saved["spec"]}),
                    HTTPStatus.CREATED)
            elif action == "update":
                handler._json(save_report(user_id, body, match.group(1)))
            else:
                raise ValueError("Thao tác báo cáo không hợp lệ.")
            return True
        match = DASHBOARD_RUN.fullmatch(path)
        if match:
            handler._json(run_dashboard(user_id, match.group(1)))
            return True
        match = DASHBOARD.fullmatch(path)
        if match:
            action = body.get("action", "update")
            if action == "delete":
                if not delete_dashboard(user_id, match.group(1)):
                    raise LookupError("Không tìm thấy dashboard của tài khoản này.")
                handler._json({"ok": True})
            elif action == "default":
                handler._json(set_default_dashboard(user_id, match.group(1)))
            elif action == "update":
                handler._json(save_dashboard(user_id, body, match.group(1)))
            else:
                raise ValueError("Thao tác dashboard không hợp lệ.")
            return True
    except (ValueError, TypeError, LookupError) as exc:
        _error(handler, exc)
        return True
    return False
