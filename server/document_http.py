"""Authenticated HTTP handlers for private document and AI routes."""
from __future__ import annotations

import re
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, quote

from sqlalchemy import Numeric, func, select

from server.config import ai_settings, inline_extraction_bytes, max_upload_bytes, storage_backend
from server.database import (ai_usage, document_analyses, document_processing,
    document_versions, documents, get_db, tender_source_documents, users,
    audit_logs, now)
from server.document_ai import AIUnavailable, analysis_history, analyze
from server.document_service import (delete_document, document_content, document_for_user,
                              download_document, link_document, list_documents,
                              process_document, upload_document)

DOC_ROUTE = re.compile(r"^/api/documents/([0-9a-f]{32})(?:/(content|download|analyses|process|ocr|link|delete))?$")


def handle_get(handler, parsed) -> bool:
    path = parsed.path
    user = handler._current_user()
    if path == "/api/document-center":
        from server.document_center import catalog
        query = parse_qs(parsed.query)
        value = lambda key, default="": (query.get(key) or [default])[0]
        try:
            handler._json(catalog(user["id"], page=value("page", "1"),
                page_size=value("page_size", "25"), query=value("q"),
                source=value("source", "all"), tender_code=value("tender_code"),
                plan_code=value("plan_code"), document_type=value("type"),
                status=value("status"),
                sort=value("sort", "updated")))
        except ValueError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True
    if path == "/api/document-center/export":
        from server.document_center import export_metadata
        query = parse_qs(parsed.query)
        value = lambda key, default="": (query.get(key) or [default])[0]
        try:
            data = export_metadata(user["id"], query=value("q"),
                source=value("source", "all"), tender_code=value("tender_code"),
                plan_code=value("plan_code"), document_type=value("type"),
                status=value("status"), sort=value("sort", "updated"))
            handler._send(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=Document_Center.xlsx"})
        except ValueError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True
    if path == "/api/document-center/compare":
        from server.document_center import compare_uploaded
        query = parse_qs(parsed.query)
        try:
            handler._json(compare_uploaded(user["id"],
                (query.get("first") or [""])[0], (query.get("second") or [""])[0]))
        except LookupError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True
    center_match = re.fullmatch(r"/api/document-center/(upload|egp)/([0-9a-f]{32})", path)
    if center_match:
        from server.document_center import detail
        result = detail(user["id"], *center_match.groups())
        handler._json(result or {"error": "Không tìm thấy tài liệu."},
                      HTTPStatus.OK if result else HTTPStatus.NOT_FOUND)
        return True
    file_match = re.fullmatch(r"/api/document-center/egp/([0-9a-f]{32})/(download|preview)", path)
    if file_match:
        from server.source_documents import cached_source_file
        file = cached_source_file(file_match.group(1))
        if not file:
            handler._json({"error": "File chưa được tải từ nguồn. Hãy bấm Tải file trước."},
                          HTTPStatus.CONFLICT)
        else:
            data, filename, mime = file
            with get_db().engine.begin() as conn:
                conn.execute(audit_logs.insert().values(id=uuid.uuid4().hex,
                    user_id=user["id"], action="document_download" if file_match.group(2) == "download" else "document_preview",
                    entity_type="source_document", entity_id=file_match.group(1), created_at=now()))
            disposition = "inline" if file_match.group(2) == "preview" and mime == "application/pdf" else "attachment"
            handler._send(data, mime, headers={"Content-Disposition":
                f"{disposition}; filename=\"document{Path(filename).suffix}\"; filename*=UTF-8''{quote(filename)}",
                "X-Content-Type-Options": "nosniff"})
        return True
    compare_match = re.fullmatch(r"/api/document-center/egp/([0-9a-f]{32})/compare", path)
    if compare_match:
        from server.source_documents import compare_source_versions
        query = parse_qs(parsed.query)
        try:
            result = compare_source_versions(user["id"], compare_match.group(1),
                int((query.get("first") or [""])[0]),
                int((query.get("second") or [""])[0]))
            handler._json(result)
        except LookupError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True
    if path == "/api/ai/config":
        settings = ai_settings()
        handler._json({"enabled": settings["enabled"], "configured": settings["configured"],
                       "provider": settings["provider"], "model": settings["model"],
                       "max_upload_mb": max_upload_bytes() // (1024 * 1024),
                       "inline_extract_mb": inline_extraction_bytes() // (1024 * 1024),
                       "storage": storage_backend()})
        return True
    if path == "/api/documents":
        query = parse_qs(parsed.query)
        try:
            result = list_documents(user["id"], (query.get("page") or [1])[0],
                                    tender_code=(query.get("tender_code") or [""])[0][:50])
        except ValueError:
            handler._json({"error": "Trang không hợp lệ."}, HTTPStatus.BAD_REQUEST)
        else:
            handler._json(result)
        return True
    if path == "/api/admin/ai-stats":
        if user["role"] != "admin":
            handler._json({"error": "Không có quyền truy cập."}, HTTPStatus.FORBIDDEN)
            return True
        today = datetime.now(timezone.utc).date().isoformat()
        with get_db().engine.connect() as conn:
            count = lambda table: conn.scalar(select(func.count()).select_from(table)) or 0
            document_count, analysis_count = count(documents), count(document_analyses)
            source_count, version_count = count(tender_source_documents), count(document_versions)
            source_downloaded = conn.scalar(select(func.count()).select_from(tender_source_documents)
                .where(tender_source_documents.c.storage_key.is_not(None))) or 0
            metadata_only = conn.scalar(select(func.count()).select_from(tender_source_documents)
                .where(tender_source_documents.c.status == "metadata_only")) or 0
            source_failed = conn.scalar(select(func.count()).select_from(tender_source_documents)
                .where(tender_source_documents.c.status == "failed")) or 0
            storage_bytes = (conn.scalar(select(func.coalesce(func.sum(documents.c.size), 0))) or 0) + (
                conn.scalar(select(func.coalesce(func.sum(tender_source_documents.c.file_size), 0))
                    .where(tender_source_documents.c.storage_key.is_not(None))) or 0)
            requests_today = conn.scalar(select(func.count()).select_from(ai_usage)
                .where(ai_usage.c.created_at >= today)) or 0
            tokens = conn.execute(select(func.coalesce(func.sum(ai_usage.c.input_tokens), 0),
                func.coalesce(func.sum(ai_usage.c.output_tokens), 0))).first()
            by_model = conn.execute(select(ai_usage.c.model, func.count().label("requests"),
                func.sum(ai_usage.c.input_tokens).label("input_tokens"),
                func.sum(ai_usage.c.output_tokens).label("output_tokens"),
                func.sum(func.cast(ai_usage.c.estimated_cost, Numeric(18, 6))).label("estimated_cost"))
                .group_by(ai_usage.c.model)).mappings().all()
            known_costs = conn.execute(select(ai_usage.c.estimated_cost)
                .where(ai_usage.c.estimated_cost.is_not(None))).scalars().all()
            failures = conn.scalar(select(func.count()).select_from(document_processing)
                .where(document_processing.c.status == "failed")) or 0
            average_ms = conn.scalar(select(func.avg(document_processing.c.duration_ms))
                .where(document_processing.c.status == "completed"))
            by_user = conn.execute(select(users.c.email, func.count().label("requests"),
                func.sum(ai_usage.c.input_tokens).label("input_tokens"),
                func.sum(ai_usage.c.output_tokens).label("output_tokens"))
                .select_from(ai_usage.join(users, ai_usage.c.user_id == users.c.id))
                .group_by(users.c.id, users.c.email).order_by(func.count().desc())
                .limit(50)).mappings().all()
        total_cost = str(sum((Decimal(value) for value in known_costs), Decimal(0))) if known_costs else None
        handler._json({"documents": document_count, "analyses": analysis_count,
                       "source_documents": source_count,
                       "source_metadata_only": metadata_only,
                       "source_downloaded": source_downloaded,
                       "source_failed": source_failed,
                       "document_versions": version_count,
                       "document_storage_bytes": storage_bytes,
                       "requests_today": requests_today, "input_tokens": tokens[0],
                       "output_tokens": tokens[1], "estimated_cost": total_cost,
                       "extraction_failures": failures,
                       "average_processing_ms": round(average_ms) if average_ms is not None else None,
                       "by_user": [dict(row) for row in by_user],
                       "by_model": [{**dict(row), "estimated_cost": str(row["estimated_cost"])
                                     if row["estimated_cost"] is not None else None} for row in by_model]})
        return True
    match = DOC_ROUTE.fullmatch(path)
    if not match:
        return False
    document_id, action = match.groups()
    if action == "download":
        file = download_document(user["id"], document_id)
        if not file:
            handler._json({"error": "Không tìm thấy tài liệu."}, HTTPStatus.NOT_FOUND)
        else:
            data, filename, mime = file
            with get_db().engine.begin() as conn:
                conn.execute(audit_logs.insert().values(id=uuid.uuid4().hex,
                    user_id=user["id"], action="document_download",
                    entity_type="private_document", entity_id=document_id, created_at=now()))
            handler._send(data, mime, headers={"Content-Disposition":
                f"attachment; filename=\"document{Path(filename).suffix}\"; filename*=UTF-8''{quote(filename)}"})
        return True
    if action == "content":
        query = parse_qs(parsed.query)
        try:
            result = document_content(user["id"], document_id, (query.get("page") or [1])[0])
        except ValueError:
            handler._json({"error": "Trang không hợp lệ."}, HTTPStatus.BAD_REQUEST)
        else:
            handler._json(result or {"error": "Không tìm thấy tài liệu."},
                          HTTPStatus.OK if result else HTTPStatus.NOT_FOUND)
        return True
    if action == "analyses":
        try:
            handler._json({"items": analysis_history(user["id"], document_id)})
        except LookupError:
            handler._json({"error": "Không tìm thấy tài liệu."}, HTTPStatus.NOT_FOUND)
        return True
    document = document_for_user(user["id"], document_id)
    handler._json({"document": {key: document[key] for key in (
        "id", "tender_code", "filename", "mime_type", "size", "status",
        "scan_likely", "error", "created_at", "updated_at")} if document else None}
        if document else {"error": "Không tìm thấy tài liệu."},
        HTTPStatus.OK if document else HTTPStatus.NOT_FOUND)
    return True


def handle_post(handler, path: str, body: dict) -> bool:
    user = handler._current_user()
    source_match = re.fullmatch(r"/api/document-center/egp/([0-9a-f]{32})/(fetch|extract|ai-import)", path)
    if source_match:
        from server.source_documents import fetch_source_document, extract_source_document, import_source_for_ai
        from server.source.errors import SourceError
        try:
            action = source_match.group(2)
            result = (fetch_source_document(user["id"], source_match.group(1),
                force=body.get("force") is True) if action == "fetch" else
                extract_source_document(user["id"], source_match.group(1)) if action == "extract"
                else import_source_for_ai(user["id"], source_match.group(1)))
            handler._json(result)
        except LookupError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except (ValueError, TimeoutError) as exc:
            handler._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except SourceError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
        return True
    if path == "/api/ai/export":
        from server.document_export import export_analysis
        try:
            data, filename, mime = export_analysis(user["id"], str(body.get("analysis_id") or ""),
                str(body.get("format") or "xlsx"))
        except LookupError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        else:
            handler._send(data, mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
        return True
    if path == "/api/documents/upload":
        handler._json({"document": upload_document(user["id"], body)}, HTTPStatus.CREATED)
        return True
    if path == "/api/ai/analyze":
        try:
            result = analyze(user["id"], str(body.get("document_id") or ""),
                str(body.get("operation") or ""), str(body.get("question") or ""),
                str(body.get("related_document_id") or ""), body.get("refresh") is True)
        except AIUnavailable as exc:
            handler._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        except LookupError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        else:
            handler._json(result)
        return True
    match = DOC_ROUTE.fullmatch(path)
    if not match:
        return False
    document_id, action = match.groups()
    if action == "ocr":
        if not document_for_user(user["id"], document_id):
            handler._json({"error": "Không tìm thấy tài liệu."}, HTTPStatus.NOT_FOUND)
        else:
            handler._json({"error": "OCR chưa được cấu hình cho PDF scan."}, HTTPStatus.SERVICE_UNAVAILABLE)
        return True
    if action == "process":
        try:
            handler._json({"document": process_document(user["id"], document_id)})
        except LookupError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        return True
    if action == "link":
        try:
            handler._json({"document": link_document(user["id"], document_id,
                                                   str(body.get("tender_code") or ""))})
        except LookupError as exc:
            handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        return True
    if action == "delete":
        deleted = delete_document(user["id"], document_id)
        handler._json({"ok": True} if deleted else {"error": "Không tìm thấy tài liệu."},
                      HTTPStatus.OK if deleted else HTTPStatus.NOT_FOUND)
        return True
    return False
