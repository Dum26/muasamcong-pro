"""Stable rule registry and review thresholds."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    code: str
    entity_type: str
    severity: str
    description: str


RULES = {rule.code: rule for rule in (
    Rule("TENDER_MISSING_TITLE", "tender", "warning", "Gói thiếu tên."),
    Rule("TENDER_EXTRA_WHITESPACE", "tender", "info", "Tên gói có khoảng trắng thừa."),
    Rule("TENDER_INVALID_CODE", "tender", "error", "Mã TBMT không phù hợp định dạng đã biết."),
    Rule("TENDER_INVALID_DATE", "tender", "warning", "Ngày không thể đọc được."),
    Rule("TENDER_DEADLINE_BEFORE_PUBLISH", "tender", "warning", "Đóng thầu trước ngày đăng."),
    Rule("TENDER_INVALID_PRICE", "tender", "error", "Giá âm hoặc không hợp lệ."),
    Rule("TENDER_WINNING_PRICE_HIGHER", "tender", "info", "Giá trúng cao hơn giá gói; cần đối chiếu nguồn."),
    Rule("TENDER_STALE", "tender", "warning", "Dữ liệu gói chưa được đồng bộ gần đây."),
    Rule("SYNC_FAILED", "tender", "warning", "Lần đồng bộ gần nhất gặp lỗi."),
    Rule("PARTIAL_DATA", "tender", "info", "Gói thiếu thông tin quan trọng chưa xác minh."),
    Rule("BROKEN_RELATION", "tender", "critical", "Khóa liên kết không có bản ghi đích."),
    Rule("INVALID_ENCODING", "tender", "warning", "Văn bản có ký tự lỗi mã hóa."),
    Rule("DOCUMENT_ORPHAN", "document", "error", "Tài liệu không có gói liên quan."),
    Rule("DOCUMENT_INVALID_HASH", "document", "warning", "SHA-256 đã lưu không hợp lệ."),
    Rule("DOCUMENT_DUPLICATE", "document", "info", "Nhiều tài liệu cùng gói có cùng SHA-256."),
    Rule("DOCUMENT_STALE", "document", "info", "Metadata tài liệu chưa được quan sát lại."),
    Rule("DOCUMENT_FAILED", "document", "warning", "Tải hoặc trích xuất tài liệu thất bại."),
    Rule("ENTITY_NAME_VARIANT", "entity", "info", "Pháp nhân có tên gần giống, cần đối chiếu định danh."),
    Rule("PLAN_MISSING_TITLE", "plan", "warning", "Kế hoạch thiếu tên."),
    Rule("PLAN_INVALID_CODE", "plan", "error", "Mã KHLCNT cần đối chiếu định dạng nguồn."),
    Rule("PLAN_INVALID_DATE", "plan", "warning", "Ngày đăng kế hoạch không thể đọc được."),
    Rule("PLAN_INVALID_PRICE", "plan", "error", "Giá kế hoạch âm hoặc không hợp lệ."),
    Rule("PLAN_BROKEN_RELATION", "plan", "critical", "Chủ đầu tư liên kết không tồn tại."),
    Rule("PLAN_STALE", "plan", "info", "Kế hoạch chưa được quan sát lại trong ngưỡng cấu hình."),
    Rule("SOURCE_SCHEMA_CHANGE", "source", "error", "Nguồn có thể đã thay đổi cấu trúc phản hồi."),
    Rule("SOURCE_DEGRADED", "source", "warning", "Nguồn dữ liệu đang suy giảm hoặc không khả dụng."),
    Rule("SOURCE_CONFLICT", "tender", "warning", "Giá trị cache khác snapshot nguồn gần nhất."),
)}


def settings() -> dict:
    def integer(name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            return min(max(int(os.environ.get(name, str(default))), minimum), maximum)
        except ValueError:
            return default
    try:
        confidence = float(os.environ.get("DUPLICATE_CONFIDENCE_THRESHOLD", "0.85"))
    except ValueError:
        confidence = 0.85
    return {"enabled": os.environ.get("DATA_QUALITY_ENABLED", "true").lower() == "true",
            "batch_size": integer("DATA_QUALITY_BATCH_SIZE", 100, 10, 1000),
            "stale_tender_days": integer("STALE_TENDER_DAYS", 14, 1, 365),
            "stale_document_days": integer("STALE_DOCUMENT_DAYS", 30, 1, 365),
            "duplicate_confidence": min(max(confidence, 0.5), 1.0)}
