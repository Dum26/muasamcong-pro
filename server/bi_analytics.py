"""Server-side BI aggregates with source counts and explicit null coverage."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select

from server.database import get_db, plans, tender_changes, tenders
from server.intelligence import TZ
from server.reporting import DATASETS, _conditions, _date

FILTER_FIELDS = {"publish_date", "status", "location", "investor_name",
    "procuring_entity_name", "winning_contractor", "selection_method",
    "contract_type", "package_price"}
PERIODS = {"day", "week", "month", "quarter", "year"}


def _filters(raw: dict) -> list[dict]:
    if not isinstance(raw, dict):
        raise ValueError("Bộ lọc analytics không hợp lệ.")
    result = []
    for key in ("from", "to"):
        if raw.get(key):
            result.append({"field": "publish_date", "operator": "after" if key == "from" else "before",
                "value": _date(raw[key]) if key == "from" else
                (date.fromisoformat(_date(raw[key])) + timedelta(days=1)).isoformat()})
    for key in ("status", "location", "investor_name", "procuring_entity_name",
                "winning_contractor", "selection_method", "contract_type"):
        if raw.get(key):
            result.append({"field": key, "operator": "equals", "value": str(raw[key])[:320]})
    if raw.get("price_min") not in (None, ""):
        result.append({"field": "package_price", "operator": "at_least",
                       "value": raw["price_min"]})
    if raw.get("price_max") not in (None, ""):
        result.append({"field": "package_price", "operator": "at_most",
                       "value": raw["price_max"]})
    return result


def _bucket(value: str, period: str) -> str:
    day = date.fromisoformat(value)
    if period == "day":
        return day.isoformat()
    if period == "week":
        year, week, _ = day.isocalendar()
        return f"{year}-W{week:02d}"
    if period == "month":
        return f"{day.year}-{day.month:02d}"
    if period == "quarter":
        return f"{day.year}-Q{(day.month-1)//3+1}"
    return str(day.year)


def _aggregate(conn, conditions: list) -> dict:
    values = conn.execute(select(func.count().label("tenders"),
        func.count(tenders.c.package_price).label("priced"),
        func.sum(tenders.c.package_price).label("package_value"),
        func.count(tenders.c.winning_contractor).label("results"),
        func.count(tenders.c.winning_price).label("winning_priced"),
        func.sum(tenders.c.winning_price).label("winning_value"),
        func.count(func.distinct(tenders.c.investor_id)).label("investors"),
        func.count(func.distinct(tenders.c.contractor_id)).label("contractors"))
        .where(*conditions)).mappings().one()
    saving_condition = [*conditions, tenders.c.package_price.is_not(None),
        tenders.c.package_price > 0, tenders.c.winning_price.is_not(None)]
    savings = conn.execute(select(func.count().label("count"),
        func.sum(tenders.c.package_price - tenders.c.winning_price).label("value"),
        func.sum(tenders.c.package_price).label("base"))
        .where(*saving_condition)).mappings().one()
    amount = savings["value"]
    base = savings["base"]
    return {**{key: str(value) if isinstance(value, Decimal) else value
                for key, value in values.items()},
        "saving_count": savings["count"],
        "saving_amount": str(amount) if amount is not None else None,
        "saving_rate": str((amount / base * 100).quantize(Decimal("0.01")))
            if amount is not None and base else None}


def _comparison(conn, raw: dict, results_only: bool = False) -> dict | None:
    if not raw.get("from") or not raw.get("to"):
        return None
    start, end = date.fromisoformat(_date(raw["from"])), date.fromisoformat(_date(raw["to"]))
    if end < start or (end - start).days > 730:
        raise ValueError("Khoảng ngày phân tích không hợp lệ hoặc quá 2 năm.")
    span = (end - start).days + 1
    prior = dict(raw, **{"from": (start - timedelta(days=span)).isoformat(),
                         "to": (start - timedelta(days=1)).isoformat()})
    prior_year = dict(raw, **{"from": start.replace(year=start.year - 1).isoformat() if not
        (start.month == 2 and start.day == 29) else start.replace(year=start.year - 1, day=28).isoformat(),
        "to": end.replace(year=end.year - 1).isoformat() if not
        (end.month == 2 and end.day == 29) else end.replace(year=end.year - 1, day=28).isoformat()})
    result_condition = [tenders.c.winning_contractor.is_not(None)] if results_only else []
    return {"previous": {"from": prior["from"], "to": prior["to"],
                "values": _aggregate(conn, _conditions(DATASETS["tenders"], _filters(prior)) + result_condition)},
            "year_ago": {"from": prior_year["from"], "to": prior_year["to"],
                "values": _aggregate(conn, _conditions(DATASETS["tenders"], _filters(prior_year)) + result_condition)}}


def overview(raw_filters: dict | None = None, period: str = "month",
             results_only: bool = False) -> dict:
    raw_filters = raw_filters or {}
    if period not in PERIODS:
        raise ValueError("Đơn vị thời gian không hợp lệ.")
    filters = _filters(raw_filters)
    conditions = _conditions(DATASETS["tenders"], filters)
    if results_only:
        conditions.append(tenders.c.winning_contractor.is_not(None))
    day_expr = func.substr(tenders.c.publish_date, 1, 10).label("day")
    with get_db().engine.connect() as conn:
        kpis = _aggregate(conn, conditions)
        latest = conn.scalar(select(func.max(tenders.c.last_synced_at)).where(*conditions))
        failures = conn.scalar(select(func.count()).select_from(tenders)
            .where(*conditions, tenders.c.sync_error.is_not(None))) or 0
        daily = conn.execute(select(day_expr, func.count().label("tenders"),
            func.count(tenders.c.winning_contractor).label("results"),
            func.count(tenders.c.package_price).label("priced"),
            func.sum(tenders.c.package_price).label("package_value"),
            func.count(tenders.c.winning_price).label("winning_priced"),
            func.sum(tenders.c.winning_price).label("winning_value"))
            .where(*conditions, tenders.c.publish_date.is_not(None))
            .group_by(day_expr).order_by(day_expr)).mappings().all()
        dimensions = {}
        for name, column in (("status", tenders.c.status), ("location", tenders.c.location),
                             ("investor_name", tenders.c.investor_name),
                             ("winning_contractor", tenders.c.winning_contractor),
                             ("selection_method", tenders.c.selection_method),
                             ("contract_type", tenders.c.contract_type)):
            entity = (tenders.c.investor_id if name == "investor_name" else
                      tenders.c.contractor_id if name == "winning_contractor" else None)
            fields = [column.label("value")]
            if entity is not None:
                fields.append(entity.label("entity_id"))
            statement = select(*fields, func.count().label("count"),
                func.count(tenders.c.package_price).label("priced"),
                func.sum(tenders.c.package_price).label("package_value"))
            statement = statement.where(*conditions, column.is_not(None), column != "")
            statement = statement.group_by(column, entity) if entity is not None else statement.group_by(column)
            rows = conn.execute(statement.order_by(func.count().desc(), column)
                .limit(10)).mappings().all()
            dimensions[name] = [{key: str(value) if isinstance(value, Decimal) else value
                                 for key, value in row.items()} for row in rows]
        related_codes = select(tenders.c.tender_code).where(*conditions)
        changes = conn.scalar(select(func.count()).select_from(tender_changes)
            .where(tender_changes.c.tender_code.in_(related_codes))) or 0
        plan_compatible = not results_only and all(item["field"] in {"publish_date", "investor_name"}
                              for item in filters)
        plan_count = None
        if plan_compatible:
            plan_conditions = _conditions(DATASETS["khlcnt"], filters)
            plan_count = conn.scalar(select(func.count()).select_from(plans)
                .where(*plan_conditions)) or 0
        comparison = _comparison(conn, raw_filters, results_only)
    buckets = {}
    for row in daily:
        if not row["day"]:
            continue
        try:
            key = _bucket(row["day"], period)
        except ValueError:
            continue
        bucket = buckets.setdefault(key, {"period": key, "tenders": 0, "results": 0,
            "priced": 0, "winning_priced": 0,
            "package_value": Decimal(0), "winning_value": Decimal(0)})
        bucket["tenders"] += row["tenders"]
        bucket["results"] += row["results"]
        bucket["priced"] += row["priced"]
        bucket["winning_priced"] += row["winning_priced"]
        bucket["package_value"] += row["package_value"] or 0
        bucket["winning_value"] += row["winning_value"] or 0
    trend = []
    for item in buckets.values():
        entry = {key: str(value) if isinstance(value, Decimal) else value
                 for key, value in item.items()}
        if not item["priced"]:
            entry["package_value"] = None
        if not item["winning_priced"]:
            entry["winning_value"] = None
        trend.append(entry)
    return {"period": period, "filters": raw_filters, "kpis": kpis,
        "khlcnt": {"count": plan_count, "compatible": plan_compatible},
        "changes": changes, "trend": trend, "dimensions": dimensions,
        "source": {"last_sync": latest, "sync_failures": failures,
                   "tender_count": kpis["tenders"], "priced_count": kpis["priced"]},
        "comparison": comparison}
