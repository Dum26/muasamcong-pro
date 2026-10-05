"""User-scoped document CRUD and extraction lifecycle."""
from __future__ import annotations

import base64
import hashlib
import logging
import re
import time
import uuid

from sqlalchemy import delete, insert, or_, select, update

from server.database import (ai_conversations, ai_messages, ai_usage, document_analyses,
                      document_processing, document_text, documents, get_db, now)
from server.document_extract import extract_text, validate_file
from server.document_storage import get_storage, object_key


def _id() -> str:
    return uuid.uuid4().hex


def _public(row: dict) -> dict:
    return {key: row[key] for key in ("id", "tender_code", "filename", "mime_type", "size",
            "status", "scan_likely", "error", "created_at", "updated_at")}


def document_for_user(user_id: str, document_id: str) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{32}", str(document_id)):
        return None
    with get_db().engine.connect() as conn:
        row = conn.execute(select(documents).where(documents.c.id == document_id,
            documents.c.user_id == user_id)).mappings().first()
    return dict(row) if row else None


def list_documents(user_id: str, page: int = 1, limit: int = 20, tender_code: str = "") -> dict:
    page = max(1, min(int(page), 100_000))
    limit = max(1, min(int(limit), 50))
    conditions = [documents.c.user_id == user_id]
    if tender_code:
        conditions.append(documents.c.tender_code == tender_code)
    with get_db().engine.connect() as conn:
        rows = conn.execute(select(documents).where(*conditions)
            .order_by(documents.c.created_at.desc()).offset((page - 1) * limit).limit(limit + 1)).mappings().all()
    return {"items": [_public(dict(row)) for row in rows[:limit]], "page": page,
            "has_more": len(rows) > limit}


def upload_document(user_id: str, body: dict) -> dict:
    try:
        encoded = body.get("data")
        if not isinstance(encoded, str):
            raise ValueError("Thiếu nội dung file.")
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Nội dung file không hợp lệ.") from exc
    filename, mime = validate_file(str(body.get("filename") or ""),
                                   str(body.get("mime_type") or ""), data)
    tender_code = str(body.get("tender_code") or "").strip().upper()
    if tender_code and not re.fullmatch(r"(?:IB|PL)[A-Z0-9-]{4,40}", tender_code):
        raise ValueError("Mã TBMT/KHLCNT liên kết không hợp lệ.")
    document_id = _id()
    key = object_key(user_id, document_id)
    get_storage().put(key, data, mime)
    stamp = now()
    item = dict(id=document_id, user_id=user_id, tender_code=tender_code or None,
                filename=filename, original_filename=filename, mime_type=mime,
                size=len(data), sha256=hashlib.sha256(data).hexdigest(), storage_key=key,
                status="uploaded", scan_likely=False, error="", created_at=stamp, updated_at=stamp)
    try:
        with get_db().engine.begin() as conn:
            conn.execute(insert(documents).values(**item))
    except Exception:
        get_storage().delete(key)
        raise
    return _public(item)


def document_content(user_id: str, document_id: str, page: int = 1, limit: int = 80) -> dict | None:
    document = document_for_user(user_id, document_id)
    if not document:
        return None
    page = max(1, int(page))
    limit = max(1, min(int(limit), 100))
    with get_db().engine.connect() as conn:
        rows = conn.execute(select(document_text).where(document_text.c.document_id == document_id)
            .order_by(document_text.c.source_id).offset((page - 1) * limit).limit(limit + 1)).mappings().all()
    return {"document": _public(document), "chunks": [dict(row) for row in rows[:limit]],
            "page": page, "has_more": len(rows) > limit}


