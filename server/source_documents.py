"""Explicit e-GP file retrieval and extraction; metadata sync never fetches bytes."""
from __future__ import annotations

import hashlib
import difflib
import base64
import uuid
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, insert, select, update, func

from server.config import max_document_download_bytes, max_upload_bytes
from server.database import (audit_logs, document_notification_seen, document_versions,
    documents, followed_tenders, get_db, now, source_document_text,
    tender_source_documents, user_notifications)
from server.document_extract import extract_text, validate_file
from server.document_storage import get_storage, source_object_key
from server.source.request_manager import get_request_manager


def _row(document_id: str) -> dict | None:
    if len(document_id) != 32 or any(char not in "0123456789abcdef" for char in document_id):
        return None
    with get_db().engine.connect() as conn:
        item = conn.execute(select(tender_source_documents).where(
            tender_source_documents.c.id == document_id)).mappings().first()
    return dict(item) if item else None


def _version(conn, row: dict) -> dict:
    item = conn.execute(select(document_versions).where(
        document_versions.c.document_group_id == row["document_group_id"],
        document_versions.c.source_url == row["source_url"],
        document_versions.c.version == row["version"])).mappings().first()
    if not item:
        raise LookupError("Không tìm thấy phiên bản tài liệu.")
    return dict(item)


def fetch_source_document(user_id: str, document_id: str, *, force: bool = False) -> dict:
    row = _row(document_id)
    if not row:
        raise LookupError("Không tìm thấy tài liệu nguồn.")
    if row["storage_key"] and not force:
        return {"status": row["status"], "version": row["version"],
                "content_hash": row["content_hash"], "cached": True}
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with get_db().engine.begin() as conn:
        claimed = conn.execute(update(tender_source_documents).where(
            tender_source_documents.c.id == document_id,
            (tender_source_documents.c.status != "downloading") |
            (tender_source_documents.c.last_seen_at < stale_cutoff))
            .values(status="downloading", error=None, last_seen_at=now())).rowcount
    if not claimed:
        # Another worker (possibly on another Cloud Run instance) owns this
        # fetch. Poll the shared DB rather than hitting e-GP again.
        for _ in range(40):
            time.sleep(.25)
            current = _row(document_id)
            if current and current["status"] != "downloading":
                if current["storage_key"]:
                    return {"status": current["status"], "version": current["version"],
                            "content_hash": current["content_hash"], "cached": True}
                raise ValueError(current["error"] or "Tải tài liệu nguồn thất bại.")
        raise TimeoutError("Tài liệu đang được tải; vui lòng thử lại.")
    try:
        data, declared = get_request_manager().request_binary(row["source_url"],
            max_bytes=max_document_download_bytes())
        filename, mime = validate_file(row["document_name"], declared, data,
            max_bytes=max_document_download_bytes())
        digest = hashlib.sha256(data).hexdigest()
        with get_db().engine.connect() as conn:
            current_version = _version(conn, row)
            maximum_version = conn.scalar(select(func.max(document_versions.c.version)).where(
                document_versions.c.document_group_id == row["document_group_id"])) or row["version"]
            prior_same = conn.execute(select(document_versions)
                .where(document_versions.c.document_group_id == row["document_group_id"],
                       document_versions.c.source_url == row["source_url"],
                       document_versions.c.content_hash == digest)
                .order_by(document_versions.c.version.desc()).limit(1)).mappings().first()
        # The same bytes are not a new version. A changed hash is, even if
        # the source kept the URL and filename unchanged.
        creating = bool(current_version["content_hash"] and
            current_version["content_hash"] != digest and not prior_same)
        new_version = (prior_same["version"] if prior_same else
            maximum_version + 1 if creating else row["version"])
        key = (prior_same["storage_key"] if prior_same and prior_same["storage_key"]
               else source_object_key(document_id, new_version))
        if not (prior_same and prior_same["storage_key"]) and not (
                row["storage_key"] == key and row["content_hash"] == digest):
            get_storage().put(key, data, mime)
        stamp = now()
        with get_db().engine.begin() as conn:
            if creating:
                conn.execute(insert(document_versions).values(id=uuid.uuid4().hex,
                    document_group_id=row["document_group_id"], version=new_version,
                    storage_key=key, source_url=row["source_url"], content_hash=digest,
                    metadata_hash=row["metadata_hash"],
                    metadata_json={"document_name": filename,
                        "document_type": row["document_type"],
                        "published_at": row["published_at"],
                        "file_size": len(data), "source_url": row["source_url"]},
                    created_at=stamp))
            elif not (prior_same and prior_same["storage_key"]):
                conn.execute(update(document_versions).where(
                    document_versions.c.document_group_id == row["document_group_id"],
                    document_versions.c.version == new_version).values(
                    storage_key=key, content_hash=digest))
            conn.execute(update(tender_source_documents).where(
                tender_source_documents.c.id == document_id).values(
                document_name=filename, file_size=len(data), mime_type=mime,
                content_hash=digest, storage_key=key, version=new_version,
                status="downloaded", error=None, downloaded_at=stamp,
                last_seen_at=stamp))
            conn.execute(insert(audit_logs).values(id=uuid.uuid4().hex,
                user_id=user_id, action="document_fetch", entity_type="source_document",
                entity_id=document_id, created_at=stamp))
            if creating:
                owners = conn.execute(select(followed_tenders.c.user_id).where(
                    followed_tenders.c.tender_code == row["tender_code"])).scalars().all()
                for owner in owners:
                    if conn.execute(select(document_notification_seen.c.user_id).where(
                            document_notification_seen.c.user_id == owner,
                            document_notification_seen.c.document_id == document_id,
                            document_notification_seen.c.version == new_version)).first():
                        continue
                    conn.execute(insert(document_notification_seen).values(user_id=owner,
                        document_id=document_id, version=new_version, created_at=stamp))
                    conn.execute(insert(user_notifications).values(id=uuid.uuid4().hex,
                        user_id=owner, type="document_changed", title="File nguồn có phiên bản mới",
                        message=f"{filename} · {row['tender_code']} · phiên bản {new_version}",
                        tender_code=row["tender_code"], is_read=False, created_at=stamp))
        return {"status": "downloaded", "version": new_version,
                "content_hash": digest, "cached": False}
    except Exception as exc:
        with get_db().engine.begin() as conn:
            conn.execute(update(tender_source_documents).where(
                tender_source_documents.c.id == document_id).values(
                status="failed", error=str(exc)[:300]))
        raise


