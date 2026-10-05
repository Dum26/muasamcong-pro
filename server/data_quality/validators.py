"""Pure validators that report evidence without changing source records."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from server.data_quality.rules import RULES, settings
from server.data_quality.normalization import safe_display_text


def _issue(code: str, field: str | None, message: str, details: dict | None = None) -> dict:
    return {"rule_code": code, "field_name": field, "severity": RULES[code].severity,
            "message": message, "details_json": details or {}}


def _date(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def validate_tender(row: dict, *, current: datetime | None = None) -> list[dict]:
    issues = []
    code = str(row.get("tender_code") or "")
    if code and not re.fullmatch(r"(?:IB|TBMT)[A-Za-z0-9._-]{4,48}", code, re.I):
        issues.append(_issue("TENDER_INVALID_CODE", "tender_code", "Mã gói cần đối chiếu định dạng nguồn."))
    if not str(row.get("title") or "").strip():
        issues.append(_issue("TENDER_MISSING_TITLE", "title", "Chưa có tên gói thầu."))
    elif safe_display_text(row["title"]) != row["title"]:
        issues.append(_issue("TENDER_EXTRA_WHITESPACE", "title",
            "Tên gói có khoảng trắng thừa; có thể chuẩn hóa an toàn."))
    for field in ("title", "investor_name", "procuring_entity_name", "location"):
        if "\ufffd" in str(row.get(field) or ""):
            issues.append(_issue("INVALID_ENCODING", field, f"{field} có ký tự thay thế do lỗi mã hóa."))
    dates = {}
    for field in ("publish_date", "bid_closing_date", "result_date"):
        value = row.get(field)
        if value:
            dates[field] = _date(value)
            if dates[field] is None:
                issues.append(_issue("TENDER_INVALID_DATE", field, f"Không đọc được {field}."))
    if dates.get("publish_date") and dates.get("bid_closing_date") and dates["bid_closing_date"] < dates["publish_date"]:
        issues.append(_issue("TENDER_DEADLINE_BEFORE_PUBLISH", "bid_closing_date",
            "Thời điểm đóng thầu trước ngày đăng tải.",
            {"publish_date": str(row["publish_date"]), "bid_closing_date": str(row["bid_closing_date"])}))
    for field in ("package_price", "winning_price"):
        value = row.get(field)
        if value is not None:
            try:
                invalid = not Decimal(str(value)).is_finite() or Decimal(str(value)) < 0
            except Exception:
                invalid = True
            if invalid:
                issues.append(_issue("TENDER_INVALID_PRICE", field, f"{field} không hợp lệ."))
    package, winning = row.get("package_price"), row.get("winning_price")
    if package is not None and winning is not None:
        try:
            if Decimal(str(package)) >= 0 and Decimal(str(winning)) > Decimal(str(package)):
                issues.append(_issue("TENDER_WINNING_PRICE_HIGHER", "winning_price",
                    "Giá trúng cao hơn giá gói; cần đối chiếu bản công bố."))
        except Exception:
            pass
    if row.get("sync_status") == "failed" or row.get("sync_error"):
        issues.append(_issue("SYNC_FAILED", "sync_status", "Đồng bộ gói gần nhất gặp lỗi."))
    stamp = _date(row.get("last_success_at") or row.get("last_synced_at"))
    if stamp and ((current or datetime.now(timezone.utc)) - stamp).days > settings()["stale_tender_days"]:
        issues.append(_issue("TENDER_STALE", "last_success_at", "Gói chưa được đồng bộ trong ngưỡng cấu hình."))
    if not row.get("investor_name") and not row.get("procuring_entity_name"):
        issues.append(_issue("PARTIAL_DATA", None, "Chưa có chủ đầu tư và bên mời thầu."))
    return issues


def validate_document(row: dict, *, current: datetime | None = None) -> list[dict]:
    issues = []
    digest = row.get("content_hash")
    if digest and not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
        issues.append(_issue("DOCUMENT_INVALID_HASH", "content_hash", "SHA-256 đã lưu không hợp lệ."))
    if row.get("status") == "failed":
        issues.append(_issue("DOCUMENT_FAILED", "status", "Tải hoặc đọc tài liệu thất bại."))
    stamp = _date(row.get("last_seen_at"))
    if stamp and ((current or datetime.now(timezone.utc)) - stamp).days > settings()["stale_document_days"]:
        issues.append(_issue("DOCUMENT_STALE", "last_seen_at", "Metadata tài liệu chưa được quan sát lại."))
    return issues


def validate_plan(row: dict, *, current: datetime | None = None) -> list[dict]:
    issues = []
    code = str(row.get("plan_code") or "")
    if code and not re.fullmatch(r"(?:PL|KHLCNT)[A-Za-z0-9._-]{4,48}", code, re.I):
        issues.append(_issue("PLAN_INVALID_CODE", "plan_code", "Mã kế hoạch cần đối chiếu định dạng nguồn."))
    if not str(row.get("title") or "").strip():
        issues.append(_issue("PLAN_MISSING_TITLE", "title", "Chưa có tên kế hoạch."))
    if row.get("publish_date") and _date(row["publish_date"]) is None:
        issues.append(_issue("PLAN_INVALID_DATE", "publish_date", "Không đọc được ngày đăng kế hoạch."))
    price = row.get("package_price")
    if price is not None:
        try:
            number = Decimal(str(price))
            invalid = not number.is_finite() or number < 0
        except (ValueError, TypeError, ArithmeticError):
            invalid = True
        if invalid:
            issues.append(_issue("PLAN_INVALID_PRICE", "package_price", "Giá kế hoạch không hợp lệ."))
    if "\ufffd" in str(row.get("title") or ""):
        issues.append(_issue("INVALID_ENCODING", "title", "Tên kế hoạch có ký tự lỗi mã hóa."))
    stamp = _date(row.get("last_seen_at"))
    if stamp and ((current or datetime.now(timezone.utc)) - stamp).days > settings()["stale_tender_days"]:
        issues.append(_issue("PLAN_STALE", "last_seen_at", "Kế hoạch chưa được quan sát lại."))
    return issues
