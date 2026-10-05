"""Local, paginated search over synchronized public procurement records."""

from __future__ import annotations

import re
import os
import shlex
import threading
import time
import unicodedata
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from difflib import SequenceMatcher

from sqlalchemy import case, cast, func, literal, or_, select, text, String, union_all

from server.database import (contractors, entity_merges, get_db, investors, plans, search_metrics_daily,
                             procuring_entities, tenders)


def normalize_search(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold()).replace("đ", "d")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)).strip()


SORT_FIELDS = {"relevance", "published", "deadline", "price", "name", "updated"}
KINDS = {"tender", "plan", "investor", "procurer", "contractor"}
_cache_guard = threading.Lock()
_cache: dict[tuple, tuple[float, dict]] = {}
_key_locks: dict[tuple, threading.Lock] = {}
_cache_epoch = 0


def _cache_ttl() -> int:
    try:
        return max(1, min(int(os.environ.get("SEARCH_CACHE_TTL_SECONDS", "120")), 600))
    except ValueError:
        return 120


def invalidate_search_cache() -> None:
    global _cache_epoch
    with _cache_guard:
        _cache.clear()
        _cache_epoch += 1


def record_search_metric(kind: str, elapsed_ms: int, result: dict) -> None:
    """Aggregate counts only; never store a user's query or filter values."""
    day = datetime.now(timezone.utc).date().isoformat()
    with get_db().engine.begin() as conn:
        conn.execute(text("""INSERT INTO search_metrics_daily
            (day, kind, searches, zero_results, latency_total_ms, cache_hits)
            VALUES (:day, :kind, 1, :zero, :latency, :cached)
            ON CONFLICT (day, kind) DO UPDATE SET
            searches = search_metrics_daily.searches + 1,
            zero_results = search_metrics_daily.zero_results + excluded.zero_results,
            latency_total_ms = search_metrics_daily.latency_total_ms + excluded.latency_total_ms,
            cache_hits = search_metrics_daily.cache_hits + excluded.cache_hits"""),
            {"day": day, "kind": kind if kind in KINDS else "all",
             "zero": int(result["total"] == 0), "latency": max(0, elapsed_ms),
             "cached": int(result.get("cache_hit", False))})


def search_metrics(days: int = 14) -> dict:
    since = (datetime.now(timezone.utc).date() - timedelta(days=max(1, min(days, 90)) - 1)).isoformat()
    with get_db().engine.connect() as conn:
        rows = conn.execute(select(search_metrics_daily).where(search_metrics_daily.c.day >= since)
                            .order_by(search_metrics_daily.c.day.desc())).mappings().all()
    items = [dict(row) for row in rows]
    total = sum(row["searches"] for row in items)
    return {"items": items, "searches": total,
            "zero_result_rate": round(sum(row["zero_results"] for row in items) / total, 4) if total else 0,
            "average_latency_ms": round(sum(row["latency_total_ms"] for row in items) / total, 1) if total else 0,
            "cache_hit_rate": round(sum(row["cache_hits"] for row in items) / total, 4) if total else 0}


def search(**kwargs) -> dict:
    """Short per-process cache; concurrent identical requests share one query."""
    force_refresh = kwargs.pop("force_refresh", False) is True
    key = (get_db().url, tuple(sorted(kwargs.items())))
    with _cache_guard:
        epoch = _cache_epoch
        entry = _cache.get(key)
        if not force_refresh and entry and entry[0] > time.monotonic():
            return deepcopy(entry[1]) | {"cache_hit": True}
        lock = _key_locks.setdefault(key, threading.Lock())
    with lock:
        with _cache_guard:
            entry = _cache.get(key)
            if not force_refresh and entry and entry[0] > time.monotonic():
                return deepcopy(entry[1]) | {"cache_hit": True}
        try:
            result = _search_uncached(**kwargs)
        except Exception:
            with _cache_guard:
                _key_locks.pop(key, None)
            raise
        with _cache_guard:
            if epoch == _cache_epoch:
                if len(_cache) >= 128:
                    oldest = min(_cache, key=lambda item: _cache[item][0])
                    _cache.pop(oldest, None)
                _cache[key] = (time.monotonic() + _cache_ttl(), deepcopy(result))
            _key_locks.pop(key, None)
        return result | {"cache_hit": False}


def parse_query(value: str) -> tuple[str, dict]:
    """Parse only known field operators; malformed tokens remain plain text."""
    try:
        tokens = shlex.split(str(value or "")[:200])
    except ValueError:
        tokens = str(value or "")[:200].split()
    fields, words = {}, []
    allowed = {"investor": "investor", "contractor": "contractor",
               "status": "status", "procurer": "procurer"}
    for token in tokens:
        name, separator, raw = token.partition(":")
        if separator and raw:
            if name in allowed:
                fields[allowed[name]] = raw[:160]
                continue
            if name in {"before", "after"} and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                try:
                    fields["to_date" if name == "before" else "from_date"] = _date(raw)
                    continue
                except ValueError:
                    pass
            if name == "price" and re.fullmatch(r"[<>]=?\d+", raw):
                fields["price_min" if raw.startswith(">") else "price_max"] = raw.lstrip("<>=")
                continue
        words.append(token)
    return " ".join(words), fields


