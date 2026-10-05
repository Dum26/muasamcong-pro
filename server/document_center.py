"""Unified, read-only catalog over private uploads and e-GP document metadata."""
from __future__ import annotations

import difflib
import io
import re

from sqlalchemy import exists, func, insert, literal, or_, select, union_all, update
from sqlalchemy.exc import IntegrityError

from server.database import (document_text, document_versions, documents, get_db,
                             source_document_text, tender_source_documents, tenders,
                             user_document_state, document_analyses, now)
from server.document_service import document_for_user


def catalog(user_id: str, *, page: int = 1, page_size: int = 25,
            query: str = "", source: str = "all", tender_code: str = "",
            plan_code: str = "", document_type: str = "", status: str = "",
            sort: str = "updated") -> dict:
    page = max(1, min(int(page), 100_000))
    page_size = max(1, min(int(page_size), 100))
    if source not in {"all", "upload", "egp"}:
        raise ValueError("Nguồn tài liệu không hợp lệ.")
    if sort not in {"updated", "name", "size"}:
        raise ValueError("Cách sắp xếp không hợp lệ.")
    query = str(query or "").strip()[:120]
    tender_code = str(tender_code or "").strip().upper()[:50]
    plan_code = str(plan_code or "").strip().upper()[:50]
    document_type = str(document_type or "").strip().lower()[:80]
    status = str(status or "").strip()[:24]
    private = select(
        documents.c.id.label("id"), literal("upload").label("source"),
        documents.c.filename.label("name"), documents.c.mime_type.label("type"),
        documents.c.tender_code.label("tender_code"),
        tenders.c.khlcnt_code.label("khlcnt_code"), tenders.c.title.label("tender_title"),
        documents.c.size.label("size"), documents.c.status.label("status"),
        literal(1).label("version"), documents.c.created_at.label("discovered_at"),
        documents.c.updated_at.label("updated_at"), literal("").label("source_url"),
        literal("").label("document_group_id"),
        documents.c.sha256.label("content_hash"),
        literal(False).label("is_new"),
        exists(select(document_analyses.c.id).where(
            document_analyses.c.document_id == documents.c.id,
            document_analyses.c.user_id == user_id,
            document_analyses.c.status == "completed")).label("ai_analyzed"),
    ).select_from(documents.outerjoin(tenders, documents.c.tender_code == tenders.c.tender_code))
    private_conditions = [documents.c.user_id == user_id]
    if tender_code:
        private_conditions.append(documents.c.tender_code == tender_code)
    if plan_code:
        private_conditions.append(tenders.c.khlcnt_code == plan_code)
    if document_type:
        private_conditions.append(func.lower(documents.c.mime_type).like(f"%{document_type}%"))
    if status:
        private_conditions.append(documents.c.status == status)
    if query:
        pattern = f"%{query.lower()}%"
        private_conditions.append(or_(
            func.lower(documents.c.filename).like(pattern),
            func.lower(documents.c.tender_code).like(pattern),
            func.lower(tenders.c.title).like(pattern),
            exists(select(document_text.c.id).where(
                document_text.c.document_id == documents.c.id,
                func.lower(document_text.c.text).like(pattern))),
        ))
    private = private.where(*private_conditions)

    public = select(
        tender_source_documents.c.id.label("id"), literal("egp").label("source"),
        tender_source_documents.c.document_name.label("name"),
        tender_source_documents.c.document_type.label("type"),
        tender_source_documents.c.tender_code.label("tender_code"),
        tenders.c.khlcnt_code.label("khlcnt_code"), tenders.c.title.label("tender_title"),
        tender_source_documents.c.file_size.label("size"),
        tender_source_documents.c.status.label("status"),
        tender_source_documents.c.version.label("version"),
        tender_source_documents.c.first_seen_at.label("discovered_at"),
        tender_source_documents.c.last_seen_at.label("updated_at"),
        tender_source_documents.c.source_url.label("source_url"),
        tender_source_documents.c.document_group_id.label("document_group_id"),
        tender_source_documents.c.content_hash.label("content_hash"),
        (~exists(select(user_document_state.c.document_id).where(
            user_document_state.c.user_id == user_id,
            user_document_state.c.document_id == tender_source_documents.c.id,
            user_document_state.c.last_viewed_at >= select(document_versions.c.created_at)
                .where(document_versions.c.document_group_id == tender_source_documents.c.document_group_id,
                       document_versions.c.source_url == tender_source_documents.c.source_url,
                       document_versions.c.version == tender_source_documents.c.version)
                .scalar_subquery()))).label("is_new"),
        literal(False).label("ai_analyzed"),
    ).select_from(tender_source_documents.join(
        tenders, tender_source_documents.c.tender_code == tenders.c.tender_code))
    public_conditions = []
    if tender_code:
        public_conditions.append(tender_source_documents.c.tender_code == tender_code)
    if plan_code:
        public_conditions.append(tenders.c.khlcnt_code == plan_code)
    if document_type:
        public_conditions.append(func.lower(tender_source_documents.c.document_type).like(f"%{document_type}%"))
    if status:
        public_conditions.append(tender_source_documents.c.status == status)
    if query:
        public_conditions.append(or_(
            func.lower(tender_source_documents.c.document_name).like(pattern),
            func.lower(tender_source_documents.c.document_type).like(pattern),
            func.lower(tender_source_documents.c.tender_code).like(pattern),
            func.lower(tenders.c.khlcnt_code).like(pattern),
            func.lower(tenders.c.investor_name).like(pattern),
            func.lower(tenders.c.title).like(pattern),
            exists(select(source_document_text.c.id).select_from(
                source_document_text.join(document_versions,
                    source_document_text.c.version_id == document_versions.c.id))
                .where(document_versions.c.document_group_id == tender_source_documents.c.document_group_id,
                       document_versions.c.source_url == tender_source_documents.c.source_url,
                       document_versions.c.version == tender_source_documents.c.version,
                       func.lower(source_document_text.c.text).like(pattern)))))
    public = public.where(*public_conditions)
    selections = [private] if source == "upload" else [public] if source == "egp" else [private, public]
    combined = union_all(*selections).subquery() if len(selections) > 1 else selections[0].subquery()
    order = {"updated": combined.c.updated_at.desc(),
             "name": combined.c.name.asc(), "size": combined.c.size.desc()}[sort]
    with get_db().engine.connect() as conn:
        total = conn.scalar(select(func.count()).select_from(combined)) or 0
        rows = conn.execute(select(combined).order_by(order, combined.c.id)
            .offset((page - 1) * page_size).limit(page_size)).mappings().all()
        items = [dict(row) for row in rows]
        if query:
            pattern = f"%{query.lower()}%"
            private_ids = [item["id"] for item in items if item["source"] == "upload"]
            private_matches = {}
            if private_ids:
                ranked = select(document_text.c.document_id.label("document_id"),
                    document_text.c.text.label("text"), document_text.c.label.label("label"),
                    func.row_number().over(partition_by=document_text.c.document_id,
                        order_by=document_text.c.id).label("rank")).where(
                    document_text.c.document_id.in_(private_ids),
                    func.lower(document_text.c.text).like(pattern)).subquery()
                private_matches = {row.document_id: row for row in conn.execute(
                    select(ranked).where(ranked.c.rank == 1))}
            public_items = [item for item in items if item["source"] == "egp"]
            public_matches = {}
            if public_items:
                groups = {item["document_group_id"] for item in public_items}
                ranked = select(document_versions.c.document_group_id.label("group_id"),
                    document_versions.c.source_url.label("source_url"),
                    document_versions.c.version.label("version"),
                    source_document_text.c.text.label("text"),
                    source_document_text.c.label.label("label"),
                    func.row_number().over(partition_by=(document_versions.c.document_group_id,
                        document_versions.c.source_url, document_versions.c.version),
                        order_by=source_document_text.c.id).label("rank")
                    ).select_from(source_document_text.join(document_versions,
                        source_document_text.c.version_id == document_versions.c.id)).where(
                    document_versions.c.document_group_id.in_(groups),
                    func.lower(source_document_text.c.text).like(pattern)).subquery()
                public_matches = {(row.group_id, row.source_url, row.version): row
                    for row in conn.execute(select(ranked).where(ranked.c.rank == 1))}
            for item in items:
                match = (private_matches.get(item["id"]) if item["source"] == "upload" else
                    public_matches.get((item["document_group_id"], item["source_url"], item["version"])))
                if match:
                    text_value, label = match.text, match.label
                    position = text_value.lower().find(query.lower())
                    start = max(0, position - 70)
                    item["snippet"] = ("…" if start else "") + text_value[start:start + 220] + (
                        "…" if start + 220 < len(text_value) else "")
                    item["citation"] = label
    return {"items": items, "total": total,
            "page": page, "page_size": page_size, "has_more": page * page_size < total}


