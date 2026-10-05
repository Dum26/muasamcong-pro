"""Run after migration with production env: python -m server.production_check."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from server.config import production, validate_production_config


def checks() -> list[tuple[str, bool]]:
    results = []
    try:
        validate_production_config()
        results.append(("production configuration", production()))
    except (RuntimeError, ValueError):
        results.append(("production configuration", False))
    url = os.environ.get("APP_BASE_URL") or os.environ.get("SITE_URL", "")
    parsed = urlparse(url)
    results.append(("public HTTPS URL", parsed.scheme == "https" and bool(parsed.netloc)))
    results.append(("debug disabled", os.environ.get("LOG_LEVEL", "INFO").upper() != "DEBUG"))
    if os.environ.get("REACT_FRONTEND_ENABLED") == "1":
        from server.config import ROOT
        results.append(("React production build", (ROOT / "frontend" / "dist" / "index.html").is_file()))
    try:
        from server.database import get_db
        results.append(("current database schema", get_db().health()))
    except Exception:
        results.append(("current database schema", False))
    try:
        from server.document_storage import get_storage
        storage = get_storage()
        results.append(("GCS bucket access", bool(storage.bucket.exists())))
    except Exception:
        results.append(("GCS bucket access", False))
    return results


def main() -> int:
    results = checks()
    for label, passed in results:
        print(f"{'PASS' if passed else 'FAIL'} {label}")
    if all(passed for _, passed in results):
        print("PRODUCTION READY")
        return 0
    print("NOT READY")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
