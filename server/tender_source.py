"""Small adapter around the existing e-GP client; public data only."""
from __future__ import annotations

import threading
import time
from typing import Protocol

from sqlalchemy import update

from app import (MuaSamCongClient, deep_first_value, extract_notify_no,
                 plan_row_from_search, rows_from_kqlcnt)
from server.intelligence import clean_code, get_tender, ingest_row
from server.database import get_db, tenders
from server.config import source_settings

_SOURCE_LOCK = threading.Lock()
_LAST_REQUEST = 0.0
_CODE_LOCKS: dict[str, threading.Lock] = {}


class TenderSource(Protocol):
    def get_tender(self, code: str) -> tuple[dict, dict | None, dict | None]: ...


class EgpTenderSource:
    def __init__(self, *, force_refresh: bool = False):
        self.force_refresh = force_refresh

    def get_tender(self, code: str) -> tuple[dict, dict | None, dict | None]:
        global _LAST_REQUEST
        code = clean_code(code)
        if not code:
            raise ValueError("Mã TBMT không hợp lệ.")
        with _SOURCE_LOCK:
            delay = 0.6 - (time.monotonic() - _LAST_REQUEST)
            if delay > 0:
                time.sleep(delay)
            _LAST_REQUEST = time.monotonic()
        client = MuaSamCongClient(force_refresh=self.force_refresh)
        try:
            records = client.search_notices(code, max_pages=1, page_size=20)
            record = next((item for item in records
                           if clean_code(extract_notify_no(item)) == code), None)
            if record is None:
                raise LookupError("Không tìm thấy mã TBMT trên nguồn e-GP.")
            detail = None
            package_id = deep_first_value(record, ["bidId", "packageId"], "")
            if package_id:
                try:
                    detail = client.get_package_detail(str(package_id))
                except Exception:
                    # Search data stays usable; caller reports partial source detail.
                    detail = None
            result = None
            result_id = deep_first_value(record, ["inputResultId"], "")
            if result_id:
                try:
                    result = client.get_kqlcnt(str(result_id))
                except Exception:
                    result = None
            return record, detail, result
        finally:
            # This compatibility session is local; the real source session is
            # shared by SourceRequestManager and remains open for reuse.
            client.s.close()


def refresh_tender(code: str, *, force: bool = False,
                   source: TenderSource | None = None, max_age_seconds: int | None = None) -> dict:
    code = clean_code(code)
    if not code:
        raise ValueError("Mã TBMT không hợp lệ.")
    max_age_seconds = max_age_seconds or source_settings()["tender_cache_ttl"]
    lock = _CODE_LOCKS.setdefault(code, threading.Lock())
    with lock:
        cached = get_tender(code)
        if cached and not force and cached["tender"]["last_synced_at"]:
            from datetime import datetime, timezone
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                    cached["tender"]["last_synced_at"])).total_seconds()
                if age < max_age_seconds and not cached["tender"]["sync_error"]:
                    return {"detail": cached, "cached": True}
            except ValueError:
                pass
        provider = source or EgpTenderSource(force_refresh=force)
        record, detail, result = provider.get_tender(code)
        row = plan_row_from_search(record)
        if result:
            result_rows = rows_from_kqlcnt(result, record)
            if result_rows:
                extra = result_rows[0]
                row.winner = extra.winner or row.winner
                row.decision_date = extra.decision_date or row.decision_date
                row.winning_price = extra.winning_price or row.winning_price
        observation = ingest_row(row, source_record={"search": record,
            "detail": detail, "result": result})
        partial = bool((deep_first_value(record, ["bidId", "packageId"], "") and detail is None)
                       or (deep_first_value(record, ["inputResultId"], "") and result is None))
        if partial:
            with get_db().engine.begin() as conn:
                conn.execute(update(tenders).where(tenders.c.tender_code == code)
                    .values(sync_status="partial"))
        return {"detail": get_tender(code), "cached": False,
                "changed": observation["changed"] if observation else False,
                "detail_available": detail is not None, "partial": partial}