def cached_source_file(document_id: str) -> tuple[bytes, str, str] | None:
    row = _row(document_id)
    if not row or not row["storage_key"]:
        return None
    return get_storage().get(row["storage_key"]), row["document_name"], row["mime_type"]


def extract_source_document(user_id: str, document_id: str) -> dict:
    row = _row(document_id)
    if not row:
        raise LookupError("Không tìm thấy tài liệu nguồn.")
    if not row["storage_key"]:
        raise ValueError("Cần tải file nguồn trước khi trích xuất.")
    with get_db().engine.begin() as conn:
        version = _version(conn, row)
        if conn.scalar(select(func.count()).select_from(source_document_text).where(
                source_document_text.c.version_id == version["id"])):
            return {"status": "ready", "version": row["version"], "cached": True}
        conn.execute(update(tender_source_documents).where(
            tender_source_documents.c.id == document_id).values(status="extracting", error=None))
    try:
        result = extract_text(row["document_name"], get_storage().get(row["storage_key"]))
        with get_db().engine.begin() as conn:
            conn.execute(delete(source_document_text).where(
                source_document_text.c.version_id == version["id"]))
            for chunk in result.chunks:
                conn.execute(insert(source_document_text).values(id=uuid.uuid4().hex,
                    version_id=version["id"], source_id=chunk["source_id"],
                    label=chunk["label"], page_number=chunk.get("page_number"),
                    section=chunk.get("section"), sheet_name=chunk.get("sheet_name"),
                    row_start=chunk.get("row_start"), row_end=chunk.get("row_end"),
                    text=chunk["text"], text_hash=hashlib.sha256(chunk["text"].encode()).hexdigest(),
                    created_at=now()))
            conn.execute(update(tender_source_documents).where(
                tender_source_documents.c.id == document_id).values(status="ready", error=None))
            conn.execute(insert(audit_logs).values(id=uuid.uuid4().hex,
                user_id=user_id, action="document_extract", entity_type="source_document",
                entity_id=document_id, created_at=now()))
        return {"status": "ready", "version": row["version"],
                "chunks": len(result.chunks), "scan_likely": result.scan_likely,
                "cached": False}
    except Exception as exc:
        with get_db().engine.begin() as conn:
            conn.execute(update(tender_source_documents).where(
                tender_source_documents.c.id == document_id).values(
                status="failed", error=str(exc)[:300]))
        raise


