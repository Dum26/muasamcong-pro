"""Cloud Logging-compatible JSON output without request bodies or credentials."""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit


def redact(value: str) -> str:
    secrets = [secret for name, secret in os.environ.items()
               if len(secret) >= 8 and (name.endswith(("_SECRET", "_TOKEN", "_KEY", "_PASSWORD"))
                                        or name == "DATABASE_URL")]
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        try:
            password = urlsplit(database_url).password
            if password and len(password) >= 8:
                secrets.extend((password, quote(password, safe="")))
        except ValueError:
            pass
    for secret in sorted(set(secrets), key=len, reverse=True):
        value = value.replace(secret, "[REDACTED]")
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        item = {"timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname, "message": redact(record.getMessage())}
        for name in ("event", "request_id", "route", "method", "status", "duration_ms"):
            value = getattr(record, name, None)
            if value is not None:
                item[name] = value
        if record.exc_info:
            item["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(item, ensure_ascii=False)


def configure_production_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level if level in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO",
                        handlers=[handler], force=True)
