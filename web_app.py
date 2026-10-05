# -*- coding: utf-8 -*-
"""Máy chủ web cục bộ cho MuaSamCong Tool.

Không dùng framework bên ngoài để bản đóng gói gọn và chạy được ngay. Máy chủ chỉ
lắng nghe trên 127.0.0.1; dữ liệu tìm kiếm không được công khai ra mạng LAN.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import base64
import csv
import re
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import hmac
import hashlib
import copy
from collections import deque
from http.cookies import SimpleCookie
from dataclasses import asdict, replace
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from app import (App, MuaSamCongClient, ResultRow, Workbook, save_lot_list,
                 extract_notify_no, plan_row_from_search, clean_plan_no, display_plan_no, text_value)
from lot_export import EXPORT_CONTEXT_KEYS
from server.seo import render_html, robots_txt, sitemap_xml
from server.auth import (login as account_login, logout as account_logout,
                  register as account_register, session_user, validate_session_config)
from server.config import APP_VERSION, ai_settings, max_upload_bytes, production, job_secret, storage_backend, validate_production_config
from server.database import get_db
from server.database import user_notifications, users, saved_searches, followed_tenders, search_history, download_history, job_runs, saved_reports, report_runs, user_dashboards, automation_rules, automation_runs, now as db_now
from sqlalchemy import select, update, delete, func


RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WEB_DIR = RESOURCE_DIR / "web"
REACT_DIR = RESOURCE_DIR / "frontend" / "dist"


class RateLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.events: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int, seconds: int) -> bool:
        current = time.monotonic()
        with self.lock:
            events = self.events.setdefault(key, deque())
            while events and current - events[0] >= seconds:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(current)
            if len(self.events) > 10_000:
                self.events = {name: values for name, values in self.events.items()
                               if values and current - values[-1] < 3600}
            return True


RATE_LIMITER = RateLimiter()


class PresetStore:
    """Keep named queries across restarts, independent of the browser port."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def read(self) -> list[dict]:
        with self.lock:
            if not self.path.exists():
                return []
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, list) or any(
                    not isinstance(item, dict) or not isinstance(item.get("id"), str)
                    or not isinstance(item.get("name"), str)
                    or not isinstance(item.get("params"), dict) for item in data
                ):
                    raise ValueError()
                return data
            except (ValueError, OSError) as exc:
                raise ValueError("Không đọc được bộ truy vấn đã lưu. Hãy kiểm tra saved_queries.json.") from exc

    def update(self, body: dict) -> list[dict]:
        with self.lock:
            items = self.read()
            if body.get("action") == "delete":
                items = [item for item in items if item["id"] != body.get("id")]
            elif body.get("action") == "save":
                name = str(body.get("name") or "").strip()
                params = body.get("params")
                if not name or len(name) > 80 or not isinstance(params, dict):
                    raise ValueError("Tên bộ tìm kiếm cần từ 1 đến 80 ký tự.")
                if params.get("mode") not in {"Thông báo mời thầu", "Kế hoạch lựa chọn nhà thầu"}:
                    raise ValueError("Loại truy vấn không hợp lệ.")
                fields = {"mode", "keyword", "use_dates", "date_from", "date_to", "status",
                          "pages", "detail", "fast_mode", "remove_duplicates", "bid_form", "location"}
                params = {key: value for key, value in params.items() if key in fields}
                if len(json.dumps(params, ensure_ascii=False)) > 5000:
                    raise ValueError("Bộ tìm kiếm quá dài.")
                existing = next((item for item in items if item["name"].casefold() == name.casefold()), None)
                item = {"id": existing["id"] if existing else uuid.uuid4().hex,
                        "name": name, "params": params}
                items = [item] + [old for old in items if old["id"] != item["id"]]
                if len(items) > 30:
                    raise ValueError("Đã đủ 30 bộ tìm kiếm. Hãy xóa một bộ trước khi thêm.")
            else:
                raise ValueError("Thao tác bộ tìm kiếm không hợp lệ.")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                                 suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(items, stream, ensure_ascii=False, indent=2)
                os.replace(temporary, self.path)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
            return items


PRESETS = PresetStore((Path(sys.executable).parent if getattr(sys, "frozen", False)
                       else Path(__file__).resolve().parent) / "saved_queries.json")


