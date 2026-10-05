"""Small, read-only production status for administrators."""

import os

from server.config import APP_VERSION, production, storage_backend


def snapshot() -> dict:
    from server.database import get_db
    from server.document_storage import get_storage
    from server.performance import snapshot as performance_snapshot
    from server.source.request_manager import get_request_manager

    result = {"environment": "production" if production() else "development",
              "version": APP_VERSION, "build_sha": os.environ.get("GIT_SHA", "")[:40]}
    try:
        result["database"] = "ready" if get_db().health() else "schema_outdated"
    except Exception:
        result["database"] = "unavailable"
    try:
        storage = get_storage()
        result["storage"] = ("ready" if storage.bucket.exists() else "unavailable") if storage_backend() == "gcs" else "local"
    except Exception:
        result["storage"] = "unavailable"
    try:
        metrics = get_request_manager().metrics()
        result["source"] = metrics.get("status", "unknown") if metrics.get("request_count") else "no_samples"
    except Exception:
        result["source"] = "unavailable"
    try:
        metrics = performance_snapshot()
        result["queue_length"] = metrics["queue_length"]
        result["recent_5xx"] = metrics["error_count_5xx"]
        result["request_count"] = metrics["request_count"]
    except Exception:
        result.update(queue_length=None, recent_5xx=None, request_count=None)
    result["scope"] = "this_instance_for_request_metrics"
    return result
