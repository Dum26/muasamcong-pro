"""Authenticated automation API for the existing HTTP server."""
from __future__ import annotations

import re
from http import HTTPStatus
from urllib.parse import parse_qs

from server.automation_actions import ACTION_TYPES
from server.automation_conditions import (BOOLEAN_FIELDS, DATE_FIELDS,
    NUMBER_FIELDS, TEXT_FIELDS)
from server.automation_engine import (FREQUENCIES, TRIGGERS, delete_rule,
    automation_analytics, duplicate_rule, get_rule, list_events, list_rules, list_runs, run_rule,
    preview_rule, save_rule, set_enabled)

RULE = re.compile(r"^/api/automations/([0-9a-f]{32})$")
RULE_ACTION = re.compile(r"^/api/automations/([0-9a-f]{32})/(test|run|enable|pause|duplicate|delete|runs)$")
RUN_EVENTS = re.compile(r"^/api/automations/runs/([0-9a-f]{32})/events$")


def _error(handler, exc: Exception) -> None:
    handler._json({"error": str(exc)}, HTTPStatus.NOT_FOUND if isinstance(exc, LookupError)
                  else HTTPStatus.BAD_REQUEST)


def handle_get(handler, parsed) -> bool:
    path = parsed.path
    if not path.startswith("/api/automations"):
        return False
    user_id = handler._current_user()["id"]
    try:
        if path == "/api/automations/schema":
            handler._json({"triggers": TRIGGERS, "frequencies": list(FREQUENCIES),
                "actions": sorted(ACTION_TYPES),
                "fields": {"text": sorted(TEXT_FIELDS), "number": sorted(NUMBER_FIELDS),
                           "date": sorted(DATE_FIELDS), "boolean": sorted(BOOLEAN_FIELDS)}})
            return True
        if path == "/api/automations":
            query = parse_qs(parsed.query)
            one = lambda key: str((query.get(key) or [""])[0])[:100]
            items = list_rules(user_id, q=one("q"), status=one("status"),
                               trigger=one("trigger"), last_run=one("last_run"))
            runs = list_runs(user_id)
            handler._json({"items": items, "summary": {
                "active": sum(bool(item["is_enabled"]) for item in items),
                "paused": sum(not item["is_enabled"] for item in items),
                "recent_runs": len(runs),
                "failures": sum(bool(row["error_message"]) for row in runs)}})
            return True
        if path == "/api/automations/runs":
            handler._json({"items": list_runs(user_id)})
            return True
        if path == "/api/automations/analytics":
            query = parse_qs(parsed.query)
            raw_days = (query.get("days") or ["14"])[0]
            handler._json(automation_analytics(user_id, int(raw_days)))
            return True
        match = RUN_EVENTS.fullmatch(path)
        if match:
            handler._json({"items": list_events(user_id, match.group(1))})
            return True
        match = RULE_ACTION.fullmatch(path)
        if match and match.group(2) == "runs":
            handler._json({"items": list_runs(user_id, match.group(1))})
            return True
        match = RULE.fullmatch(path)
        if match:
            rule = get_rule(user_id, match.group(1))
            if rule is None:
                raise LookupError("Không tìm thấy rule của tài khoản này.")
            handler._json(rule)
            return True
    except (ValueError, TypeError, LookupError) as exc:
        _error(handler, exc)
        return True
    return False


def handle_post(handler, path: str, body: dict) -> bool:
    if not path.startswith("/api/automations"):
        return False
    user_id = handler._current_user()["id"]
    try:
        if path == "/api/automations/preview":
            handler._json(preview_rule(user_id, body))
            return True
        if path == "/api/automations":
            handler._json(save_rule(user_id, body), HTTPStatus.CREATED)
            return True
        match = RULE_ACTION.fullmatch(path)
        if match:
            rule_id, action = match.groups()
            if action == "test":
                handler._json(run_rule(user_id, rule_id, dry_run=True))
            elif action == "run":
                handler._json(run_rule(user_id, rule_id))
            elif action == "enable":
                handler._json(set_enabled(user_id, rule_id, True))
            elif action == "pause":
                handler._json(set_enabled(user_id, rule_id, False))
            elif action == "duplicate":
                handler._json(duplicate_rule(user_id, rule_id), HTTPStatus.CREATED)
            elif action == "delete":
                if not delete_rule(user_id, rule_id):
                    raise LookupError("Không tìm thấy rule của tài khoản này.")
                handler._json({"ok": True})
            else:
                return False
            return True
        match = RULE.fullmatch(path)
        if match:
            handler._json(save_rule(user_id, body, match.group(1)))
            return True
    except (ValueError, TypeError, LookupError) as exc:
        _error(handler, exc)
        return True
    return False