def _date(value: str) -> str:
    if not value:
        return ""
    return date.fromisoformat(value).isoformat()


def _search_uncached(*, q: str = "", page: int = 1, page_size: int = 25,
           kind: str = "", status: str = "", location: str = "",
           investor: str = "", procurer: str = "", contractor: str = "",
           from_date: str = "", to_date: str = "", deadline_from: str = "",
           deadline_to: str = "", price_min: str = "", price_max: str = "",
           selection_method: str = "", contract_type: str = "",
           results_only: bool = False, sort: str = "relevance",
           order: str = "desc", internal: bool = False) -> dict:
    if kind and kind not in KINDS:
        raise ValueError("Loại dữ liệu không hợp lệ.")
    if sort not in SORT_FIELDS or order not in {"asc", "desc"}:
        raise ValueError("Cách sắp xếp không hợp lệ.")
    page = max(1, int(page)) if internal else max(1, min(int(page), 100_000))
    page_size = int(page_size)
    if page_size not in ({10, 25, 50, 100, 1000} if internal else {10, 25, 50, 100}):
        raise ValueError("Số kết quả mỗi trang không hợp lệ.")
    free_text, operators = parse_query(q)
    if not kind and not operators:
        if re.fullmatch(r"IB[0-9A-Z-]{6,32}", free_text.strip().upper()):
            kind = "tender"
        elif re.fullmatch(r"PL[0-9A-Z]{6,30}", free_text.strip().upper()):
            kind = "plan"
    investor = investor or operators.get("investor", "")
    contractor = contractor or operators.get("contractor", "")
    procurer = procurer or operators.get("procurer", "")
    status = status or operators.get("status", "")
    from_date = from_date or operators.get("from_date", "")
    to_date = to_date or operators.get("to_date", "")
    price_min = price_min or operators.get("price_min", "")
    price_max = price_max or operators.get("price_max", "")
    phrase = normalize_search(free_text)
    code = re.sub(r"[^A-Z0-9]", "", free_text[:100].upper())
    postgres = get_db().engine.dialect.name == "postgresql"
    conditions = []
    for raw, column, greater in ((from_date, tenders.c.publish_date, True),
                                 (to_date, tenders.c.publish_date, False),
                                 (deadline_from, tenders.c.bid_closing_date, True),
                                 (deadline_to, tenders.c.bid_closing_date, False)):
        if raw:
            value = _date(raw)
            conditions.append(column >= value if greater else column <= value + "T23:59:59")
    for raw, column in ((status, tenders.c.status), (location, tenders.c.location),
                        (investor, tenders.c.investor_name),
                        (procurer, tenders.c.procuring_entity_name),
                        (contractor, tenders.c.winning_contractor),
                        (selection_method, tenders.c.selection_method),
                        (contract_type, tenders.c.contract_type)):
        if raw:
            value = raw[:160].casefold().replace("%", "").replace("_", "")
            # A field-specific filter must not accidentally match another field.
            if any(column is item for item in (tenders.c.status, tenders.c.selection_method,
                                                tenders.c.contract_type)):
                conditions.append(func.lower(column) == raw[:160].casefold())
            else:
                conditions.append(func.lower(column).like("%" + value + "%"))
    for raw, greater in ((price_min, True), (price_max, False)):
        if raw:
            try:
                amount = int(raw)
            except ValueError as exc:
                raise ValueError("Khoảng giá không hợp lệ.") from exc
            if amount < 0:
                raise ValueError("Khoảng giá không hợp lệ.")
            conditions.append(tenders.c.package_price >= amount if greater else
                              tenders.c.package_price <= amount)
    if results_only:
        conditions.append(tenders.c.winning_contractor.is_not(None))
    tender_filters = bool(conditions)

    def branch(table, type_name, code_col, name_col, search_col, published,
               deadline, price, status_col, investor_col, updated, extra=()):
        if phrase:
            pattern = phrase.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            full_text = (func.to_tsvector("simple", search_col).op("@@")(
                             func.plainto_tsquery("simple", phrase))
                         if postgres else literal(False))
            matches = or_(func.upper(code_col) == code, func.upper(code_col).like(code + "%"),
                          full_text, search_col.like("%" + pattern + "%", escape="\\"))
            rank = case((func.upper(code_col) == code, 0),
                        (func.lower(name_col) == free_text.strip().casefold(), 1),
                        (func.upper(code_col).like(code + "%"), 2),
                        (search_col.like(pattern + "%", escape="\\"), 3),
                        (full_text, 4), else_=5)
        else:
            matches, rank = literal(True), literal(5)
        return select(literal(type_name).label("kind"), cast(code_col, String).label("code"),
            name_col.label("name"), published.label("published"), deadline.label("deadline"),
            price.label("price"), status_col.label("status"), investor_col.label("investor"),
            updated.label("updated"), rank.label("rank")).where(matches, *extra)

    empty = literal(None)
    branches = []
    if kind in {"", "tender"}:
        branches.append(branch(tenders, "tender", tenders.c.tender_code, tenders.c.title,
            tenders.c.search_text, tenders.c.publish_date, tenders.c.bid_closing_date,
            tenders.c.package_price, tenders.c.status, tenders.c.investor_name,
            tenders.c.last_seen_at, conditions))
    if not tender_filters:
        if kind in {"", "plan"}:
            branches.append(branch(plans, "plan", plans.c.plan_code, plans.c.title,
                plans.c.search_text, plans.c.publish_date, empty, plans.c.package_price,
                empty, plans.c.investor_name, plans.c.last_seen_at))
        for type_name, table in (("investor", investors), ("procurer", procuring_entities),
                                 ("contractor", contractors)):
            if kind in {"", type_name}:
                quality_kind = "procuring_entity" if type_name == "procurer" else type_name
                active_entity = ~select(entity_merges.c.id).where(
                    entity_merges.c.entity_type == quality_kind,
                    entity_merges.c.source_id == table.c.id).exists()
                branches.append(branch(table, type_name, table.c.id,
                    table.c.name, table.c.search_text, empty, empty, empty, empty, empty,
                    table.c.last_seen_at, (active_entity,)))
    if not branches:
        return {"items": [], "page": page, "page_size": page_size, "total": 0, "total_pages": 0}
    data = union_all(*branches).subquery("search_results") if len(branches) > 1 else branches[0].subquery("search_results")
    sort_col = {"published": data.c.published, "deadline": data.c.deadline,
                "price": data.c.price, "name": data.c.name, "updated": data.c.updated}.get(sort)
    ordering = ([data.c.rank.asc(), data.c.updated.desc()] if sort == "relevance" else
                [sort_col.asc().nullslast() if order == "asc" else sort_col.desc().nullslast()])
    with get_db().engine.connect() as conn:
        total = conn.scalar(select(func.count()).select_from(data)) or 0
        rows = conn.execute(select(data).order_by(*ordering, data.c.code)
                            .offset((page - 1) * page_size).limit(page_size)).mappings()
        items = [dict(row) for row in rows]
        if not total and phrase and not tender_filters and len(phrase) >= 6:
            # Conservative typo fallback, bounded at 300 candidates. It runs
            # only after exact/normalized search has produced no matches.
            first = phrase.split()[0]
            candidates = []
            sources = (("tender", tenders, tenders.c.tender_code, tenders.c.title),
                       ("plan", plans, plans.c.plan_code, plans.c.title),
                       ("investor", investors, investors.c.id, investors.c.name),
                       ("procurer", procuring_entities, procuring_entities.c.id, procuring_entities.c.name),
                       ("contractor", contractors, contractors.c.id, contractors.c.name))
            for type_name, table, code_col, name_col in sources:
                if kind and kind != type_name:
                    continue
                candidates.extend((type_name, row) for row in conn.execute(
                    select(code_col.label("code"), name_col.label("name"),
                           table.c.last_seen_at.label("updated"))
                    .where(table.c.search_text.like(first + "%"),
                           *(() if type_name in {"tender", "plan"} else (
                               ~select(entity_merges.c.id).where(
                                   entity_merges.c.entity_type == (
                                       "procuring_entity" if type_name == "procurer" else type_name),
                                   entity_merges.c.source_id == table.c.id).exists(),)))
                    .order_by(table.c.last_seen_at.desc()).limit(300)).mappings())
            fuzzy = []
            for type_name, row in candidates:
                name = normalize_search(row["name"])
                comparable = name[:max(len(phrase) + 4, 20)]
                score = SequenceMatcher(None, phrase, comparable).ratio()
                if score >= .78:
                    fuzzy.append({"kind": type_name, "code": row["code"], "name": row["name"],
                                  "published": None, "deadline": None, "price": None,
                                  "status": None, "investor": None, "updated": row["updated"],
                                  "rank": 6, "match_score": round(score, 3)})
            fuzzy.sort(key=lambda row: (-row["match_score"], row["code"]))
            total = len(fuzzy)
            items = fuzzy[(page - 1) * page_size:page * page_size]
    return {"items": items, "page": page, "page_size": page_size,
            "total": total, "total_pages": (total + page_size - 1) // page_size}
