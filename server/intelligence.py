"""Canonical public tender observations, snapshots and evidence-based analytics."""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable
from urllib.parse import urlparse

from sqlalchemy import Integer, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from server.config import source_settings
from server.database import (contractors, document_versions, document_notification_seen,
    followed_tenders, get_db, investors, now, user_notifications,
    plans, procuring_entities, tender_changes, tender_events, tender_snapshots,
    tender_source_documents, tenders)

TZ = timezone(timedelta(hours=7))
FIELDS = ("khlcnt_code", "title", "investor_name", "procuring_entity_name",
          "package_price", "currency", "publish_date", "bid_closing_date",
          "result_date", "status", "selection_method", "contract_type", "location",
          "result_status", "winning_contractor", "winning_price", "source_url")
CHANGE_FIELDS = ("title", "package_price", "bid_closing_date", "status", "investor_name",
                 "procuring_entity_name", "selection_method", "contract_type",
                 "result_status", "winning_contractor", "winning_price", "documents")
SORTS = {"published": tenders.c.publish_date, "deadline": tenders.c.bid_closing_date,
         "price": tenders.c.package_price, "updated": tenders.c.last_synced_at,
         "code": tenders.c.tender_code}


def _id() -> str:
    return uuid.uuid4().hex


def normalize_name(value: str) -> str:
    """Exact canonical spelling; never fuzzy-merge legally different entities."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).strip()).casefold()


def _search_text(*values) -> str:
    from server.search_engine import normalize_search
    return normalize_search(" ".join(str(value or "") for value in values))


def _clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_code(value: str, kind: str = "tender") -> str:
    code = str(value or "").strip().upper()
    if kind == "plan":
        code = "PL" + re.sub(r"^PL", "", code)
        return code if re.fullmatch(r"PL[0-9A-Z]{6,30}", code) else ""
    code = re.sub(r"-\d{2}$", "", code)
    return code if re.fullmatch(r"IB[0-9A-Z]{6,30}", code) else ""


def parse_money(value) -> Decimal | None:
    if isinstance(value, Decimal):
        return value if value >= 0 else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value)) if value >= 0 else None
    raw = str(value or "").strip().upper().replace("VND", "").replace("VNĐ", "").strip()
    if not raw or not re.fullmatch(r"[\d.,\s]+", raw):
        return None
    raw = raw.replace(" ", "")
    if "." in raw and "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "." in raw and all(len(group) == 3 for group in raw.split(".")[1:]):
        raw = raw.replace(".", "")
    elif "," in raw and all(len(group) == 3 for group in raw.split(",")[1:]):
        raw = raw.replace(",", "")
    else:
        raw = raw.replace(",", ".")
    try:
        result = Decimal(raw)
        return result if result >= 0 and result.is_finite() else None
    except InvalidOperation:
        return None


def iso_date(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.isoformat(timespec="seconds") if "%H" in fmt else parsed.date().isoformat()
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(TZ).replace(tzinfo=None)
        return parsed.isoformat(timespec="seconds") if "T" in raw or " " in raw else parsed.date().isoformat()
    except ValueError:
        return None


def _row_values(row) -> dict:
    if isinstance(row, dict):
        return row
    from dataclasses import asdict, is_dataclass
    return asdict(row) if is_dataclass(row) else dict(row)


def _entity(conn, table, name: str, stamp: str, tax_code: str = "") -> str | None:
    clean = re.sub(r"\s+", " ", str(name or "")).strip()
    key = normalize_name(clean)
    if not key:
        return None
    identity = ("tax:" + tax_code.strip() if tax_code.strip() else "name:" + key)
    column = table.c.identity_key if table is contractors else table.c.normalized_name
    lookup = identity if table is contractors else key
    existing = conn.execute(select(table.c.id).where(column == lookup)).scalar()
    if existing:
        from server.database import entity_merges
        kind = "contractor" if table is contractors else "investor" if table is investors else "procuring_entity"
        existing = conn.scalar(select(entity_merges.c.target_id).where(
            entity_merges.c.entity_type == kind, entity_merges.c.source_id == existing)) or existing
        conn.execute(update(table).where(table.c.id == existing).values(last_seen_at=stamp))
        return existing
    values = dict(id=_id(), name=clean[:320], normalized_name=key[:320],
                  search_text=_search_text(clean, tax_code),
                  first_seen_at=stamp, last_seen_at=stamp)
    if table is contractors:
        values.update(identity_key=identity[:380], tax_code=tax_code.strip() or None)
    conn.execute(insert(table).values(**values))
    return values["id"]


def _source_url(value: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlparse(raw)
        return raw if parsed.scheme == "https" and parsed.hostname == "muasamcong.mpi.gov.vn" \
            and not parsed.username and not parsed.password and parsed.port in (None, 443) else ""
    except ValueError:
        return ""


def discover_documents(record: dict | None) -> list[dict]:
    """Only accept explicit HTTPS links returned by e-GP, never invent file URLs."""
    if not isinstance(record, dict):
        return []
    found, seen = [], set()
    stack = [record]
    while stack and len(found) < 100:
        value = stack.pop()
        if isinstance(value, list):
            stack.extend(value[:200])
        elif isinstance(value, dict):
            raw_url = next((value.get(key) for key in ("fileUrl", "downloadUrl", "documentUrl", "attachmentUrl")
                            if isinstance(value.get(key), str)), "")
            url = _source_url(raw_url)
            name = next((value.get(key) for key in ("fileName", "documentName", "attachmentName", "name")
                         if isinstance(value.get(key), str)), "")
            if url and url not in seen and name:
                seen.add(url)
                found.append({"document_name": str(name)[:240],
                              "document_type": str(value.get("documentType") or value.get("type") or "")[:80],
                              "source_url": url,
                              "published_at": iso_date(value.get("publishedAt") or value.get("publicDate")),
                              "file_size": value.get("fileSize") if isinstance(value.get("fileSize"), int) else None})
            stack.extend(child for child in value.values() if isinstance(child, (dict, list)))
    return found


def _sync_documents(conn, code: str, items: list[dict], stamp: str,
                    *, complete: bool = False) -> None:
    def notify(document_id: str, version: int, name: str, changed: bool = False) -> None:
        owners = conn.execute(select(followed_tenders.c.user_id).where(
            followed_tenders.c.tender_code == code)).scalars().all()
        for owner in owners:
            seen = conn.execute(select(document_notification_seen.c.user_id).where(
                document_notification_seen.c.user_id == owner,
                document_notification_seen.c.document_id == document_id,
                document_notification_seen.c.version == version)).first()
            if seen:
                continue
            conn.execute(insert(document_notification_seen).values(user_id=owner,
                document_id=document_id, version=version, created_at=stamp))
            conn.execute(insert(user_notifications).values(id=_id(), user_id=owner,
                type="document_changed" if changed else "new_document",
                title="Tài liệu nguồn cập nhật" if changed else "Tài liệu mới cho gói đang theo dõi",
                message=f"{name} · {code} · phiên bản {version}",
                tender_code=code, is_read=False, created_at=stamp))

    observed_urls = set()
    for item in items:
        url = _source_url(item.get("source_url", ""))
        if not url:
            continue
        observed_urls.add(url)
        name = str(item.get("document_name") or "Tài liệu")[:240]
        kind = str(item.get("document_type") or "")[:80]
        published = iso_date(item.get("published_at"))
        size = item.get("file_size") if isinstance(item.get("file_size"), int) else None
        digest = hashlib.sha256(json.dumps([name, kind, published, size],
            ensure_ascii=False).encode()).hexdigest()
        metadata_value = {"document_name": name, "document_type": kind,
                          "published_at": published, "file_size": size, "source_url": url}
        existing = conn.execute(select(tender_source_documents).where(
            tender_source_documents.c.tender_code == code,
            tender_source_documents.c.source_url == url)).mappings().first()
        if existing:
            # A stable source URL may point at revised metadata. The first
            # observation of an older database is a baseline, not a revision.
            old_digest = existing["metadata_hash"]
            if old_digest and old_digest != digest:
                version = (conn.scalar(select(func.max(document_versions.c.version)).where(
                    document_versions.c.document_group_id == existing["document_group_id"])) or existing["version"]) + 1
                conn.execute(insert(document_versions).values(id=_id(),
                    document_group_id=existing["document_group_id"], version=version,
                    storage_key=None, source_url=url, content_hash=None,
                    metadata_hash=digest, metadata_json=metadata_value, created_at=stamp))
                conn.execute(update(tender_source_documents).where(
                    tender_source_documents.c.id == existing["id"]).values(
                    document_name=name, document_type=kind, published_at=published,
                    file_size=size, metadata_hash=digest, version=version,
                    content_hash=None, storage_key=None, mime_type=None,
                    status="metadata_only", error=None, last_seen_at=stamp))
                notify(existing["id"], version, name, changed=True)
                continue
            conn.execute(update(tender_source_documents).where(
                tender_source_documents.c.id == existing["id"]).values(
                last_seen_at=stamp, metadata_hash=digest,
                status="metadata_only" if existing["status"] == "deleted_at_source" else existing["status"]))
            continue
        # A tender may publish several files of the same type. The source URL
        # identifies one file across metadata revisions; type/name do not.
        group = hashlib.sha256((code + "|" + url).encode()).hexdigest()[:32]
        version = (conn.scalar(select(func.max(document_versions.c.version)).where(
            document_versions.c.document_group_id == group)) or 0) + 1
        document_id = _id()
        conn.execute(insert(tender_source_documents).values(id=document_id, tender_code=code,
            document_name=name,
            document_type=kind, source_url=url,
            published_at=published, file_size=size,
            content_hash=None, metadata_hash=digest, document_group_id=group, version=version,
            first_seen_at=stamp, last_seen_at=stamp))
        conn.execute(insert(document_versions).values(id=_id(), document_group_id=group,
            version=version, storage_key=None, source_url=url, content_hash=None,
            metadata_hash=digest, metadata_json=metadata_value,
            created_at=stamp))
        notify(document_id, version, name)
    if complete:
        conditions = [tender_source_documents.c.tender_code == code,
            tender_source_documents.c.status != "deleted_at_source"]
        if observed_urls:
            conditions.append(tender_source_documents.c.source_url.not_in(observed_urls))
        conn.execute(update(tender_source_documents).where(*conditions).values(
            status="deleted_at_source", last_seen_at=stamp))


def _snapshot(conn, code: str, values: dict, stamp: str) -> tuple[bool, list[dict]]:
    docs = conn.execute(select(tender_source_documents.c.source_url,
        tender_source_documents.c.document_name, tender_source_documents.c.version)
        .where(tender_source_documents.c.tender_code == code)
        .order_by(tender_source_documents.c.document_group_id,
                  tender_source_documents.c.version)).all()
    snapshot = {key: str(values[key]) if isinstance(values.get(key), Decimal) else values.get(key)
                for key in FIELDS}
    snapshot["documents"] = [dict(url=url, name=name, version=version)
                             for url, name, version in docs]
    digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    previous = conn.execute(select(tender_snapshots.c.snapshot_json,
        tender_snapshots.c.snapshot_hash, tender_snapshots.c.version)
        .where(tender_snapshots.c.tender_code == code)
        .order_by(tender_snapshots.c.version.desc())
        .limit(1)).first()
    if previous and previous.snapshot_hash == digest:
        return False, []
    changes = []
    if previous:
        for field in CHANGE_FIELDS:
            old, new = previous.snapshot_json.get(field), snapshot.get(field)
            if old != new:
                changes.append({"field_name": field, "old_value": old,
                                "new_value": new, "detected_at": stamp})
                conn.execute(insert(tender_changes).values(id=_id(), tender_code=code,
                    field_name=field, old_value=old, new_value=new, detected_at=stamp))
    conn.execute(insert(tender_snapshots).values(id=_id(), tender_code=code,
        snapshot_json=snapshot, snapshot_hash=digest,
        version=(previous.version if previous else 0) + 1, created_at=stamp))
    return True, changes


def _event(conn, code: str, kind: str, label: str, when: str | None,
           details: dict | None = None) -> None:
    if not when:
        return
    exists = conn.execute(select(tender_events.c.id).where(
        tender_events.c.tender_code == code, tender_events.c.event_type == kind,
        tender_events.c.event_at == when)).scalar()
    if not exists:
        conn.execute(insert(tender_events).values(id=_id(), tender_code=code,
            event_type=kind, label=label, event_at=when, details=details or {}, created_at=now()))


def ingest_row(row, *, source_record: dict | None = None, synced: bool = True) -> dict | None:
    """Merge a real search/detail observation without erasing richer known fields."""
    raw = _row_values(row)
    code = clean_code(raw.get("notify_no"))
    plan_code = clean_code(raw.get("plan_no") or raw.get("plan_reference"), "plan")
    if not code and not plan_code:
        return None
    stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    docs = discover_documents(source_record)
    for attempt in range(2):
        try:
            with get_db().engine.begin() as conn:
                investor_id = _entity(conn, investors, raw.get("investor_name", ""), stamp)
                if plan_code:
                    prior_plan = conn.execute(select(plans).where(plans.c.plan_code == plan_code)).mappings().first()
                    plan_values = {"title": _clean_text(raw.get("plan_name")),
                                   "search_text": _search_text(raw.get("plan_name"), raw.get("investor_name")),
                                   "investor_id": investor_id,
                                   "investor_name": _clean_text(raw.get("investor_name")) or None,
                                   "publish_date": iso_date(raw.get("public_date")),
                                   "source_url": _source_url(raw.get("source_url", "")) or None,
                                   "last_seen_at": stamp}
                    if prior_plan:
                        conn.execute(update(plans).where(plans.c.plan_code == plan_code).values(
                            **{key: value for key, value in plan_values.items() if value is not None and value != ""}))
                    else:
                        conn.execute(insert(plans).values(plan_code=plan_code,
                            first_seen_at=stamp, **plan_values))
                if not code:
                    return {"plan_code": plan_code, "changed": False}
                procuring_id = _entity(conn, procuring_entities,
                                       raw.get("procuring_entity_name", ""), stamp)
                contractor_id = _entity(conn, contractors, raw.get("winner", ""), stamp)
                existing = conn.execute(select(tenders).where(tenders.c.tender_code == code)).mappings().first()
                price = parse_money(raw.get("package_price"))
                winning_price = parse_money(raw.get("winning_price"))
                incoming = {"khlcnt_code": plan_code or None,
                    "title": _clean_text(raw.get("package_name") or raw.get("plan_name")),
                    "search_text": _search_text(raw.get("package_name") or raw.get("plan_name"),
                        raw.get("investor_name"), raw.get("procuring_entity_name"),
                        raw.get("winner"), raw.get("location")),
                    "investor_id": investor_id, "investor_name": _clean_text(raw.get("investor_name")) or None,
                    "procuring_entity_id": procuring_id,
                    "procuring_entity_name": _clean_text(raw.get("procuring_entity_name")) or None,
                    "contractor_id": contractor_id,
                    "winning_contractor": _clean_text(raw.get("winner")) or None,
                    "package_price": price, "winning_price": winning_price,
                    "currency": "VND" if price is not None or winning_price is not None else None,
                    "publish_date": iso_date(raw.get("public_date")),
                    "bid_closing_date": iso_date(raw.get("bid_close_date")),
                    "result_date": iso_date(raw.get("decision_date")),
                    "status": str(raw.get("tender_status") or "") or None,
                    "selection_method": str(raw.get("bid_form") or "") or None,
                    "contract_type": str(raw.get("contract_type") or "") or None,
                    "location": str(raw.get("location") or "") or None,
                    "result_status": str(raw.get("result_status") or "") or None,
                    "source_url": _source_url(raw.get("source_url", "")) or None,
                    "last_seen_at": stamp, "sync_error": None,
                    "last_success_at": stamp if synced else None,
                    "sync_status": "fresh" if synced else "stale",
                    "sync_error_code": None}
                if existing:
                    values = {key: (incoming[key] if incoming.get(key) not in (None, "") else existing[key])
                              for key in incoming}
                    values["last_seen_at"] = stamp
                    values["last_synced_at"] = stamp if synced else existing["last_synced_at"]
                    values["last_success_at"] = stamp if synced else existing["last_success_at"]
                    conn.execute(update(tenders).where(tenders.c.tender_code == code).values(**values))
                else:
                    values = {**incoming, "first_seen_at": stamp,
                              "last_synced_at": stamp if synced else None, "raw_hash": None}
                    conn.execute(insert(tenders).values(tender_code=code, **values))
                detail = source_record.get("detail") if isinstance(source_record, dict) else None
                complete_docs = isinstance(detail, dict) and any(
                    isinstance(detail.get(key), list) for key in ("documents", "attachments"))
                _sync_documents(conn, code, docs, stamp, complete=complete_docs)
                changed, changes = _snapshot(conn, code, values, stamp)
                if changed:
                    digest = conn.execute(select(tender_snapshots.c.snapshot_hash).where(
                        tender_snapshots.c.tender_code == code).order_by(
                        tender_snapshots.c.version.desc())
                        .limit(1)).scalar()
                    conn.execute(update(tenders).where(tenders.c.tender_code == code)
                        .values(raw_hash=digest))
                _event(conn, code, "published", "Đăng TBMT", values.get("publish_date"))
                _event(conn, code, "deadline", "Hạn đóng thầu", values.get("bid_closing_date"))
                if values.get("winning_contractor") and values.get("result_date"):
                    _event(conn, code, "result", "Có KQLCNT", values["result_date"])
                for change in changes:
                    label = "Gia hạn/đổi hạn đóng thầu" if change["field_name"] == "bid_closing_date" else "Cập nhật " + change["field_name"]
                    _event(conn, code, "change:" + change["field_name"], label, stamp,
                           {"old": change["old_value"], "new": change["new_value"]})
                from server.search_engine import invalidate_search_cache
                invalidate_search_cache()
                return {"tender_code": code, "changed": changed, "changes": changes}
        except IntegrityError:
            if attempt:
                raise
    return None


def ingest_rows(rows: Iterable) -> dict:
    seen, changed, plans_seen = set(), 0, 0
    for row in rows:
        result = ingest_row(row)
        if result and result.get("tender_code"):
            seen.add(result["tender_code"])
            changed += int(result["changed"])
        elif result:
            plans_seen += 1
    return {"tenders": len(seen), "plans": plans_seen, "snapshots": changed}


def _public(row) -> dict:
    return {key: str(value) if isinstance(value, Decimal) else value
            for key, value in dict(row).items()}


def _money_stats(row: dict) -> dict:
    package = parse_money(row.get("package_price"))
    winning = parse_money(row.get("winning_price"))
    if package is None or package <= 0 or winning is None:
        return {"saving_amount": None, "saving_rate": None}
    saving = package - winning
    return {"saving_amount": str(saving),
            "saving_rate": str((saving / package * 100).quantize(Decimal("0.01")))}


def _search_terms(query: str) -> tuple[list, str]:
    conditions, words = [], []
    try:
        tokens = shlex.split(str(query or "")[:500])
    except ValueError:
        tokens = str(query or "")[:500].split()
    columns = {"investor": tenders.c.investor_name,
               "contractor": tenders.c.winning_contractor,
               "status": tenders.c.status,
               "procurer": tenders.c.procuring_entity_name}
    for token in tokens:
        if ":" in token:
            name, value = token.split(":", 1)
            if name in columns and value:
                conditions.append(func.lower(columns[name]).like("%" + value.lower().replace("%", "") + "%"))
                continue
            if name in {"before", "after"} and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                conditions.append(tenders.c.publish_date < value if name == "before"
                                  else tenders.c.publish_date >= value)
                continue
        words.append(token)
    remaining = " ".join(words).strip()
    if remaining:
        pattern = "%" + remaining.lower().replace("%", "") + "%"
        conditions.append(or_(*[func.lower(column).like(pattern) for column in (
            tenders.c.tender_code, tenders.c.khlcnt_code, tenders.c.title,
            tenders.c.investor_name, tenders.c.procuring_entity_name,
            tenders.c.winning_contractor)]))
    return conditions, remaining


def list_tenders(*, page: int = 1, page_size: int = 50, query: str = "",
                 status: str = "", investor_id: str = "", contractor_id: str = "",
                 from_date: str = "", to_date: str = "", sort: str = "published",
                 descending: bool = True, results_only: bool = False) -> dict:
    page, page_size = max(1, min(int(page), 100_000)), max(1, min(int(page_size), 100))
    conditions, _ = _search_terms(query)
    if status:
        conditions.append(tenders.c.status == status[:160])
    if investor_id:
        conditions.append(tenders.c.investor_id == investor_id[:32])
    if contractor_id:
        conditions.append(tenders.c.contractor_id == contractor_id[:32])
    if from_date:
        if not iso_date(from_date):
            raise ValueError("Từ ngày không hợp lệ.")
        conditions.append(tenders.c.publish_date >= iso_date(from_date))
    if to_date:
        if not iso_date(to_date):
            raise ValueError("Đến ngày không hợp lệ.")
        conditions.append(tenders.c.publish_date <= iso_date(to_date) + "T23:59:59")
    if results_only:
        conditions.append(tenders.c.winning_contractor.is_not(None))
    column = SORTS.get(sort, tenders.c.publish_date)
    order = column.desc() if descending else column.asc()
    with get_db().engine.connect() as conn:
        total = conn.scalar(select(func.count()).select_from(tenders).where(*conditions)) or 0
        rows = conn.execute(select(tenders).where(*conditions)
            .order_by(order, tenders.c.tender_code).offset((page - 1) * page_size)
            .limit(page_size)).mappings().all()
    return {"items": [_public(row) | _money_stats(row) for row in rows],
            "page": page, "page_size": page_size, "total": total}


def get_tender(code: str) -> dict | None:
    code = clean_code(code)
    if not code:
        return None
    with get_db().engine.connect() as conn:
        row = conn.execute(select(tenders).where(tenders.c.tender_code == code)).mappings().first()
        if not row:
            return None
        events = conn.execute(select(tender_events).where(tender_events.c.tender_code == code)
            .order_by(tender_events.c.event_at, tender_events.c.id).limit(200)).mappings().all()
        changes = conn.execute(select(tender_changes).where(tender_changes.c.tender_code == code)
            .order_by(tender_changes.c.detected_at.desc()).limit(100)).mappings().all()
        source_docs = conn.execute(select(tender_source_documents).where(
            tender_source_documents.c.tender_code == code).order_by(
            tender_source_documents.c.document_group_id,
            tender_source_documents.c.version)).mappings().all()
        snapshots = conn.execute(select(tender_snapshots.c.id, tender_snapshots.c.version,
            tender_snapshots.c.created_at).where(tender_snapshots.c.tender_code == code)
            .order_by(tender_snapshots.c.version.desc()).limit(20)).mappings().all()
        related_conditions = []
        if row["khlcnt_code"]:
            related_conditions.append(tenders.c.khlcnt_code == row["khlcnt_code"])
        if row["investor_id"]:
            related_conditions.append(tenders.c.investor_id == row["investor_id"])
        related = conn.execute(select(tenders.c.tender_code, tenders.c.title,
            tenders.c.khlcnt_code, tenders.c.investor_id).where(
            tenders.c.tender_code != code, or_(*related_conditions))
            .order_by(tenders.c.publish_date.desc()).limit(10)).mappings().all() if related_conditions else []
    data = _public(row) | _money_stats(row)
    age = None
    if row["last_synced_at"]:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["last_synced_at"])).total_seconds()
        except ValueError:
            pass
    data["data_health"] = "Lỗi đồng bộ" if row["sync_error"] else (
        "Dữ liệu chưa đầy đủ" if row["sync_status"] == "partial" else
        "Chưa đồng bộ" if age is None else "Dữ liệu cũ" if age > source_settings()["tender_stale_after"] else
        "Có cập nhật" if changes and changes[0]["detected_at"] >= row["last_synced_at"] else "Đã đồng bộ")
    data["quality_flags"] = [flag for flag, missing in (
        ("missing_price", row["package_price"] is None),
        ("missing_deadline", not row["bid_closing_date"]),
        ("missing_investor", not row["investor_name"]),
        ("sync_failed", bool(row["sync_error"])),
        ("partial_data", not row["title"] or not row["publish_date"])) if missing]
    return {"tender": data, "timeline": [_public(item) for item in events],
            "changes": [_public(item) for item in changes],
            "documents": [_public(item) for item in source_docs],
            "snapshots": [_public(item) for item in snapshots],
            "related": [dict(item) | {"reason": "Cùng KHLCNT" if item["khlcnt_code"] and
                item["khlcnt_code"] == row["khlcnt_code"] else "Cùng chủ đầu tư"}
                for item in related]}


def get_plan(code: str) -> dict | None:
    code = clean_code(code, "plan")
    if not code:
        return None
    with get_db().engine.connect() as conn:
        row = conn.execute(select(plans).where(plans.c.plan_code == code)).mappings().first()
        if not row:
            return None
        count = conn.scalar(select(func.count()).select_from(tenders)
            .where(tenders.c.khlcnt_code == code)) or 0
        packages = conn.execute(select(tenders.c.tender_code, tenders.c.title,
            tenders.c.status, tenders.c.package_price, tenders.c.publish_date)
            .where(tenders.c.khlcnt_code == code)
            .order_by(tenders.c.publish_date.desc()).limit(100)).mappings().all()
    return {"plan": _public(row), "packages": [_public(item) for item in packages],
            "package_count": count}


def entity_profile(kind: str, entity_id: str, *, page: int = 1,
                   page_size: int = 30, query: str = "", status: str = "",
                   from_date: str = "", to_date: str = "") -> dict | None:
    table, link = {"investor": (investors, tenders.c.investor_id),
                   "contractor": (contractors, tenders.c.contractor_id),
                   "procurer": (procuring_entities, tenders.c.procuring_entity_id)}.get(kind, (None, None))
    if table is None or not re.fullmatch(r"[0-9a-f]{32}", entity_id):
        return None
    page, page_size = max(1, int(page)), max(1, min(int(page_size), 100))
    conditions = [link == entity_id]
    if query:
        pattern = "%" + query[:160].lower().replace("%", "") + "%"
        conditions.append(or_(func.lower(tenders.c.tender_code).like(pattern),
                              func.lower(tenders.c.title).like(pattern)))
    if status:
        conditions.append(tenders.c.status == status[:160])
    if from_date and iso_date(from_date):
        conditions.append(tenders.c.publish_date >= iso_date(from_date))
    if to_date and iso_date(to_date):
        conditions.append(tenders.c.publish_date <= iso_date(to_date) + "T23:59:59")
    with get_db().engine.connect() as conn:
        entity = conn.execute(select(table).where(table.c.id == entity_id)).mappings().first()
        if not entity:
            return None
        total = conn.scalar(select(func.count()).select_from(tenders).where(*conditions)) or 0
        rows = conn.execute(select(tenders).where(*conditions)
            .order_by(tenders.c.publish_date.desc()).offset((page - 1) * page_size)
            .limit(page_size)).mappings().all()
        stats = conn.execute(select(func.count(), func.sum(tenders.c.package_price),
            func.sum(tenders.c.winning_price),
            func.sum(tenders.c.winning_contractor.is_not(None).cast(Integer)))
            .where(link == entity_id)).one()
    return {"entity": _public(entity), "kind": kind, "items": [_public(item) | _money_stats(item)
        for item in rows], "page": page, "page_size": page_size, "total": total,
        "stats": {"tenders": stats[0] or 0,
                  "package_value": str(stats[1]) if stats[1] is not None else None,
                  "winning_value": str(stats[2]) if stats[2] is not None else None,
                  "results": stats[3] or 0}}


def compare_tenders(codes: list[str]) -> dict:
    selected = list(dict.fromkeys(clean_code(code) for code in codes))
    selected = [code for code in selected if code]
    if not 2 <= len(selected) <= 5:
        raise ValueError("Chọn từ 2 đến 5 mã TBMT hợp lệ.")
    with get_db().engine.connect() as conn:
        rows = {row["tender_code"]: row for row in conn.execute(select(tenders)
            .where(tenders.c.tender_code.in_(selected))).mappings()}
    if len(rows) != len(selected):
        raise LookupError("Một hoặc nhiều mã chưa có trong dữ liệu đã thu thập.")
    return {"items": [_public(rows[code]) | _money_stats(rows[code]) for code in selected],
            "fields": ["tender_code", "title", "investor_name", "package_price",
                       "bid_closing_date", "selection_method", "status",
                       "winning_contractor", "winning_price", "saving_rate"]}


def analytics(period: str = "month", from_date: str = "", to_date: str = "") -> dict:
    if period not in {"day", "week", "month", "quarter", "year"}:
        raise ValueError("Đơn vị thời gian không hợp lệ.")
    conditions = [tenders.c.publish_date.is_not(None)]
    if from_date:
        if not iso_date(from_date):
            raise ValueError("Từ ngày không hợp lệ.")
        conditions.append(tenders.c.publish_date >= iso_date(from_date))
    if to_date:
        if not iso_date(to_date):
            raise ValueError("Đến ngày không hợp lệ.")
        conditions.append(tenders.c.publish_date <= iso_date(to_date) + "T23:59:59")
    day = func.substr(tenders.c.publish_date, 1, 10).label("day")
    with get_db().engine.connect() as conn:
        daily = conn.execute(select(day, func.count().label("tenders"),
            func.sum(tenders.c.package_price).label("value"),
            func.sum(tenders.c.winning_contractor.is_not(None).cast(Integer)).label("results"))
            .where(*conditions).group_by(day).order_by(day)).mappings().all()
        total = conn.scalar(select(func.count()).select_from(tenders)) or 0
        missing_dates = conn.scalar(select(func.count()).select_from(tenders)
            .where(tenders.c.publish_date.is_(None))) or 0
        top_investors = conn.execute(select(tenders.c.investor_id, tenders.c.investor_name,
            func.count().label("count")).where(tenders.c.investor_id.is_not(None))
            .group_by(tenders.c.investor_id, tenders.c.investor_name)
            .order_by(func.count().desc()).limit(10)).mappings().all()
        top_contractors = conn.execute(select(tenders.c.contractor_id,
            tenders.c.winning_contractor, func.count().label("count"))
            .where(tenders.c.contractor_id.is_not(None))
            .group_by(tenders.c.contractor_id, tenders.c.winning_contractor)
            .order_by(func.count().desc()).limit(10)).mappings().all()
        statuses = conn.execute(select(tenders.c.status, func.count().label("count"))
            .where(tenders.c.status.is_not(None)).group_by(tenders.c.status)
            .order_by(func.count().desc())).mappings().all()
        methods = conn.execute(select(tenders.c.selection_method, func.count().label("count"))
            .where(tenders.c.selection_method.is_not(None))
            .group_by(tenders.c.selection_method).order_by(func.count().desc())).mappings().all()
    buckets: dict[str, dict] = {}
    for item in daily:
        try:
            observed = date.fromisoformat(item["day"])
        except (TypeError, ValueError):
            continue
        if period == "day":
            key = observed.isoformat()
        elif period == "week":
            year, week, _ = observed.isocalendar()
            key = f"{year}-W{week:02d}"
        elif period == "month":
            key = f"{observed.year}-{observed.month:02d}"
        elif period == "quarter":
            key = f"{observed.year}-Q{(observed.month - 1) // 3 + 1}"
        else:
            key = str(observed.year)
        bucket = buckets.setdefault(key, {"period": key, "tenders": 0,
            "package_value": Decimal(0), "valued_count": 0, "results": 0})
        bucket["tenders"] += item["tenders"]
        bucket["results"] += item["results"] or 0
        if item["value"] is not None:
            bucket["package_value"] += item["value"]
            bucket["valued_count"] += 1
    series = [{**entry, "package_value": str(entry["package_value"])
               if entry["valued_count"] else None} for entry in buckets.values()]
    return {"period": period, "series": series, "total_tenders": total,
            "dated_tenders": sum(item["tenders"] for item in series),
            "missing_dates": missing_dates,
            "top_investors": [dict(item) for item in top_investors],
            "top_contractors": [dict(item) for item in top_contractors],
            "statuses": [dict(item) for item in statuses],
            "selection_methods": [dict(item) for item in methods]}


def deadline_center(days: int = 30, page: int = 1, page_size: int = 50) -> dict:
    days = max(1, min(int(days), 30))
    page, page_size = max(1, int(page)), max(1, min(int(page_size), 100))
    today = datetime.now(TZ)
    earliest = today.date().isoformat()
    latest = (today.date() + timedelta(days=days)).isoformat() + "T23:59:59"
    conditions = [tenders.c.bid_closing_date >= earliest,
                  tenders.c.bid_closing_date <= latest,
                  ~func.lower(func.coalesce(tenders.c.status, "")).like("%hủy%")]
    with get_db().engine.connect() as conn:
        total = conn.scalar(select(func.count()).select_from(tenders).where(*conditions)) or 0
        rows = conn.execute(select(tenders).where(*conditions)
            .order_by(tenders.c.bid_closing_date).offset((page - 1) * page_size)
            .limit(page_size)).mappings().all()
    items = []
    for row in rows:
        raw = row["bid_closing_date"]
        try:
            closing = datetime.fromisoformat(raw)
            if closing.tzinfo is None:
                closing = closing.replace(tzinfo=TZ)
            remaining = int((closing - today).total_seconds())
        except (TypeError, ValueError):
            remaining = None
        items.append(_public(row) | {"remaining_seconds": remaining})
    return {"items": items, "page": page, "page_size": page_size,
            "total": total, "days": days, "as_of": today.isoformat(timespec="seconds")}


def admin_data_stats() -> dict:
    with get_db().engine.connect() as conn:
        count = lambda table: conn.scalar(select(func.count()).select_from(table)) or 0
        return {"tenders": count(tenders), "plans": count(plans),
                "results": conn.scalar(select(func.count()).select_from(tenders)
                    .where(tenders.c.winning_contractor.is_not(None))) or 0,
                "contractors": count(contractors), "investors": count(investors),
                "source_documents": count(tender_source_documents),
                "last_sync": conn.scalar(select(func.max(tenders.c.last_synced_at))),
                "sync_failures": conn.scalar(select(func.count()).select_from(tenders)
                    .where(tenders.c.sync_error.is_not(None))) or 0,
                "missing_price": conn.scalar(select(func.count()).select_from(tenders)
                    .where(tenders.c.package_price.is_(None))) or 0,
                "missing_deadline": conn.scalar(select(func.count()).select_from(tenders)
                    .where(tenders.c.bid_closing_date.is_(None))) or 0,
                "missing_investor": conn.scalar(select(func.count()).select_from(tenders)
                    .where(tenders.c.investor_id.is_(None))) or 0}