def compare_source_versions(user_id: str, document_id: str, first: int, second: int) -> dict:
    row = _row(document_id)
    if not row:
        raise LookupError("Không tìm thấy tài liệu nguồn.")
    if first == second or not 1 <= first <= 1_000_000 or not 1 <= second <= 1_000_000:
        raise ValueError("Cần chọn hai phiên bản khác nhau.")
    with get_db().engine.begin() as conn:
        versions = conn.execute(select(document_versions).where(
            document_versions.c.document_group_id == row["document_group_id"],
            document_versions.c.source_url == row["source_url"],
            document_versions.c.version.in_([first, second]))).mappings().all()
        by_number = {item["version"]: item for item in versions}
        if first not in by_number or second not in by_number:
            raise LookupError("Không tìm thấy phiên bản tài liệu.")
        texts = {}
        for number in (first, second):
            texts[number] = conn.execute(select(source_document_text.c.text).where(
                source_document_text.c.version_id == by_number[number]["id"])
                .order_by(source_document_text.c.source_id).limit(301)).scalars().all()
        conn.execute(insert(audit_logs).values(id=uuid.uuid4().hex,
            user_id=user_id, action="document_compare", entity_type="source_document",
            entity_id=document_id, created_at=now()))
    fields = ("document_name", "document_type", "published_at", "file_size", "source_url")
    old_meta = by_number[first]["metadata_json"] or {}
    new_meta = by_number[second]["metadata_json"] or {}
    changes = [{"field": field, "before": old_meta.get(field), "after": new_meta.get(field)}
               for field in fields if field in old_meta and field in new_meta
               and old_meta[field] != new_meta[field]]
    raw_diff = list(difflib.unified_diff(texts[first][:300], texts[second][:300],
        fromfile=f"v{first}", tofile=f"v{second}", lineterm=""))[:400] \
        if texts[first] and texts[second] else []
    return {"first": first, "second": second, "metadata_changes": changes,
            "text_diff": raw_diff, "text_available": bool(texts[first] and texts[second]),
            "truncated": len(texts[first]) > 300 or len(texts[second]) > 300}


def import_source_for_ai(user_id: str, document_id: str) -> dict:
    """Explicitly copy a cached public file into the caller's private AI workspace."""
    from server.document_service import process_document, upload_document
    row = _row(document_id)
    if not row:
        raise LookupError("Không tìm thấy tài liệu nguồn.")
    file = cached_source_file(document_id)
    if not file:
        raise ValueError("Hãy tải file nguồn trước khi phân tích AI.")
    data, filename, mime = file
    if len(data) > max_upload_bytes():
        raise ValueError("File vượt giới hạn hồ sơ AI. Bạn vẫn có thể tải và xem file nguồn.")
    digest = hashlib.sha256(data).hexdigest()
    with get_db().engine.connect() as conn:
        prior = conn.execute(select(documents.c.id, documents.c.status).where(
            documents.c.user_id == user_id, documents.c.tender_code == row["tender_code"],
            documents.c.sha256 == digest).limit(1)).first()
    if prior:
        if prior.status in {"uploaded", "failed"}:
            process_document(user_id, prior.id)
        return {"document_id": prior.id, "cached": True}
    item = upload_document(user_id, {"filename": filename, "mime_type": mime,
        "tender_code": row["tender_code"], "data": base64.b64encode(data).decode()})
    process_document(user_id, item["id"])
    return {"document_id": item["id"], "cached": False}