def detail(user_id: str, source: str, document_id: str) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{32}", document_id):
        return None
    if source == "upload":
        document = document_for_user(user_id, document_id)
        if not document:
            return None
        with get_db().engine.connect() as conn:
            chunks = conn.execute(select(document_text.c.source_id,
                document_text.c.label, document_text.c.text)
                .where(document_text.c.document_id == document_id)
                .order_by(document_text.c.source_id).limit(80)).mappings().all()
        return {"source": "upload", "document": {key: document[key] for key in (
            "id", "filename", "tender_code", "mime_type", "size", "status", "created_at", "updated_at")},
            "chunks": [dict(row) for row in chunks], "versions": []}
    if source != "egp":
        return None
    with get_db().engine.connect() as conn:
        row = conn.execute(select(tender_source_documents).where(
            tender_source_documents.c.id == document_id)).mappings().first()
        if not row:
            return None
        versions = conn.execute(select(document_versions.c.id, document_versions.c.version,
            document_versions.c.created_at, document_versions.c.source_url,
            document_versions.c.content_hash, document_versions.c.metadata_hash)
            .where(document_versions.c.document_group_id == row["document_group_id"],
                   document_versions.c.source_url == row["source_url"])
            .order_by(document_versions.c.version.desc()).limit(50)).mappings().all()
        current = next((item for item in versions if item["version"] == row["version"]), None)
        chunks = conn.execute(select(source_document_text.c.source_id,
            source_document_text.c.label, source_document_text.c.text)
            .where(source_document_text.c.version_id == current["id"])
            .order_by(source_document_text.c.source_id).limit(80)).mappings().all() if current else []
    safe = {key: row[key] for key in row.keys() if key not in {"storage_key", "error"}}
    safe["has_file"] = bool(row["storage_key"])
    try:
        with get_db().engine.begin() as conn:
            changed = conn.execute(update(user_document_state).where(
                user_document_state.c.user_id == user_id,
                user_document_state.c.document_id == document_id).values(
                last_viewed_at=now(), is_read=True)).rowcount
            if not changed:
                conn.execute(insert(user_document_state).values(user_id=user_id,
                    document_id=document_id, last_viewed_at=now(), is_read=True))
    except IntegrityError:
        # Concurrent detail requests raced to insert the same read marker.
        pass
    return {"source": "egp", "document": safe, "chunks": [dict(item) for item in chunks],
            "versions": [dict(item) for item in versions]}


