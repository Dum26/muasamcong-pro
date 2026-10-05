"""Validated, bounded conditions for user automation rules."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

TEXT_FIELDS = {"tender_code", "khlcnt_code", "title", "investor_name",
    "procuring_entity_name", "winning_contractor", "location", "status",
    "selection_method", "contract_type", "tag", "changed_field", "saved_search"}
NUMBER_FIELDS = {"package_price", "winning_price"}
DATE_FIELDS = {"publish_date", "bid_closing_date", "result_date"}
BOOLEAN_FIELDS = {"is_followed"}
FIELDS = TEXT_FIELDS | NUMBER_FIELDS | DATE_FIELDS | BOOLEAN_FIELDS
TEXT_OPS = {"equals", "not_equals", "contains", "not_contains", "starts_with", "ends_with"}
NUMBER_OPS = {"equal", "not_equals", "greater_than", "greater_or_equal",
    "less_than", "less_or_equal", "between"}
DATE_OPS = {"before", "after", "between", "within_days", "equals"}
BOOLEAN_OPS = {"is", "is_not"}
LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _decimal(value) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Giá trị tiền phải là số hợp lệ.") from exc
    if not number.is_finite() or abs(number) > Decimal("999999999999999999999999"):
        raise ValueError("Giá trị tiền vượt giới hạn.")
    return number


def _date(value) -> date:
    try:
        if isinstance(value, datetime):
            return value.date()
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError) as exc:
        raise ValueError("Ngày phải có dạng YYYY-MM-DD.") from exc


def validate_condition(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Điều kiện không hợp lệ.")
    field, operator = raw.get("field"), raw.get("operator")
    allowed = (TEXT_OPS if field in TEXT_FIELDS else NUMBER_OPS if field in NUMBER_FIELDS
               else DATE_OPS if field in DATE_FIELDS else BOOLEAN_OPS if field in BOOLEAN_FIELDS
               else set())
    if operator not in allowed:
        raise ValueError("Trường hoặc phép so sánh không được hỗ trợ.")
    value = raw.get("value")
    if operator == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("Khoảng so sánh cần hai giá trị.")
        parsed = [_decimal(item) if field in NUMBER_FIELDS else _date(item) for item in value]
        if parsed[0] > parsed[1]:
            raise ValueError("Khoảng so sánh bị đảo chiều.")
        value = [str(item) if field in NUMBER_FIELDS else item.isoformat() for item in parsed]
    elif field in NUMBER_FIELDS:
        value = str(_decimal(value))
    elif operator == "within_days":
        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Số ngày phải là số nguyên.") from exc
        if not 1 <= value <= 365:
            raise ValueError("Số ngày phải từ 1 đến 365.")
    elif field in DATE_FIELDS:
        value = _date(value).isoformat()
    elif field in BOOLEAN_FIELDS:
        if not isinstance(value, bool):
            raise ValueError("Điều kiện theo dõi cần true hoặc false.")
    else:
        value = str(value or "").strip()
        if not value or len(value) > 320:
            raise ValueError("Giá trị chữ phải có từ 1 đến 320 ký tự.")
    return {"field": field, "operator": operator, "value": value}


def validate_group(raw: dict, depth: int = 0) -> dict:
    if not isinstance(raw, dict) or depth > 2:
        raise ValueError("Nhóm điều kiện không hợp lệ hoặc quá sâu.")
    logic = raw.get("logic", "AND")
    items = raw.get("items", [])
    if logic not in {"AND", "OR"} or not isinstance(items, list) or len(items) > 12:
        raise ValueError("Nhóm chỉ hỗ trợ AND/OR với tối đa 12 điều kiện.")
    clean = [validate_group(item, depth + 1) if isinstance(item, dict) and "items" in item
             else validate_condition(item) for item in items]
    return {"logic": logic, "items": clean}


def evaluate_condition(entity: dict, condition: dict, *, today: date | None = None) -> bool:
    field, operator, expected = (condition[key] for key in ("field", "operator", "value"))
    actual = entity.get(field)
    if field == "tag":
        values = [str(item).casefold() for item in entity.get("tags", [])]
        needle = str(expected).casefold()
        return (needle in values) if operator == "equals" else (needle not in values) if operator == "not_equals" else any(needle in item for item in values) if operator == "contains" else not any(needle in item for item in values) if operator == "not_contains" else any(item.startswith(needle) for item in values) if operator == "starts_with" else any(item.endswith(needle) for item in values)
    if field in BOOLEAN_FIELDS:
        return bool(actual) is expected if operator == "is" else bool(actual) is not expected
    if actual is None or actual == "":
        return False
    if field in NUMBER_FIELDS:
        try:
            left = _decimal(actual)
        except ValueError:
            return False
        if operator == "between":
            return _decimal(expected[0]) <= left <= _decimal(expected[1])
        right = _decimal(expected)
        return {"equal": left == right, "not_equals": left != right,
            "greater_than": left > right, "greater_or_equal": left >= right,
            "less_than": left < right, "less_or_equal": left <= right}[operator]
    if field in DATE_FIELDS:
        try:
            left = _date(actual)
        except ValueError:
            return False
        if operator == "between":
            return _date(expected[0]) <= left <= _date(expected[1])
        if operator == "within_days":
            current = today or datetime.now(LOCAL_TZ).date()
            return current <= left <= current + timedelta(days=expected)
        right = _date(expected)
        return {"equals": left == right, "before": left < right, "after": left > right}[operator]
    left, right = str(actual).casefold(), str(expected).casefold()
    return {"equals": left == right, "not_equals": left != right,
        "contains": right in left, "not_contains": right not in left,
        "starts_with": left.startswith(right), "ends_with": left.endswith(right)}[operator]


def evaluate_group(entity: dict, group: dict, *, today: date | None = None) -> bool:
    results = [evaluate_group(entity, item, today=today) if "items" in item
               else evaluate_condition(entity, item, today=today) for item in group["items"]]
    return all(results) if group["logic"] == "AND" else any(results)


def evaluate_rule(entity: dict, rule: dict, *, today: date | None = None) -> bool:
    return evaluate_group(entity, rule["conditions_json"], today=today)