def process_document(user_id: str, document_id: str) -> dict:
    document = document_for_user(user_id, document_id)
    if not document:
        raise LookupError("Không tìm thấy tài liệu.")
    if document["status"] == "extracting":
        return _public(document)
    started = time.monotonic()
    attempt_id = _id()
    with get_db().engine.begin() as conn:
        changed = conn.execute(update(documents).where(documents.c.id == document_id,
            documents.c.user_id == user_id, documents.c.status.in_(["uploaded", "failed", "ready"]))
            .values(status="extracting", error="", updated_at=now())).rowcount
        if changed:
            conn.execute(insert(document_processing).values(id=attempt_id,
                user_id=user_id, document_id=document_id, status="extracting",
                duration_ms=None, created_at=now()))
    if not changed:
        raise ValueError("Tài liệu chưa sẵn sàng để xử lý.")
    try:
        data = get_storage().get(document["storage_key"])
        result = extract_text(document["filename"], data)
        with get_db().engine.begin() as conn:
            # Reprocessing can change extracted evidence; old citations and cached AI
            # answers must not be served against the new chunks.
            if document["status"] == "ready":
                conversations = select(ai_conversations.c.id).where(
                    ai_conversations.c.user_id == user_id,
                    ai_conversations.c.document_id == document_id)
                conn.execute(delete(ai_messages).where(ai_messages.c.conversation_id.in_(conversations)))
                conn.execute(delete(ai_conversations).where(ai_conversations.c.user_id == user_id,
                    ai_conversations.c.document_id == document_id))
                conn.execute(delete(document_analyses).where(document_analyses.c.user_id == user_id,
                    or_(document_analyses.c.document_id == document_id,
                        document_analyses.c.related_document_id == document_id)))
            conn.execute(delete(document_text).where(document_text.c.document_id == document_id))
            for chunk in result.chunks:
                conn.execute(insert(document_text).values(
                    id=_id(), document_id=document_id, source_id=chunk["source_id"],
                    label=chunk["label"],
                    page_number=chunk.get("page_number"), section=chunk.get("section"),
                    sheet_name=chunk.get("sheet_name"), row_start=chunk.get("row_start"),
                    row_end=chunk.get("row_end"), text=chunk["text"], created_at=now()))
            conn.execute(update(documents).where(documents.c.id == document_id,
                documents.c.user_id == user_id).values(status="ready",
                    scan_likely=result.scan_likely, error="", updated_at=now()))
            conn.execute(update(document_processing).where(document_processing.c.id == attempt_id)
                .values(status="completed", duration_ms=int((time.monotonic() - started) * 1000)))
    except Exception as exc:
        logging.exception("Document extraction failed for %s", document_id)
        with get_db().engine.begin() as conn:
            conn.execute(update(documents).where(documents.c.id == document_id,
                documents.c.user_id == user_id).values(status="failed",
                    error=str(exc)[:300], updated_at=now()))
            conn.execute(update(document_processing).where(document_processing.c.id == attempt_id)
                .values(status="failed", duration_ms=int((time.monotonic() - started) * 1000)))
        raise
    return _public(document_for_user(user_id, document_id))


def process_pending_documents(limit: int = 3) -> dict:
    with get_db().engine.connect() as conn:
        pending = conn.execute(select(documents.c.user_id, documents.c.id)
            .where(documents.c.status == "uploaded")
            .order_by(documents.c.created_at).limit(max(1, min(limit, 10)))).all()
    complete = failed = 0
    for user_id, document_id in pending:
        try:
            process_document(user_id, document_id)
            complete += 1
        except Exception:
            failed += 1
    return {"status": "done", "processed": complete, "failed": failed}


def link_document(user_id: str, document_id: str, tender_code: str) -> dict:
    document = document_for_user(user_id, document_id)
    if not document:
        raise LookupError("Không tìm thấy tài liệu.")
    code = str(tender_code or "").strip().upper()
    if code and not re.fullmatch(r"(?:IB|PL)[A-Z0-9-]{4,40}", code):
        raise ValueError("Mã TBMT/KHLCNT không hợp lệ.")
    with get_db().engine.begin() as conn:
        conn.execute(update(documents).where(documents.c.id == document_id,
            documents.c.user_id == user_id).values(tender_code=code or None, updated_at=now()))
    return _public(document_for_user(user_id, document_id))


def delete_document(user_id: str, document_id: str) -> bool:
    document = document_for_user(user_id, document_id)
    if not document:
        return False
    # Delete the private object first; a failed storage delete leaves DB history intact for retry.
    get_storage().delete(document["storage_key"])
    with get_db().engine.begin() as conn:
        conversations = select(ai_conversations.c.id).where(ai_conversations.c.user_id == user_id,
                                                             ai_conversations.c.document_id == document_id)
        conn.execute(delete(ai_messages).where(ai_messages.c.conversation_id.in_(conversations)))
        conn.execute(delete(ai_conversations).where(ai_conversations.c.user_id == user_id,
                                                     ai_conversations.c.document_id == document_id))
        conn.execute(delete(document_analyses).where(document_analyses.c.user_id == user_id,
            or_(document_analyses.c.document_id == document_id,
                document_analyses.c.related_document_id == document_id)))
        conn.execute(delete(document_processing).where(document_processing.c.user_id == user_id,
            document_processing.c.document_id == document_id))
        conn.execute(delete(document_text).where(document_text.c.document_id == document_id))
        conn.execute(delete(documents).where(documents.c.id == document_id,
                                             documents.c.user_id == user_id))
    return True


def download_document(user_id: str, document_id: str) -> tuple[bytes, str, str] | None:
    document = document_for_user(user_id, document_id)
    if not document:
        return None
    return get_storage().get(document["storage_key"]), document["filename"], document["mime_type"]