class WatchlistStore:
    """Persist tender workflow and snapshots, including legacy 2.5 entries."""

    FIELDS = ("package_name", "plan_name", "investor_name", "procuring_entity_name",
              "bid_close_date", "tender_status", "winner", "package_price", "location",
              "bid_form", "lot_file_status", "public_date", "source_url", "plan_no")
    LABELS = {"bid_close_date": "Thời điểm đóng thầu", "tender_status": "Trạng thái",
              "winner": "KQLCNT / nhà thầu trúng", "package_price": "Giá gói thầu",
              "lot_file_status": "Dữ liệu phân lô", "package_name": "Tên gói",
              "plan_name": "Tên kế hoạch", "investor_name": "Chủ đầu tư",
              "procuring_entity_name": "Bên mời thầu", "location": "Địa điểm",
              "bid_form": "Hình thức LCNT", "public_date": "Ngày đăng"}
    WORKFLOW = {"Mới", "Đang xem", "Quan tâm", "Đang xử lý", "Hoàn tất", "Bỏ qua"}
    PRIORITIES = {"Thấp", "Trung bình", "Cao", "Khẩn cấp"}

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    @classmethod
    def _snapshot(cls, row: dict) -> dict:
        return {field: str(row.get(field) or "").strip()[:1000] for field in cls.FIELDS}

    @classmethod
    def _normalize(cls, item: dict) -> dict:
        result = dict(item)
        result.setdefault("workflow_status", "Mới")
        result.setdefault("priority", "Trung bình")
        result.setdefault("note", "")
        result.setdefault("tags", [])
        result.setdefault("pinned", False)
        result.setdefault("changes", [])
        result.setdefault("has_update", False)
        result.setdefault("last_checked", "")
        result.setdefault("fetch_state", "unfetched")
        result.setdefault("fetch_error", "")
        result.setdefault("created_at", "")
        result.setdefault("snapshot", {"package_name": result.get("name", ""),
                                       "investor_name": result.get("investor", ""),
                                       "bid_close_date": result.get("deadline", ""),
                                       "source_url": result.get("url", "")})
        if not isinstance(result["tags"], list):
            result["tags"] = []
        if not isinstance(result["changes"], list):
            result["changes"] = []
        if not isinstance(result["snapshot"], dict):
            result["snapshot"] = {}
        return result

    def read(self) -> list[dict]:
        with self.lock:
            if not self.path.exists():
                return []
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    raise ValueError()
                return [self._normalize(item) for item in data if isinstance(item, dict)
                        and isinstance(item.get("code"), str)]
            except (ValueError, OSError) as exc:
                raise ValueError("Không đọc được danh sách theo dõi.") from exc

    def _write(self, items: list[dict]) -> list[dict]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(items[:500], stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        return items[:500]

    @classmethod
    def _apply_row(cls, item: dict, row: dict) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        old = dict(item.get("snapshot") or {})
        incoming = cls._snapshot(row)
        current = {**old, **{key: value for key, value in incoming.items() if value}}
        changes = []
        for field in cls.FIELDS:
            previous, value = str(old.get(field) or ""), str(current.get(field) or "")
            if previous and value and previous != value and field != "source_url":
                changes.append({"time": now, "field": field, "label": cls.LABELS.get(field, field),
                                "from": previous, "to": value})
            elif not previous and value and field in cls.LABELS and not (
                    field == "lot_file_status" and value in {"Chưa kiểm tra", "Chưa kiểm tra được"}):
                changes.append({"time": now, "field": field, "label": cls.LABELS.get(field, field),
                                "from": "Chưa có dữ liệu", "to": value})
        if changes:
            item["changes"] = (changes + item.get("changes", []))[:100]
            item["has_update"] = True
        item["snapshot"] = current
        item["name"] = current.get("package_name") or current.get("plan_name") or item.get("name", "")
        item["investor"] = current.get("investor_name") or item.get("investor", "")
        item["deadline"] = current.get("bid_close_date") or item.get("deadline", "")
        item["url"] = current.get("source_url") or item.get("url", "")
        item["last_checked"] = now
        item["fetch_state"] = "ok"
        item["fetch_error"] = ""

    def update(self, body: dict) -> list[dict]:
        code = str(body.get("code") or "").strip().upper()
        if not re.fullmatch(r"(?:IB|PL)[A-Z0-9-]{4,40}", code):
            raise ValueError("Mã theo dõi không hợp lệ.")
        with self.lock:
            items = self.read()
            existing = next((item for item in items if item["code"] == code), None)
            action = body.get("action")
            if action == "add":
                if existing is None:
                    existing = self._normalize({"code": code, "name": str(body.get("name") or "")[:300],
                                                "investor": str(body.get("investor") or "")[:200],
                                                "deadline": str(body.get("deadline") or "")[:40],
                                                "url": str(body.get("url") or "")[:1000],
                                                "created_at": datetime.now().isoformat(timespec="seconds")})
                    items.insert(0, existing)
                    if isinstance(body.get("row"), dict):
                        existing["snapshot"] = self._snapshot(body["row"])
                        existing["last_checked"] = datetime.now().isoformat(timespec="seconds")
                        existing["fetch_state"] = "ok"
                elif isinstance(body.get("row"), dict):
                    self._apply_row(existing, body["row"])
            elif action == "remove":
                items = [item for item in items if item["code"] != code]
            elif action == "edit" and existing is not None:
                if "workflow_status" in body:
                    if body["workflow_status"] not in self.WORKFLOW:
                        raise ValueError("Trạng thái xử lý không hợp lệ.")
                    existing["workflow_status"] = body["workflow_status"]
                if "priority" in body:
                    if body["priority"] not in self.PRIORITIES:
                        raise ValueError("Mức ưu tiên không hợp lệ.")
                    existing["priority"] = body["priority"]
                if "note" in body:
                    existing["note"] = str(body["note"])[:5000]
                if "tags" in body:
                    if not isinstance(body["tags"], list):
                        raise ValueError("Tag không hợp lệ.")
                    existing["tags"] = list(dict.fromkeys(str(tag).strip()[:30] for tag in body["tags"]
                                                           if str(tag).strip()))[:15]
                if "pinned" in body:
                    existing["pinned"] = bool(body["pinned"])
            elif action == "mark-read" and existing is not None:
                existing["has_update"] = False
            else:
                raise ValueError("Thao tác theo dõi không hợp lệ.")
            return self._write(items)

    def sync(self, rows: list[dict]) -> list[dict]:
        with self.lock:
            items = self.read()
            by_code = {item["code"]: item for item in items}
            for row in rows[:1000]:
                if not isinstance(row, dict):
                    continue
                code = str(row.get("code") or row.get("notify_no") or "").upper()
                if code in by_code:
                    self._apply_row(by_code[code], row)
            return self._write(items)

    def mark_error(self, code: str, message: str) -> list[dict]:
        with self.lock:
            items = self.read()
            item = next((entry for entry in items if entry["code"] == code), None)
            if item:
                item["fetch_state"] = "error"
                item["fetch_error"] = message[:300]
                item["last_checked"] = datetime.now().isoformat(timespec="seconds")
                return self._write(items)
            return items


WATCHLIST = WatchlistStore((Path(sys.executable).parent if getattr(sys, "frozen", False)
                            else Path(__file__).resolve().parent) / "watchlist.json")


class QueryHistoryStore:
    """Recent searches shared by all local browser ports."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def read(self) -> list[dict]:
        with self.lock:
            if not self.path.exists():
                return []
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    raise ValueError()
                items = [item for item in data if isinstance(item, dict) and
                         item.get("mode") in {"Thông báo mời thầu", "Kế hoạch lựa chọn nhà thầu", "Kho dữ liệu"}][:100]
                for item in items:
                    item.setdefault("id", uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(item, sort_keys=True,
                                      ensure_ascii=False)).hex)
                    item.setdefault("name", item.get("keyword") or "Tất cả TBMT")
                    item.setdefault("pinned", False)
                    item.setdefault("result_count", None)
                return items
            except (ValueError, OSError) as exc:
                raise ValueError("Không đọc được lịch sử truy vấn.") from exc

    def add(self, body: dict) -> list[dict]:
        params = body.get("params")
        if not isinstance(params, dict) or params.get("mode") not in {
                "Thông báo mời thầu", "Kế hoạch lựa chọn nhà thầu", "Kho dữ liệu"}:
            raise ValueError("Truy vấn lịch sử không hợp lệ.")
        fields = {"mode", "keyword", "use_dates", "date_from", "date_to", "status",
                  "pages", "detail", "fast_mode", "remove_duplicates", "bid_form", "location",
                  "kind", "sort", "page_size", "from", "to", "deadline_from", "deadline_to",
                  "investor", "procurer", "contractor", "selection_method", "contract_type",
                  "price_min", "price_max", "results"}
        item = {key: value for key, value in params.items() if key in fields}
        if len(json.dumps(item, ensure_ascii=False)) > 5000:
            raise ValueError("Truy vấn lịch sử quá dài.")
        item["time"] = datetime.now().isoformat(timespec="seconds")
        with self.lock:
            previous = self.read()
            same = next((old for old in previous if all(old.get(key) == item.get(key) for key in fields)), None)
            item.update({"id": same["id"] if same else uuid.uuid4().hex,
                         "name": same.get("name") if same else item.get("keyword") or "Tất cả TBMT",
                         "pinned": same.get("pinned", False) if same else False,
                         "result_count": None})
            items = [item] + [old for old in previous if old["id"] != item["id"]]
            items = items[:100]
            return self._write(items)

    def _write(self, items: list[dict]) -> list[dict]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(items, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        return items

    def update(self, body: dict) -> list[dict]:
        action = body.get("action")
        with self.lock:
            items = self.read()
            if action == "complete":
                params = body.get("params")
                if not isinstance(params, dict):
                    raise ValueError("Truy vấn lịch sử không hợp lệ.")
                fields = {"mode", "keyword", "use_dates", "date_from", "date_to", "status",
                          "pages", "detail", "fast_mode", "remove_duplicates", "bid_form", "location",
                          "kind", "sort", "page_size", "from", "to", "deadline_from", "deadline_to",
                          "investor", "procurer", "contractor", "selection_method", "contract_type",
                          "price_min", "price_max", "results"}
                item = next((old for old in items if all(old.get(key) == params.get(key) for key in fields)), None)
                if item is not None:
                    item["result_count"] = max(0, int(body.get("result_count") or 0))
            else:
                item = next((old for old in items if old["id"] == body.get("id")), None)
                if item is None:
                    raise ValueError("Không tìm thấy truy vấn lịch sử.")
                if action == "pin":
                    item["pinned"] = bool(body.get("pinned"))
                elif action == "rename":
                    name = str(body.get("name") or "").strip()
                    if not name or len(name) > 80:
                        raise ValueError("Tên lịch sử cần từ 1 đến 80 ký tự.")
                    item["name"] = name
                elif action == "delete":
                    items = [old for old in items if old["id"] != item["id"]]
                else:
                    raise ValueError("Thao tác lịch sử không hợp lệ.")
            return self._write(items)


HISTORY = QueryHistoryStore((Path(sys.executable).parent if getattr(sys, "frozen", False)
                             else Path(__file__).resolve().parent) / "query_history.json")


class Value:
    """Thay cho Tk variable khi dùng lại bộ máy tìm kiếm ở chế độ web."""

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class SearchJob:
    def __init__(self, params: dict, owner: str = ""):
        self.id = uuid.uuid4().hex
        self.owner = owner
        self.params = params
        self.state = "queued"
        self.message = "Đang xếp hàng…"
        self.rows: list[ResultRow] = []
        self.source_count = 0
        self.error = ""
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.lock = threading.Lock()

    def update(self, kind: str, payload):
        with self.lock:
            self.updated_at = time.time()
            if kind == "status":
                self.state = "running"
                self.message = str(payload)
            elif kind == "source_count":
                self.source_count = int(payload)
            elif kind == "done":
                self.state = "done"
                self.rows = list(payload)
                self.message = f"Hoàn tất - {len(self.rows)} kết quả"
            elif kind == "error":
                self.state = "error"
                self.error = str(payload)
                self.message = "Không thể hoàn tất truy vấn"

    def public_data(self, include_rows: bool = False) -> dict:
        with self.lock:
            data = {
                "id": self.id,
                "state": self.state,
                "message": self.message,
                "error": self.error,
                "count": len(self.rows),
                "source_count": self.source_count or len(self.rows),
                "fetched_at": datetime.fromtimestamp(self.updated_at).isoformat(timespec="seconds") if self.state == "done" else "",
            }
            if include_rows and self.state == "done":
                data["rows"] = [row_to_public_dict(row, i) for i, row in enumerate(self.rows)]
            return data


class JobQueue:
    def __init__(self, job: SearchJob):
        self.job = job

    def put(self, item):
        kind, payload = item
        self.job.update(kind, payload)


class JobStore:
    def __init__(self):
        self.jobs: dict[str, SearchJob] = {}
        self.lock = threading.Lock()

    def create(self, params: dict, owner: str = "") -> SearchJob:
        job = SearchJob(params, owner)
        with self.lock:
            self.jobs[job.id] = job
            # Giữ tối đa 20 truy vấn gần nhất trong bộ nhớ.
            old = sorted(self.jobs.values(), key=lambda item: item.created_at)[:-20]
            for item in old:
                self.jobs.pop(item.id, None)
        return job

    def get(self, job_id: str) -> SearchJob | None:
        with self.lock:
            return self.jobs.get(job_id)

    def find_cached(self, params: dict, max_age: int = 120, owner: str = "") -> SearchJob | None:
        key = json.dumps(params, ensure_ascii=False, sort_keys=True)
        now = time.time()
        with self.lock:
            candidates = [
                job for job in self.jobs.values()
                if job.owner == owner and job.state == "done" and now - job.updated_at <= max_age
                and json.dumps(job.params, ensure_ascii=False, sort_keys=True) == key
            ]
        return max(candidates, key=lambda job: job.updated_at, default=None)


JOBS = JobStore()
EXTRACTIONS: dict[str, dict] = {}
EXTRACTIONS_LOCK = threading.Lock()
PROCUREMENT_CODE_RE = re.compile(r"\b(?:IB|PL)\d{8,14}(?:-\d{2})?\b", re.IGNORECASE)


def _cell_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_grid(sheet_name: str, rows, output: list[dict]) -> None:
    """Quét một lưới, đồng thời lấy giá trị ở ô ngay bên dưới mã tìm thấy."""
    from openpyxl.utils import get_column_letter

    pending: dict[int, list[tuple[dict, int]]] = {}
    for row_number, raw_row in enumerate(rows, 1):
        row = list(raw_row)
        for record, column in pending.pop(row_number, []):
            record["below_value"] = _cell_text(row[column - 1]) if column <= len(row) else ""
        for column, value in enumerate(row, 1):
            text = _cell_text(value)
            if not text:
                continue
            for matched in PROCUREMENT_CODE_RE.findall(text):
                code = re.sub(r"-\d{2}$", "", matched.upper())
                record = {
                    "code": code,
                    "code_type": "KHLCNT" if code.startswith("PL") else "TBMT",
                    "source": sheet_name,
                    "cell": f"{get_column_letter(column)}{row_number}",
                    "matched_value": text,
                    "below_value": "",
                }
                output.append(record)
                pending.setdefault(row_number + 1, []).append((record, column))


def extract_tbmt_codes(*, text: str = "", file_data: bytes = b"", filename: str = "",
                       remove_duplicates: bool = True,
                       text_source: str = "Dữ liệu dán") -> list[dict]:
    output: list[dict] = []
    if text.strip():
        _extract_grid(text_source or "Dữ liệu dán", ((line,) for line in text.splitlines()), output)

    if file_data:
        suffix = Path(filename).suffix.lower()
        if suffix == ".xlsx":
            from openpyxl import load_workbook
            workbook = load_workbook(BytesIO(file_data), read_only=True, data_only=True)
            try:
                for sheet in workbook.worksheets:
                    _extract_grid(sheet.title, sheet.iter_rows(values_only=True), output)
            finally:
                workbook.close()
        elif suffix in {".csv", ".txt"}:
            decoded = file_data.decode("utf-8-sig", errors="replace")
            rows = csv.reader(decoded.splitlines()) if suffix == ".csv" else ((line,) for line in decoded.splitlines())
            _extract_grid(Path(filename).name or "Tệp dữ liệu", rows, output)
        else:
            raise ValueError("Chỉ hỗ trợ tệp .xlsx, .csv hoặc .txt.")

    if remove_duplicates:
        unique = []
        seen = set()
        for record in output:
            if record["code"] in seen:
                continue
            seen.add(record["code"])
            unique.append(record)
        output = unique
    return output


def extraction_fields(row: ResultRow) -> dict:
    return {"tender_status": row.tender_status, "location": row.location,
            "bid_form": row.bid_form, "title": row.package_name or row.plan_name,
            "investor_name": row.investor_name, "lookup_error": ""}


def lookup_notice_fields(code: str) -> dict:
    client = MuaSamCongClient()
    try:
        records = client.search_notices(code, max_pages=1)
        notice = next((r for r in records if extract_notify_no(r) == code), None)
        if notice is None:
            return {"tender_status": "", "location": "", "bid_form": "",
                    "lookup_error": "Không tìm thấy TBMT"}
        row = plan_row_from_search(notice)
        if not row.location and row.plan_no:
            try:
                row.location = client.get_plan_location(row.plan_no)
            except Exception:
                logging.exception("Location lookup failed code=%s", code)
        return extraction_fields(row)
    except Exception:
        logging.exception("Extracted notice lookup failed code=%s", code)
        return {"tender_status": "", "location": "", "bid_form": "",
                "lookup_error": "Tra cứu lỗi, hãy thử lại"}
    finally:
        client.s.close()


def lookup_plan_fields(code: str) -> dict:
    """Resolve a pasted PL code as a plan, never as a tender notice."""
    client = MuaSamCongClient()
    try:
        plans = client.search_plans(code, max_pages=1)
        plan = next((item for item in plans
                     if display_plan_no(item.get("planNo") or item.get("planNoStand")) == code), None)
        if plan is None:
            return {"lookup_error": "Không tìm thấy KHLCNT"}
        row = plan_row_from_search(plan)
        return {"title": row.plan_name or row.package_name,
                "investor_name": row.investor_name, "location": row.location,
                "bid_form": row.bid_form, "tender_status": "", "lookup_error": ""}
    except Exception:
        logging.exception("Extracted plan lookup failed code=%s", code)
        return {"lookup_error": "Tra cứu KHLCNT lỗi, hãy thử lại"}
    finally:
        client.s.close()


def enrich_extraction(extraction_id: str) -> None:
    with EXTRACTIONS_LOCK:
        task = EXTRACTIONS[extraction_id]
    codes = list(dict.fromkeys(record["code"] for record in task["rows"]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(lookup_plan_fields if code.startswith("PL") else lookup_notice_fields,
                               code): code for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            fields = future.result()
            with EXTRACTIONS_LOCK:
                for record in task["rows"]:
                    if record["code"] == code:
                        record.update(fields)
                        task["processed"] += 1
    with EXTRACTIONS_LOCK:
        task["state"] = "done"


def start_extraction(records: list[dict], *, lookup: bool = True, owner: str = "") -> dict:
    extraction_id = uuid.uuid4().hex
    task = {"id": extraction_id, "owner": owner, "state": "running" if lookup and records else "done",
            "count": len(records), "processed": 0 if lookup else len(records),
            "rows": [dict(record) for record in records]}
    with EXTRACTIONS_LOCK:
        EXTRACTIONS[extraction_id] = task
        # Keep active tasks until their lookups finish.
        for old_id in list(EXTRACTIONS):
            if len(EXTRACTIONS) <= 20:
                break
            if old_id != extraction_id and EXTRACTIONS[old_id]["state"] == "done":
                del EXTRACTIONS[old_id]
        snapshot = {**task, "rows": [dict(row) for row in task["rows"]]}
    if task["state"] == "running":
        threading.Thread(target=enrich_extraction, args=(extraction_id,), daemon=True).start()
    return snapshot


def build_extraction_workbook(records: list[dict]) -> bytes:
    if Workbook is None:
        raise RuntimeError("Chưa cài openpyxl để xuất Excel")
    from openpyxl.styles import Alignment, Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    has_plans = any(str(record.get("code", "")).startswith("PL") for record in records)
    sheet.title = "Mã TBMT và KHLCNT" if has_plans else "Mã TBMT"
    headers = (["STT", "Loại mã", "Mã", "Tên gói hoặc kế hoạch", "Chủ đầu tư",
                "Trạng thái TBMT", "Địa điểm", "Hình thức lựa chọn nhà thầu"]
               if has_plans else
               ["STT", "Mã TBMT", "Trạng thái", "Địa điểm", "Hình thức lựa chọn nhà thầu"])
    sheet.append(headers)
    for index, record in enumerate(records, 1):
        common = [record.get("tender_status") or record.get("lookup_error", ""),
                  record.get("location", ""), record.get("bid_form", "")]
        sheet.append(([index, record.get("code_type") or
                       ("KHLCNT" if str(record.get("code", "")).startswith("PL") else "TBMT"),
                       record.get("code", ""), record.get("title", ""),
                       record.get("investor_name", ""), *common] if has_plans else
                      [index, record.get("code", ""), *common]))
    fill = PatternFill("solid", fgColor="102A43")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in sheet.iter_rows(min_row=2):
        row[2 if has_plans else 1].number_format = "@"
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    widths = ({"A": 8, "B": 14, "C": 22, "D": 56, "E": 38, "F": 30,
               "G": 32, "H": 36} if has_plans else
              {"A": 8, "B": 22, "C": 32, "D": 32, "E": 36})
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def row_to_public_dict(row: ResultRow, index: int) -> dict:
    data = asdict(row)
    data.pop("lot_data", None)
    data["index"] = index
    data["has_lots"] = bool(row.lot_data and row.lot_file_status == "done")
    return data


def _run_search(job: SearchJob) -> None:
    params = job.params
    mode = str(params.get("mode") or "Thông báo mời thầu")
    keyword = str(params.get("keyword") or "").strip()
    use_dates = bool(params.get("use_dates", True))
    date_from = str(params.get("date_from") or "")
    date_to = str(params.get("date_to") or "")
    if not keyword and mode != "Thông báo mời thầu":
        job.update("error", "Hãy nhập từ khóa hoặc mã KHLCNT.")
        return
    if not keyword and mode == "Thông báo mời thầu" and not use_dates:
        job.update("error", "Quét TBMT không có từ khóa cần một khoảng ngày.")
        return

    runner = SimpleNamespace(
        client=MuaSamCongClient(),
        keyword_var=Value(keyword),
        search_mode_var=Value(mode),
        pages_var=Value(max(1, min(50, int(params.get("pages") or 5)))),
        use_date_filter_var=Value(use_dates),
        date_from_var=Value(date_from),
        date_to_var=Value(date_to),
        detail_var=Value(bool(params.get("detail", False))),
        fast_mode_var=Value(bool(params.get("fast_mode", True))),
        remove_dup_var=Value(bool(params.get("remove_duplicates", True))),
        notice_status_var=Value(str(params.get("status") or "Tất cả trạng thái")),
        msg_queue=JobQueue(job),
    )
    job.update("status", "Đang kết nối dữ liệu e-GP…")
    # Phương thức này chỉ phụ thuộc các thuộc tính ở trên; gọi không cần tạo cửa sổ Tk.
    App._search_worker(runner)
    if job.state == "done":
        try:
            from server.intelligence import ingest_rows
            ingest_rows(job.rows)
        except Exception:
            logging.exception("Could not update tender intelligence cache")


def start_search(params: dict, owner: str = "") -> SearchJob:
    params = dict(params)
    force_refresh = params.pop("force_refresh", False) is True
    cached = None if force_refresh else JOBS.find_cached(params, owner=owner)
    job = JOBS.create(params, owner)
    if cached is not None:
        # Reuse only this account's result: later actions may enrich in-memory rows.
        job.update("done", copy.deepcopy(cached.rows))
        job.source_count = cached.source_count
        with job.lock:
            job.message = f"Đã dùng bộ nhớ đệm - {len(job.rows)} kết quả"
        return job
    threading.Thread(target=_run_search, args=(job,), daemon=True).start()
    return job


def selected_rows(job: SearchJob, indices) -> list[ResultRow]:
    if indices is None or indices == "all":
        return list(job.rows)
    clean = []
    seen = set()
    for value in indices:
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if index in seen or not 0 <= index < len(job.rows):
            continue
        seen.add(index)
        clean.append(job.rows[index])
    return clean


def build_result_workbook(rows: list[ResultRow], notice_mode: bool) -> bytes:
    if Workbook is None:
        raise RuntimeError("Chưa cài openpyxl để xuất Excel")
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.worksheets[0]
    ws.title = "Kết quả"
    if notice_mode:
        headers = [
            "STT", "Mã TBMT", "Mã KHLCNT", "Tên gói thầu", "Hình thức LCNT",
            "Tỉnh / Thành phố", "Ngày đăng tải", "Thời điểm đóng thầu", "Trạng thái",
            "Chủ đầu tư", "Tên KHLCNT / Dự án", "Nhà thầu trúng", "Ngày phê duyệt",
        ]
        widths = [7, 19, 16, 48, 24, 24, 16, 21, 22, 42, 42, 38, 16]
    else:
        headers = [
            "STT", "Mã KHLCNT", "Tên KHLCNT / Dự án", "Tên gói thầu", "Ngày đăng tải",
            "Ngày phê duyệt", "Nhà thầu trúng", "Hình thức LCNT", "Chủ đầu tư",
            "Danh sách phân lô",
        ]
        widths = [7, 16, 38, 42, 16, 16, 40, 24, 40, 24]
    ws.append(headers)
    for number, row in enumerate(rows, 1):
        if notice_mode:
            values = [
                number, row.notify_no, display_plan_no(row.plan_no or row.plan_reference), row.package_name, row.bid_form,
                row.location, row.public_date, row.bid_close_date, row.tender_status,
                row.investor_name, row.plan_name, row.winner, row.decision_date,
            ]
        else:
            values = [
                number, display_plan_no(row.plan_no or row.plan_reference), row.plan_name, row.package_name, row.public_date,
                row.decision_date, row.winner, row.bid_form, row.investor_name,
                row.lot_file_status,
            ]
        ws.append(values)

    header_fill = PatternFill("solid", fgColor="102A43")
    alternate_fill = PatternFill("solid", fgColor="F2F7F7")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32
    code_columns = (2, 3) if notice_mode else (2,)
    for row_number in range(2, ws.max_row + 1):
        for column in code_columns:
            ws.cell(row=row_number, column=column).number_format = "@"
        for cell in ws[row_number]:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if row_number % 2 == 0:
                cell.fill = alternate_fill
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


class NoLotFileError(ValueError):
    """The selected package has no public lot list to export."""


def load_lots_for_download(row: ResultRow) -> ResultRow:
    """Resolve exactly the displayed package; never expand a selected plan."""
    if row.lot_file_status in {"Ko co file", "Không có file"}:
        raise NoLotFileError("Không có file phân lô (đã kiểm tra trong lần tra cứu này)")
    row = replace(row, lot_data=[])
    client = MuaSamCongClient()
    try:
        if row.notify_no:
            notices = client.search_notices(row.notify_no, max_pages=1)
            notice = next((item for item in notices if extract_notify_no(item) == row.notify_no), None)
            if notice is None:
                raise ValueError("Không tìm thấy TBMT")
            package_id = text_value(notice.get("bidId"))
            if not package_id:
                raise ValueError("TBMT thiếu mã liên kết gói thầu")
            row = plan_row_from_search(notice)
            row.package_id = package_id
        elif not row.package_id:
            plans = client.search_plans("PL" + row.plan_no, max_pages=1)
            plan = next((p for p in plans if clean_plan_no(p.get("planNo")) == row.plan_no), None)
            if plan is None:
                raise ValueError("Không tìm thấy KHLCNT")
            plan_detail = client.get_plan_detail(plan["id"])
            packages = plan_detail.get("bidpPlanDetailToProjectList") or []
            normalize = lambda value: " ".join(str(value or "").split()).casefold()
            if row.package_no:
                matches = [p for p in packages if text_value(p.get("bidNo")) == row.package_no]
            elif row.package_name:
                matches = [p for p in packages if normalize(p.get("bidName") or p.get("packageName") or p.get("name")) == normalize(row.package_name)]
            else:
                matches = []
            if len(matches) != 1:
                raise ValueError("Chưa xác định duy nhất gói đang hiển thị. Hãy tắt quét nhanh và tìm lại mã KHLCNT này.")
            package = matches[0]
            if str(package.get("isMultiLot")).lower() in {"0", "false"}:
                raise NoLotFileError("Không có file phân lô: gói không chia lô")
            row.package_id = text_value(package.get("idDetail") or package.get("id"))
            row.package_no = text_value(package.get("bidNo"))
        if not row.package_id:
            raise ValueError("Gói đang hiển thị thiếu mã chi tiết. Hãy tìm kiếm lại.")
        detail = client.get_package_detail(row.package_id)
        if str(detail.get("isMultiLot")).lower() in {"0", "false"}:
            raise NoLotFileError("Không có file phân lô: gói không chia lô")
        detail_no = text_value(detail.get("bidNo"))
        if row.package_no and detail_no and row.package_no != detail_no:
            raise ValueError("Mã gói trong chi tiết không khớp dòng đã chọn. Hãy tìm kiếm lại.")
        row.package_no = detail_no or row.package_no
        row.package_name = text_value(detail.get("bidName")) or row.package_name
        row.package_scoped = True
        context = {key: detail.get(key) for key in EXPORT_CONTEXT_KEYS}
        row.lot_data = [{**lot, "bidNo": row.package_no, "bidName": row.package_name,
                         "_export_context": context}
                        for lot in (detail.get("bidpBidLotList") or [])
                        if isinstance(lot, dict) and any(v not in (None, "", [], {}) for v in lot.values())]
        if not row.lot_data:
            raise NoLotFileError("Không có danh sách phân lô")
        row.lot_file_status = "done"
        return row
    finally:
        client.s.close()


def prepare_lot_download(rows: list[ResultRow], allow_empty=False) -> tuple[list[ResultRow], list[dict]]:
    unique = {}
    for row in rows:
        key = row.notify_no or (row.plan_no, row.package_no, row.package_id, row.package_name)
        unique.setdefault(key, row)
    if not unique:
        raise ValueError("Hãy tick ít nhất một mã để tải phân lô.")
    ready, issues = {}, {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(load_lots_for_download, row): key for key, row in unique.items()}
        for future in as_completed(futures):
            key = futures[future]
            row = unique[key]
            try:
                ready[key] = future.result()
                row.lot_file_status = "done"
                row.lot_data = ready[key].lot_data
            except Exception as exc:
                row.lot_data = []
                row.lot_file_status = "Ko co file" if isinstance(exc, NoLotFileError) else "Chưa kiểm tra được"
                logging.exception("Download lots failed code=%s", row.notify_no or row.plan_no)
                issues[key] = {"code": row.notify_no or "PL" + row.plan_no, "reason": str(exc)}
    for row in rows:
        key = row.notify_no or (row.plan_no, row.package_no, row.package_id, row.package_name)
        row.lot_file_status = unique[key].lot_file_status
        row.lot_data = unique[key].lot_data
    if not ready and not allow_empty:
        raise ValueError("Không tải được phân lô: " + "; ".join(
            item["code"] + ": " + item["reason"] for item in issues.values()))
    return [ready[key] for key in unique if key in ready], [issues[key] for key in unique if key in issues]


class LotFileStore:
    """Keep recent individual downloads on disk while the local server runs."""

    def __init__(self):
        self.lock = threading.Lock()
        self.batches = []

    def _prune(self):
        now = time.time()
        while self.batches and (len(self.batches) > 10 or now - self.batches[0][0] > 7200):
            self.batches.pop(0)[1].cleanup()

    def add(self, files, issues):
        with self.lock:
            folder = tempfile.TemporaryDirectory(prefix="muasamcong_files_")
            entries, manifest = {}, []
            try:
                for file in files:
                    token = uuid.uuid4().hex
                    path = Path(folder.name) / (token + ".xlsx")
                    path.write_bytes(file["data"])
                    entries[token] = (path, file["name"])
                    manifest.append({"name": file["name"], "code": file["code"],
                                     "analysis": file.get("analysis"),
                                     "url": "/api/lot-file?id=" + token})
                self.batches.append((time.time(), folder, entries))
                self._prune()
                return {"files": manifest, "issues": issues}
            except Exception:
                folder.cleanup()
                raise

    def read(self, token):
        with self.lock:
            self._prune()
            for _, _, entries in self.batches:
                if token in entries:
                    path, name = entries[token]
                    return path.read_bytes(), name
        return None

    def close(self):
        with self.lock:
            for _, folder, _ in self.batches:
                folder.cleanup()
            self.batches.clear()


LOT_FILES = LotFileStore()


class DownloadArchive:
    """Keep exported workbooks available after the in-memory job expires."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.lock = threading.RLock()

    def read(self) -> list[dict]:
        with self.lock:
            index = self.folder / "index.json"
            if not index.exists():
                return []
            try:
                data = json.loads(index.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    raise ValueError()
                return [item for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]
            except (ValueError, OSError) as exc:
                raise ValueError("Không đọc được lịch sử tải xuống.") from exc

    def _write(self, items: list[dict]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.folder,
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(items[:200], stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self.folder / "index.json")
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def add(self, data: bytes, name: str, kind: str) -> dict:
        with self.lock:
            token = uuid.uuid4().hex
            self.folder.mkdir(parents=True, exist_ok=True)
            (self.folder / f"{token}.xlsx").write_bytes(data)
            item = {"id": token, "name": Path(name).name[:200], "kind": kind[:50],
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "status": "Hoàn thành", "size": len(data),
                    "url": f"/api/download-file?id={token}"}
            self._write([item] + self.read())
            return item

    def record_error(self, name: str, kind: str, message: str) -> dict:
        with self.lock:
            token = uuid.uuid4().hex
            item = {"id": token, "name": Path(name).name[:200], "kind": kind[:50],
                    "time": datetime.now().isoformat(timespec="seconds"), "status": "Lỗi",
                    "size": 0, "error": message[:300], "url": ""}
            self._write([item] + self.read())
            return item

    def file(self, token: str) -> tuple[bytes, str] | None:
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            return None
        with self.lock:
            item = next((entry for entry in self.read() if entry["id"] == token and
                         entry.get("status") == "Hoàn thành"), None)
            path = self.folder / f"{token}.xlsx"
            if item and path.is_file():
                return path.read_bytes(), item["name"]
            return None


DOWNLOADS = DownloadArchive((Path(sys.executable).parent if getattr(sys, "frozen", False)
                             else Path(__file__).resolve().parent) / "download_center")

LOCAL_STORES = SimpleNamespace(presets=PRESETS, watchlist=WATCHLIST, history=HISTORY,
                               downloads=DOWNLOADS, lot_files=LOT_FILES)
_SESSION_STORES: dict[str, SimpleNamespace] = {}
_SESSION_STORES_LOCK = threading.Lock()


def session_stores(session_id: str) -> SimpleNamespace:
    """Cloud Run sessions are isolated within an instance; local EXE keeps its legacy files."""
    with _SESSION_STORES_LOCK:
        stores = _SESSION_STORES.get(session_id)
        if stores is None:
            folder = Path(tempfile.gettempdir()) / "muasamcong_sessions" / session_id
            stores = SimpleNamespace(presets=PresetStore(folder / "saved_queries.json"),
                                     watchlist=WatchlistStore(folder / "watchlist.json"),
                                     history=QueryHistoryStore(folder / "query_history.json"),
                                     downloads=DownloadArchive(folder / "download_center"),
                                     lot_files=LotFileStore())
            _SESSION_STORES[session_id] = stores
        return stores


def archive_download(data: bytes, name: str, kind: str,
                     archive: DownloadArchive | None = None) -> dict | None:
    try:
        return (archive or DOWNLOADS).add(data, name, kind)
    except Exception:
        logging.exception("Could not archive download %s", name)
        return None


def build_lot_download(rows: list[ResultRow], issues: list[dict]) -> tuple[list[dict], list[dict]]:
    """Produce exactly one unchanged Excel template per package, never a bundle."""
    files, seen, problems = [], set(), list(issues)
    with tempfile.TemporaryDirectory(prefix="muasamcong_") as temp:
        for row in rows:
            if row.lot_file_status != "done" or not row.lot_data:
                continue
            packages = {}
            for lot in row.lot_data:
                packages.setdefault(str(lot.get("bidNo") or "").strip(), []).append(lot)
            if len(packages) != 1 or (row.package_no and row.package_no not in packages):
                problems.append({"code": row.package_no or row.plan_no,
                                 "reason": "Dữ liệu chưa giới hạn đúng một gói đang hiển thị. Hãy tìm lại mã."})
                continue
            for bid_no, lots in packages.items():
                key = (clean_plan_no(row.plan_no), bid_no)
                if key in seen:
                    continue
                try:
                    path = save_lot_list(ResultRow(**{**asdict(row), "lot_data": lots}), Path(temp))
                    from lot_analysis import analyze_lots
                    files.append({"name": path.name, "code": bid_no, "data": path.read_bytes(),
                                  "analysis": analyze_lots(lots, row.package_name, row.plan_no)})
                    seen.add(key)
                except Exception as exc:
                    logging.exception("Excel export failed package=%s", bid_no)
                    problems.append({"code": bid_no or row.notify_no or row.plan_no,
                                     "reason": str(exc)})
    if not files:
        raise ValueError("Không tạo được file phân lô. " + "; ".join(
            item["code"] + ": " + item["reason"] for item in problems))
    return files, problems


class WebHandler(BaseHTTPRequestHandler):
    server_version = "MuaSamCongWeb/1.0"

    def _auth_token(self) -> str:
        if not hasattr(self, "_cached_auth_token"):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                self._cached_auth_token = cookie["msc_auth"].value if "msc_auth" in cookie else ""
            except Exception:
                self._cached_auth_token = ""
        return self._cached_auth_token

    def _current_user(self) -> dict | None:
        if not hasattr(self, "_cached_user"):
            self._cached_user = session_user(self._auth_token()) if self._auth_token() else None
        return self._cached_user

    def _owner_id(self) -> str:
        user = self._current_user()
        return user["id"] if user else self._session_id()

    def _require_user(self) -> dict | None:
        user = self._current_user()
        if not user:
            self._json({"error": "Vui lòng đăng nhập để tiếp tục."}, HTTPStatus.UNAUTHORIZED)
        return user

    def _check_rate_limit(self) -> bool:
        route = self.path.split("?", 1)[0]
        if route == "/api/auth/login":
            return True  # Account-scoped limit is applied after parsing the login body.
        if route == "/api/auth/register":
            client = self.client_address[0]
            amount, window = 20, 3600
            key = route + ":" + client
        elif route == "/api/ai/analyze":
            amount, window = ai_settings()["requests_per_minute"], 60
            key = route + ":" + self._owner_id()
        elif route.startswith("/api/intelligence/tenders/") and route.endswith("/refresh"):
            amount, window = 6, 60
            key = "refresh-tender:" + self._owner_id()
        elif route in {"/api/reports/preview", "/api/reports/export"} or route.endswith("/run") and route.startswith(("/api/reports/", "/api/dashboards/")):
            amount, window = 20, 60
            key = "report-query:" + self._owner_id()
        elif route == "/api/automations/preview" or route.startswith("/api/automations/") and route.endswith(("/run", "/test")):
            amount, window = 6, 60
            key = "automation-run:" + self._owner_id()
        elif route.startswith("/api/data-sync"):
            amount, window = 10, 60
            key = "data-sync-admin:" + self._owner_id()
        elif route.startswith("/api/document-center/egp/") and route.endswith(("/fetch", "/extract", "/ai-import")):
            amount, window = 8, 60
            key = "document-source:" + self._owner_id()
        elif route in {"/api/intelligence/search", "/api/intelligence/suggest"}:
            amount, window = (60 if route.endswith("/search") else 180), 60
            key = route + ":" + self._owner_id()
        elif route in {"/api/search", "/api/export", "/api/export-codes", "/api/lots",
                        "/api/documents/upload",
                       "/api/refresh-watch", "/api/extract"}:
            amount, window = (30, 60) if route == "/api/search" else (20, 60)
            key = route + ":" + self._owner_id()
        else:
            return True
        try:
            amount = max(1, int(os.environ.get("RATE_LIMIT_PER_WINDOW", amount)))
        except ValueError:
            pass
        if RATE_LIMITER.allow(key, amount, window):
            return True
        self._json({"error": "Thao tác quá nhanh. Vui lòng thử lại sau."},
                   HTTPStatus.TOO_MANY_REQUESTS, {"Retry-After": str(window)})
        return False

    def _session_id(self) -> str:
        if os.environ.get("PORT") in {None, "", "0"}:
            return ""
        if not hasattr(self, "_browser_session_id"):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                value = cookie["msc_session"].value if "msc_session" in cookie else ""
            except Exception:
                value = ""
            self._browser_session_id = value if re.fullmatch(r"[0-9a-f]{32}", value) else uuid.uuid4().hex
            self._new_browser_session = not bool(re.fullmatch(r"[0-9a-f]{32}", value))
        return self._browser_session_id

    def _stores(self) -> SimpleNamespace:
        user = self._current_user()
        if user:
            from server.database_adapters import user_stores
            return user_stores(user["id"])
        session_id = self._session_id()
        return session_stores(session_id) if session_id else LOCAL_STORES

    def _owns(self, item) -> bool:
        return bool(item) and getattr(item, "owner", "") == self._owner_id()

    def log_message(self, format, *args):
        return  # _send logs one sanitized event; BaseHTTPRequestHandler includes raw query text.

    def _send(self, body: bytes, content_type: str, status=HTTPStatus.OK, headers=None):
        if (len(body) >= 1024 and status == HTTPStatus.OK and
                "gzip" in self.headers.get("Accept-Encoding", "").lower() and
                content_type.startswith(("application/json", "application/javascript", "text/", "text/css"))):
            import gzip
            body = gzip.compress(body, compresslevel=5)
            headers = {**(headers or {}), "Content-Encoding": "gzip", "Vary": "Accept-Encoding"}
        from server.performance import finish_request, slow_request_ms
        elapsed_ms = (time.monotonic() - getattr(self, "_request_started", time.monotonic())) * 1000
        sample = finish_request(self.command, self.path, int(status), elapsed_ms)
        request_id = getattr(self, "_request_id", None) or uuid.uuid4().hex
        self._request_id = request_id
        self._response_started = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", request_id)
        if "Cache-Control" not in (headers or {}):
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        session_id = self._session_id()
        if session_id and self._new_browser_session:
            self.send_header("Set-Cookie", f"msc_session={session_id}; Path=/; HttpOnly; Secure; SameSite=Lax")
        if self.path.startswith(("/api/", "/internal/", "/app", "/legacy", "/admin", "/login", "/register", "/health", "/ready", "/version")):
            self.send_header("X-Robots-Tag", "noindex, nofollow")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
        if elapsed_ms >= slow_request_ms():
            logging.warning("Slow request: %s SQL queries, %.1f ms SQL time",
                sample["db_query_count"], sample["db_duration_ms"],
                extra={"event": "slow_request", "request_id": request_id,
                    "route": sample["route"], "method": self.command,
                    "status": int(status), "duration_ms": round(elapsed_ms, 2)})
        logging.info("HTTP response", extra={"event": "http_response", "request_id": request_id,
            "method": self.command, "route": sample["route"], "status": int(status),
            "duration_ms": round(elapsed_ms, 2)})

    def _json(self, data, status=HTTPStatus.OK, headers=None):
        self._send(
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
            headers,
        )

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            maximum = max(25_000_000, max_upload_bytes() * 4 // 3 + 1_000_000) if self.path == "/api/documents/upload" else 25_000_000
            if length < 0 or length > maximum:
                raise ValueError("Kích thước dữ liệu gửi lên không hợp lệ.")
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if not isinstance(data, dict):
                raise ValueError("Dữ liệu gửi lên phải là một đối tượng JSON.")
            return data
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Dữ liệu gửi lên không hợp lệ") from exc

    def _job_from_body(self, body: dict) -> SearchJob:
        job = JOBS.get(str(body.get("job_id") or ""))
        if not self._owns(job) or job.state != "done":
            raise ValueError("Không tìm thấy kết quả để tải. Hãy tìm kiếm lại.")
        return job

    def do_GET(self):
        try:
            self._do_GET()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            request_id = getattr(self, "_request_id", uuid.uuid4().hex)
            logging.exception("Web request failed", extra={"event": "request_error",
                "request_id": request_id, "route": urlparse(self.path).path,
                "method": self.command})
            if not getattr(self, "_response_started", False):
                self._request_id = request_id
                self._json({"error": "internal_error", "message": "Máy chủ gặp lỗi. Vui lòng thử lại sau.",
                            "error_id": "ERR-" + request_id[:12]}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _do_GET(self):
        self._request_started = time.monotonic()
        self._request_id = uuid.uuid4().hex
        from server.performance import begin_request
        begin_request()
        parsed = urlparse(self.path)
        if parsed.path == "/ready":
            try:
                ready = get_db().health()
                self._json({"status": "ready"} if ready else {"status": "unavailable"},
                    HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE)
            except Exception:
                self._json({"status": "unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path == "/version":
            self._json({"app_version": APP_VERSION,
                        "build_sha": os.environ.get("GIT_SHA", "")[:40],
                        "environment": "production" if production() else "development"})
            return
        if parsed.path == "/api/auth/me":
            user = self._current_user()
            self._json({"user": user} if user else {"error": "Chưa đăng nhập."},
                       HTTPStatus.OK if user else HTTPStatus.UNAUTHORIZED)
            return
        if parsed.path.startswith("/api/") and parsed.path != "/api/health" and not self._require_user():
            return
        if parsed.path in {"/api/intelligence/search", "/api/intelligence/suggest"} and not self._check_rate_limit():
            return
        if parsed.path.startswith(("/api/documents", "/api/document-center", "/api/ai/", "/api/admin/ai-stats")):
            try:
                from server.document_http import handle_get
                if handle_get(self, parsed):
                    return
            except Exception:
                logging.exception("Private document request failed")
                self._json({"error": "Không lấy được dữ liệu tài liệu."}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
        if parsed.path.startswith("/api/admin/data-quality"):
            from server.data_quality.http import handle_get
            if handle_get(self, parsed):
                return
        if parsed.path == "/api/admin/performance":
            if not self._current_user() or self._current_user()["role"] != "admin":
                self._json({"error": "Không có quyền quản trị."}, HTTPStatus.FORBIDDEN)
            else:
                from server.performance import snapshot
                try:
                    self._json(snapshot())
                except Exception:
                    logging.exception("Performance metrics unavailable")
                    self._json({"error": "Không lấy được số liệu hiệu năng."},
                               HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path == "/api/admin/production-status":
            if not self._current_user() or self._current_user()["role"] != "admin":
                self._json({"error": "Không có quyền quản trị."}, HTTPStatus.FORBIDDEN)
            else:
                from server.production_status import snapshot
                self._json(snapshot())
            return
        if parsed.path.startswith("/api/data-quality/"):
            from server.data_quality.service import entity_status
            match = re.fullmatch(r"/api/data-quality/(tenders|documents)/([A-Za-z0-9._-]{1,100})", parsed.path)
            if not match:
                self._json({"error": "Đường dẫn không hợp lệ."}, HTTPStatus.NOT_FOUND)
                return
            try:
                self._json(entity_status("tender" if match.group(1) == "tenders" else "document",
                                         match.group(2)))
            except LookupError as exc:
                self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        if parsed.path.startswith("/api/intelligence/"):
            try:
                from server.intelligence_http import handle_get
                if handle_get(self, parsed):
                    return
            except Exception:
                logging.exception("Tender intelligence request failed")
                self._json({"error": "Không lấy được dữ liệu đấu thầu."},
                           HTTPStatus.INTERNAL_SERVER_ERROR)
                return
        if parsed.path.startswith(("/api/analytics/", "/api/reports", "/api/dashboards")):
            try:
                from server.reporting_http import handle_get
                if handle_get(self, parsed):
                    return
            except Exception:
                logging.exception("Reporting request failed")
                self._json({"error": "Không lấy được dữ liệu báo cáo."},
                           HTTPStatus.INTERNAL_SERVER_ERROR)
                return
        if parsed.path.startswith("/api/automations"):
            try:
                from server.automation_http import handle_get
                if handle_get(self, parsed):
                    return
            except Exception:
                logging.exception("Automation request failed")
                self._json({"error": "Không lấy được dữ liệu tự động hóa."},
                           HTTPStatus.INTERNAL_SERVER_ERROR)
                return
        if parsed.path.startswith("/api/data-sync"):
            from server.data_sync_http import handle_get
            if handle_get(self, parsed.path):
                return
        if (parsed.path == "/admin" or parsed.path.startswith("/admin/")) and (not self._current_user() or self._current_user()["role"] != "admin"):
            self._json({"error": "Không có quyền truy cập."}, HTTPStatus.FORBIDDEN)
            return
        if (parsed.path == "/app" or parsed.path.startswith("/app/") or parsed.path == "/legacy") and not self._current_user():
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/login")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if parsed.path in {"/index.html", "/loc-du-lieu-mua-sam-cong.html", "/loc-du-lieu-mua-sam-cong/"}:
            destination = "/" if parsed.path == "/index.html" else "/loc-du-lieu-mua-sam-cong"
            self.send_response(HTTPStatus.PERMANENT_REDIRECT)
            self.send_header("Location", destination)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if parsed.path == "/health":
            self._json({"status": "ok", "ok": True})
            return
        if parsed.path == "/robots.txt":
            self._send(robots_txt(self.headers.get("Host", "")), "text/plain; charset=utf-8")
            return
        if parsed.path == "/sitemap.xml":
            try:
                self._send(sitemap_xml(self.headers.get("Host", "")), "application/xml; charset=utf-8")
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path == "/api/lot-file":
            token = (parse_qs(parsed.query).get("id") or [""])[0]
            file = self._stores().lot_files.read(token)
            if file is None:
                self._json({"error": "File đã hết hạn. Hãy chọn lại mã và tải phân lô."}, HTTPStatus.NOT_FOUND)
                return
            data, filename = file
            self._send(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                "X-Filename": filename})
            return
        if parsed.path == "/api/download-file":
            token = (parse_qs(parsed.query).get("id") or [""])[0]
            file = self._stores().downloads.file(token)
            if file is None:
                self._json({"error": "File không còn trong Download Center."}, HTTPStatus.NOT_FOUND)
                return
            data, filename = file
            mime = "text/csv; charset=utf-8" if filename.lower().endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            self._send(data, mime,
                       headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                "X-Filename": filename})
            return
        if parsed.path == "/api/downloads":
            try:
                self._json({"items": self._stores().downloads.read()})
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/presets":
            try:
                self._json({"presets": self._stores().presets.read()})
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/watchlist":
            try:
                self._json({"items": self._stores().watchlist.read()})
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/history":
            try:
                self._json({"items": self._stores().history.read()})
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/health":
            self._json({"ok": True, "time": datetime.now().isoformat(timespec="seconds")})
            return
        if parsed.path == "/api/profile":
            self._json({"user": self._current_user()})
            return
        if parsed.path == "/api/notifications":
            user_id = self._current_user()["id"]
            with get_db().engine.connect() as conn:
                rows = conn.execute(select(user_notifications)
                    .where(user_notifications.c.user_id == user_id)
                    .order_by(user_notifications.c.created_at.desc()).limit(100)).mappings().all()
            self._json({"items": [dict(row) for row in rows]})
            return
        if parsed.path == "/api/admin/users":
            from server.admin_users import list_accounts
            params = parse_qs(parsed.query)
            try:
                self._json(list_accounts(self._current_user()["id"],
                    params.get("q", [""])[0], params.get("status", [""])[0],
                    params.get("role", [""])[0], params.get("page", ["1"])[0]))
            except PermissionError as exc:
                self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/admin/stats":
            if self._current_user()["role"] != "admin":
                self._json({"error": "Không có quyền quản trị."}, HTTPStatus.FORBIDDEN)
                return
            today = datetime.now().date().isoformat()
            with get_db().engine.connect() as conn:
                count = lambda table, *filters: conn.scalar(select(func.count()).select_from(table).where(*filters))
                data = {"total_users": count(users), "active_users": count(users, users.c.is_active.is_(True)),
                        "searches_today": count(search_history, search_history.c.created_at >= today),
                        "saved_searches": count(saved_searches), "followed_tenders": count(followed_tenders),
                        "notifications_generated": count(user_notifications), "downloads": count(download_history),
                        "saved_reports": count(saved_reports), "report_runs": count(report_runs),
                        "custom_dashboards": count(user_dashboards),
                        "automation_active_rules": count(automation_rules,
                            automation_rules.c.is_enabled.is_(True),
                            automation_rules.c.deleted_at.is_(None)),
                        "automation_runs_today": count(automation_runs,
                            automation_runs.c.started_at >= today),
                        "automation_matches_today": conn.scalar(select(func.coalesce(
                            func.sum(automation_runs.c.matched_count), 0)).where(
                            automation_runs.c.started_at >= today)),
                        "automation_failures_today": count(automation_runs,
                            automation_runs.c.started_at >= today,
                            automation_runs.c.error_message.is_not(None)),
                        "automation_average_duration_ms": float(conn.scalar(select(func.coalesce(
                            func.avg(automation_runs.c.duration_ms), 0)).where(
                            automation_runs.c.started_at >= today)) or 0),
                        "automation_top_triggers": [{"trigger": row.trigger_type,
                            "count": row.count} for row in conn.execute(select(
                                automation_rules.c.trigger_type,
                                func.count().label("count"))
                            .where(automation_rules.c.deleted_at.is_(None))
                            .group_by(automation_rules.c.trigger_type)
                            .order_by(func.count().desc()).limit(5))],
                        "recent_jobs": [dict(row) for row in conn.execute(select(job_runs)
                            .order_by(job_runs.c.created_at.desc()).limit(10)).mappings()]}
            self._json(data)
            return
        if parsed.path == "/api/extraction":
            extraction_id = (parse_qs(parsed.query).get("id") or [""])[0]
            with EXTRACTIONS_LOCK:
                task = EXTRACTIONS.get(extraction_id)
                snapshot = {**task, "rows": [dict(row) for row in task["rows"]]} if task and task.get("owner", "") == self._owner_id() else None
            self._json(snapshot or {"error": "Không tìm thấy danh sách mã"},
                       HTTPStatus.OK if snapshot else HTTPStatus.NOT_FOUND)
            return
        if parsed.path == "/api/job":
            job_id = (parse_qs(parsed.query).get("id") or [""])[0]
            job = JOBS.get(job_id)
            if not self._owns(job):
                self._json({"error": "Không tìm thấy truy vấn"}, HTTPStatus.NOT_FOUND)
                return
            self._json(job.public_data(include_rows=True))
            return
        react_enabled = os.environ.get("REACT_FRONTEND_ENABLED") == "1" and (REACT_DIR / "index.html").is_file()
        if react_enabled and parsed.path.startswith("/assets/"):
            asset = parsed.path.removeprefix("/")
            if not re.fullmatch(r"assets/[A-Za-z0-9_.-]+\.(?:js|css|svg|png|woff2?)", asset):
                self._json({"error": "Không tìm thấy tài nguyên"}, HTTPStatus.NOT_FOUND)
                return
            path = REACT_DIR / asset
            if not path.is_file():
                self._json({"error": "Không tìm thấy tài nguyên"}, HTTPStatus.NOT_FOUND)
                return
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if mime.startswith("text/") or mime == "application/javascript":
                mime += "; charset=utf-8"
            self._send(path.read_bytes(), mime, headers={"Cache-Control": "public, max-age=31536000, immutable"})
            return
        if react_enabled and (parsed.path == "/app" or parsed.path.startswith("/app/") or
                              parsed.path in {"/login", "/register", "/admin"} or parsed.path.startswith("/admin/")):
            self._send((REACT_DIR / "index.html").read_bytes(), "text/html; charset=utf-8",
                       headers={"Cache-Control": "no-cache"})
            return
        seo_page = parsed.path.rstrip("/") or "/"
        if seo_page == "/loc-du-lieu-mua-sam-cong":
            relative = "loc-du-lieu-mua-sam-cong.html"
        elif seo_page == "/":
            relative = "public-home.html"
        elif seo_page == "/app" or seo_page.startswith("/app/") or seo_page == "/legacy":
            relative = "index.html"
        elif seo_page in {"/login", "/register"}:
            relative = "auth.html"
        elif seo_page in {"/admin", "/admin/data-quality", "/admin/performance"}:
            relative = "admin.html"
        else:
            relative = parsed.path.lstrip("/")
        if relative in {"admin.html", "auth.html", "public-home.html", "index.html"} and seo_page not in {
                 "/", "/app", "/legacy", "/login", "/register", "/admin", "/admin/data-quality", "/admin/performance"} and not seo_page.startswith("/app/"):
            self._json({"error": "Không tìm thấy tài nguyên"}, HTTPStatus.NOT_FOUND)
            return
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", relative) or ".." in relative:
            self._json({"error": "Đường dẫn không hợp lệ"}, HTTPStatus.BAD_REQUEST)
            return
        path = RESOURCE_DIR / "app_icon.png" if relative == "app_icon.png" else WEB_DIR / relative
        if not path.is_file():
            self._json({"error": "Không tìm thấy tài nguyên"}, HTTPStatus.NOT_FOUND)
            return
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
            mime += "; charset=utf-8"
        cache_headers = None
        if seo_page not in {"/", "/loc-du-lieu-mua-sam-cong", "/app", "/admin", "/admin/data-quality", "/admin/performance", "/login", "/register"} and not seo_page.startswith("/app/") and path.suffix.lower() in {".css", ".js", ".png", ".ico", ".svg", ".woff", ".woff2"}:
            stat = path.stat()
            etag = f'W/"{stat.st_size:x}-{stat.st_mtime_ns:x}"'
            cache_headers = {"ETag": etag, "Cache-Control": "public, max-age=300"}
            if self.headers.get("If-None-Match") == etag:
                self._send(b"", mime, HTTPStatus.NOT_MODIFIED, cache_headers)
                return
        data = path.read_bytes()
        if seo_page in {"/", "/loc-du-lieu-mua-sam-cong"}:
            data = render_html(data, seo_page, self.headers.get("Host", ""))
            mime = "text/html; charset=utf-8"
        elif seo_page == "/app" or seo_page.startswith("/app/") or seo_page == "/legacy":
            data = data.replace(b'<meta name="robots" content="index,follow">',
                                b'<meta name="robots" content="noindex,nofollow">', 1)
            if os.environ.get("PORT") not in {None, "", "0"}:
                data = data.replace(b"<body>", b'<body class="cloud-service">', 1)
        self._send(data, mime, headers=cache_headers)

    def do_POST(self):
        self._request_started = time.monotonic()
        self._request_id = uuid.uuid4().hex
        from server.performance import begin_request
        begin_request()
        try:
            origin = self.headers.get("Origin", "")
            if origin and urlparse(origin).netloc.lower() != self.headers.get("Host", "").lower():
                self._json({"error": "Nguồn yêu cầu không hợp lệ."}, HTTPStatus.FORBIDDEN)
                return
            if (production() and self._auth_token() and not self.path.startswith("/internal/jobs/") and
                    (not origin or urlparse(origin).scheme != "https")):
                self._json({"error": "Thiếu xác minh nguồn yêu cầu."}, HTTPStatus.FORBIDDEN)
                return
            if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                self._json({"error": "Yêu cầu phải là JSON."}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            if self.path.startswith("/api/") and self.path not in {
                    "/api/auth/login", "/api/auth/register"} and not self._require_user():
                return
            if not self.path.startswith("/internal/jobs/") and not self._check_rate_limit():
                return
            body = self._read_json()
            if self.path == "/api/admin/users/status":
                from server.admin_users import set_account_active
                try:
                    self._json(set_account_active(self._current_user()["id"],
                        str(body.get("id", "")), body.get("is_active")))
                except PermissionError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if self.path == "/api/auth/login":
                email = str(body.get("email") or "").strip().casefold()[:320]
                key = "login-account:" + hashlib.sha256(email.encode("utf-8")).hexdigest()
                if not RATE_LIMITER.allow(key, 10, 300):
                    self._json({"error": "Thử đăng nhập quá nhanh. Vui lòng thử lại sau."},
                               HTTPStatus.TOO_MANY_REQUESTS, {"Retry-After": "300"})
                    return
            if self.path.startswith("/internal/jobs/"):
                secret = job_secret()
                supplied = self.headers.get("X-Job-Secret", "")
                if len(secret) < 32 or not hmac.compare_digest(secret, supplied):
                    self._json({"error": "Không có quyền chạy job."}, HTTPStatus.FORBIDDEN)
                    return
                from server.background_jobs import (check_followed_tenders, run_saved_searches,
                                             cleanup_expired_downloads)
                if self.path == "/internal/jobs/check-followed-tenders":
                    self._json(check_followed_tenders())
                elif self.path == "/internal/jobs/run-saved-searches":
                    self._json(run_saved_searches())
                elif self.path == "/internal/jobs/cleanup-downloads":
                    self._json({"status": "done", "removed": cleanup_expired_downloads()})
                elif self.path == "/internal/jobs/process-document":
                    from server.document_service import process_pending_documents
                    self._json(process_pending_documents())
                elif self.path == "/internal/jobs/sync-tenders":
                    from server.intelligence_jobs import run_pending
                    self._json(run_pending())
                elif self.path == "/internal/jobs/run-automations":
                    from server.automation_engine import run_due_automations
                    self._json(run_due_automations())
                elif self.path in {"/internal/jobs/run-data-sync", "/internal/jobs/run-sync"}:
                    from server.data_sync import scheduler_tick
                    self._json(scheduler_tick())
                elif self.path == "/internal/jobs/run-data-quality":
                    from server.data_quality.service import process_scan_batch
                    self._json(process_scan_batch())
                else:
                    self._json({"error": "Không tìm thấy job."}, HTTPStatus.NOT_FOUND)
                return
            if self.path.startswith(("/api/documents/", "/api/document-center/", "/api/ai/")):
                from server.document_http import handle_post
                if handle_post(self, self.path, body):
                    return
            if self.path.startswith("/api/admin/data-quality"):
                from server.data_quality.http import handle_post
                if handle_post(self, self.path, body):
                    return
            if self.path.startswith("/api/intelligence/"):
                from server.intelligence_http import handle_post
                if handle_post(self, self.path, body):
                    return
            if self.path.startswith(("/api/reports", "/api/dashboards")):
                from server.reporting_http import handle_post
                if handle_post(self, self.path, body):
                    return
            if self.path.startswith("/api/automations"):
                from server.automation_http import handle_post
                if handle_post(self, self.path, body):
                    return
            if self.path.startswith("/api/data-sync"):
                from server.data_sync_http import handle_post
                if handle_post(self, self.path, body):
                    return
            if self.path == "/api/auth/register":
                user = account_register(body.get("email"), str(body.get("password") or ""))
                _, token = account_login(user["email"], str(body.get("password") or ""))
                secure = "; Secure" if production() else ""
                self._json({"user": user}, HTTPStatus.CREATED,
                           {"Set-Cookie": f"msc_auth={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800{secure}"})
                return
            if self.path == "/api/auth/login":
                user, token = account_login(body.get("email"), str(body.get("password") or ""))
                secure = "; Secure" if production() else ""
                self._json({"user": user}, headers={
                    "Set-Cookie": f"msc_auth={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800{secure}"})
                return
            if self.path == "/api/auth/logout":
                account_logout(self._auth_token())
                secure = "; Secure" if production() else ""
                self._json({"ok": True}, headers={"Set-Cookie":
                           f"msc_auth=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure}"})
                return
            if self.path == "/api/notifications":
                user_id = self._current_user()["id"]
                action = body.get("action")
                with get_db().engine.begin() as conn:
                    scope = user_notifications.c.user_id == user_id
                    if action == "read-all":
                        conn.execute(update(user_notifications).where(scope).values(is_read=True))
                    elif action == "read":
                        conn.execute(update(user_notifications).where(scope,
                            user_notifications.c.id == str(body.get("id") or "")).values(is_read=True))
                    elif action == "delete":
                        conn.execute(delete(user_notifications).where(scope,
                            user_notifications.c.id == str(body.get("id") or "")))
                    else:
                        raise ValueError("Thao tác thông báo không hợp lệ.")
                self._json({"ok": True})
                return
            if self.path == "/api/import-legacy":
                imported = {"watchlist": 0, "presets": 0, "history": 0}
                target = self._stores()
                if not production():
                    existing = {item["code"]: item for item in target.watchlist.read()}
                    for item in WATCHLIST.read():
                        if item["code"] not in existing:
                            existing[item["code"]] = item
                            imported["watchlist"] += 1
                    if imported["watchlist"]:
                        target.watchlist._write(list(existing.values()))
                    for item in PRESETS.read():
                        try:
                            target.presets.update({"action": "save", "name": item["name"], "params": item["params"]})
                            imported["presets"] += 1
                        except (ValueError, KeyError):
                            continue
                    old_history = HISTORY.read()
                else:
                    old_history = []
                supplied = body.get("history") if isinstance(body.get("history"), list) else []
                for item in (old_history + supplied)[:100]:
                    if not isinstance(item, dict):
                        continue
                    try:
                        target.history.add({"params": item})
                        imported["history"] += 1
                    except ValueError:
                        continue
                self._json(imported)
                return
            if self.path == "/api/presets":
                self._json({"presets": self._stores().presets.update(body)})
                return
            if self.path == "/api/watchlist":
                if body.get("action") == "sync":
                    rows = body.get("rows")
                    if not isinstance(rows, list):
                        raise ValueError("Dữ liệu đồng bộ không hợp lệ.")
                    self._json({"items": self._stores().watchlist.sync(rows)})
                else:
                    self._json({"items": self._stores().watchlist.update(body)})
                return
            if self.path == "/api/refresh-watch":
                code = str(body.get("code") or "").strip().upper()
                if not re.fullmatch(r"(?:IB|PL)[A-Z0-9-]{4,40}", code):
                    raise ValueError("Mã theo dõi không hợp lệ.")
                watchlist = self._stores().watchlist
                if code not in {item["code"] for item in watchlist.read()}:
                    raise ValueError("Mã này chưa được theo dõi.")
                client = MuaSamCongClient()
                try:
                    if code.startswith("IB"):
                        records = client.search_notices(code, max_pages=1, page_size=20)
                        record = next((item for item in records if extract_notify_no(item).upper() == code), None)
                    else:
                        records = client.search_plans(code, max_pages=1, page_size=20)
                        record = next((item for item in records if display_plan_no(item.get("planNo")) == code), None)
                    if record is None:
                        raise ValueError("Không tìm thấy mã trên e-GP trong lần kiểm tra này.")
                    row = plan_row_from_search(record)
                    items = watchlist.sync([{"code": code, **asdict(row)}])
                    self._json({"items": items, "row": row_to_public_dict(row, 0)})
                except Exception as exc:
                    watchlist.mark_error(code, str(exc))
                    self._json({"error": str(exc), "items": watchlist.read()}, HTTPStatus.BAD_GATEWAY)
                finally:
                    client.s.close()
                return
            if self.path == "/api/history":
                history = self._stores().history
                self._json({"items": history.add(body) if not body.get("action") else history.update(body)})
                return
            if self.path == "/api/downloads":
                if body.get("action") != "error":
                    raise ValueError("Thao tác tải xuống không hợp lệ.")
                item = self._stores().downloads.record_error(str(body.get("name") or "Xuất dữ liệu.xlsx"),
                                              str(body.get("kind") or "Excel"),
                                              str(body.get("error") or "Không tạo được file"))
                self._json({"item": item})
                return
            if self.path == "/api/search":
                job = start_search(body, owner=self._owner_id())
                self._json(job.public_data(), HTTPStatus.ACCEPTED)
                return
            if self.path == "/api/extract":
                if body.get("job_id"):
                    job = self._job_from_body(body)
                    records = []
                    seen = set()
                    for row in selected_rows(job, body.get("indices", [])):
                        code = row.notify_no or display_plan_no(row.plan_no or row.plan_reference)
                        if not code or (body.get("remove_duplicates", True) and code in seen):
                            continue
                        seen.add(code)
                        records.append({"code": code,
                                        "code_type": "KHLCNT" if code.startswith("PL") else "TBMT",
                                        **extraction_fields(row)})
                    self._json(start_extraction(records, lookup=False, owner=self._owner_id()))
                    return
                encoded = str(body.get("file_base64") or "")
                try:
                    file_data = base64.b64decode(encoded, validate=True) if encoded else b""
                except (ValueError, TypeError) as exc:
                    raise ValueError("Tệp tải lên không hợp lệ.") from exc
                records = extract_tbmt_codes(
                    text=str(body.get("text") or ""), file_data=file_data,
                    filename=str(body.get("filename") or ""),
                    remove_duplicates=bool(body.get("remove_duplicates", True)),
                    text_source=str(body.get("text_source") or "Dữ liệu dán"),
                )
                self._json(start_extraction(records, owner=self._owner_id()), HTTPStatus.ACCEPTED)
                return
            if self.path == "/api/export-codes":
                extraction_id = str(body.get("extraction_id") or "")
                with EXTRACTIONS_LOCK:
                    task = EXTRACTIONS.get(extraction_id)
                    records = [dict(row) for row in task["rows"]] if task and task.get("owner", "") == self._owner_id() else None
                    ready = task and task["state"] == "done"
                if records is None:
                    raise ValueError("Không tìm thấy danh sách mã. Hãy tách mã lại.")
                if not ready:
                    raise ValueError("Đang tra cứu thông tin các mã. Vui lòng chờ hoàn tất rồi xuất Excel.")
                if body.get("expected_count") is not None and body["expected_count"] != len(records):
                    raise ValueError("Danh sách mã đã thay đổi. Hãy lấy lại mã đang lọc rồi xuất Excel.")
                data = build_extraction_workbook(records)
                kind = "TBMT_KHLCNT" if any(row["code"].startswith("PL") for row in records) else "TBMT"
                filename = f"Danh_sach_ma_{kind}_{datetime.now():%Y%m%d_%H%M}.xlsx"
                archive_download(data, filename, "Danh sách mã", self._stores().downloads)
                self._send(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                    "X-Filename": filename})
                return
            if self.path == "/api/export":
                job = self._job_from_body(body)
                rows = selected_rows(job, body.get("indices"))
                if not rows:
                    raise ValueError("Chưa chọn dòng nào để xuất.")
                notice_mode = job.params.get("mode") == "Thông báo mời thầu"
                data = build_result_workbook(rows, notice_mode)
                prefix = "TBMT" if notice_mode else "KHLCNT"
                filename = f"{prefix}_{datetime.now():%Y%m%d_%H%M}.xlsx"
                archive_download(data, filename, "Excel kết quả", self._stores().downloads)
                self._send(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                    "X-Filename": filename})
                return
            if self.path == "/api/check-lot":
                job = self._job_from_body(body)
                rows = selected_rows(job, [body.get("index")])
                if len(rows) != 1:
                    raise ValueError("Hãy chọn một dòng để kiểm tra file phân lô.")
                row = rows[0]
                if row.lot_file_status not in {"done", "Ko co file", "Không có file"}:
                    _, issues = prepare_lot_download(rows, allow_empty=True)
                else:
                    issues = []
                self._json({"index": body.get("index"), "lot_file_status": row.lot_file_status,
                            "has_lots": bool(row.lot_data and row.lot_file_status == "done"),
                            "reason": issues[0]["reason"] if issues else ""})
                return
            if self.path == "/api/lots":
                if body.get("extraction_id"):
                    with EXTRACTIONS_LOCK:
                        task = EXTRACTIONS.get(str(body["extraction_id"]))
                        records = list(task["rows"]) if task and task.get("owner", "") == self._owner_id() else None
                    if records is None:
                        raise ValueError("Không tìm thấy danh sách mã. Hãy tra cứu lại.")
                    requested = body.get("indices", [])
                    if any(isinstance(index, int) and 0 <= index < len(records)
                           and records[index]["code"].startswith("PL") for index in requested):
                        raise ValueError("File phân lô chỉ áp dụng cho mã TBMT (IB), không áp dụng cho KHLCNT (PL).")
                    job = SearchJob({})
                    job.rows = [ResultRow(notify_no=record["code"]) for record in records]
                else:
                    job = self._job_from_body(body)
                rows = selected_rows(job, body.get("indices", []))
                ready, issues = prepare_lot_download(rows, allow_empty=True)
                files, issues = build_lot_download(ready, issues) if ready else ([], issues)
                result = self._stores().lot_files.add(files, issues)
                for entry, file in zip(result["files"], files):
                    archived = archive_download(file["data"], file["name"], "Excel phân lô", self._stores().downloads)
                    if archived:
                        entry["archive_url"] = archived["url"]
                selected_ids = {id(row) for row in rows}
                result["checks"] = [{"index": index, "lot_file_status": row.lot_file_status,
                                     "has_lots": bool(row.lot_data and row.lot_file_status == "done")}
                                    for index, row in enumerate(job.rows) if id(row) in selected_ids]
                result["requested"] = len(rows)
                self._json(result)
                return
            if self.path == "/api/shutdown":
                if os.environ.get("PORT") not in {None, "", "0"}:
                    self._json({"error": "Không hỗ trợ dừng server trên môi trường triển khai."}, HTTPStatus.FORBIDDEN)
                    return
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self._json({"error": "Không tìm thấy API"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            logging.exception("Web request failed", extra={"event": "request_error",
                "request_id": self._request_id, "route": urlparse(self.path).path,
                "method": self.command})
            self._json({"error": "internal_error", "message": "Máy chủ gặp lỗi. Vui lòng thử lại sau.",
                        "error_id": "ERR-" + self._request_id[:12]}, HTTPStatus.INTERNAL_SERVER_ERROR)


def run_web_app(open_browser: bool = True) -> None:
    validate_production_config()
    if production():
        from server.logging_config import configure_production_logging
        configure_production_logging()
    validate_session_config()
    storage_backend()
    get_db()
    port = int(os.environ.get("PORT") or "0")
    host = "0.0.0.0" if port else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), WebHandler)
    url = f"http://127.0.0.1:{server.server_port}/"
    if not port and open_browser and os.environ.get("MUASAMCONG_NO_BROWSER") != "1":
        threading.Timer(0.7, lambda: webbrowser.open(url + "app")).start()
    # Bản EXE windowed không có stdout.
    if sys.stdout is not None:
        print(f"MuaSamCong Web: {host}:{server.server_port}" if port else f"MuaSamCong Web: {url}")
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        LOT_FILES.close()
        get_db().engine.dispose()


if __name__ == "__main__":
    run_web_app()