def compare_uploaded(user_id: str, first_id: str, second_id: str) -> dict:
    first = document_for_user(user_id, first_id)
    second = document_for_user(user_id, second_id)
    if not first or not second:
        raise LookupError("Không tìm thấy tài liệu.")
    if first["status"] != "ready" or second["status"] != "ready":
        raise ValueError("Cần xử lý văn bản của cả hai tài liệu trước khi so sánh.")
    with get_db().engine.connect() as conn:
        def lines(document_id):
            return [row for row in conn.execute(select(document_text.c.text)
                .where(document_text.c.document_id == document_id)
                .order_by(document_text.c.source_id)).scalars()]
        before, after = lines(first_id), lines(second_id)
    # Bound output for large documents; never interpolate raw text as HTML.
    diff = list(difflib.unified_diff(before[:300], after[:300],
        fromfile=first["filename"], tofile=second["filename"], lineterm=""))[:400]
    return {"first_id": first_id, "second_id": second_id, "lines": diff,
            "truncated": len(before) > 300 or len(after) > 300}


def export_metadata(user_id: str, **filters) -> bytes:
    from openpyxl import Workbook
    from server.document_export import _safe
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Tài liệu")
    sheet.append(["Tên tài liệu", "Loại", "TBMT", "KHLCNT", "Tên gói", "Nguồn",
                  "Phiên bản", "Phát hiện", "Cập nhật", "Dung lượng", "Trạng thái", "URL nguồn"])
    for page in range(1, 51):  # at most 5,000 rows per explicit export
        result = catalog(user_id, page=page, page_size=100, **filters)
        for item in result["items"]:
            sheet.append([_safe(item["name"]), _safe(item["type"]), _safe(item["tender_code"]),
                _safe(item["khlcnt_code"]), _safe(item["tender_title"]), item["source"],
                item["version"], item["discovered_at"], item["updated_at"],
                item["size"], item["status"], _safe(item["source_url"])])
        if not result["has_more"]:
            break
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
