"""Environment configuration shared by local development and Cloud Run."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def environment() -> str:
    return os.environ.get("ENV", "development").strip().lower()


def production() -> bool:
    return environment() == "production" or bool(os.environ.get("K_SERVICE"))


def database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if value:
        if value.startswith("postgres://"):
            value = "postgresql+psycopg://" + value[len("postgres://"):]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://"):]
        if production() and not value.startswith("postgresql+psycopg://"):
            raise RuntimeError("Production requires a PostgreSQL DATABASE_URL.")
        return value
    if production():
        raise RuntimeError("Production requires DATABASE_URL (PostgreSQL).")
    return "sqlite:///" + str(ROOT / "data" / "muasamcong.db").replace("\\", "/")


def job_secret() -> str:
    return os.environ.get("JOB_SECRET", "")


APP_VERSION = "5.3.0"


def validate_production_config() -> None:
    """Fail before serving traffic; Cloud Run injects secrets as environment vars."""
    if not production():
        return
    database_url()
    if len(os.environ.get("SESSION_SECRET", "")) < 32:
        raise RuntimeError("Production requires SESSION_SECRET with at least 32 characters.")
    if len(job_secret()) < 32:
        raise RuntimeError("Production requires JOB_SECRET with at least 32 characters.")
    storage_backend()
    configured_url = os.environ.get("APP_BASE_URL") or os.environ.get("SITE_URL")
    if configured_url:
        from server.seo import site_origin
        if not site_origin().startswith("https://"):
            raise RuntimeError("Production APP_BASE_URL/SITE_URL must use HTTPS.")
    if ai_settings()["enabled"] and not ai_settings()["configured"]:
        raise RuntimeError("AI_ENABLED requires AI_PROVIDER, AI_MODEL and OPENAI_API_KEY.")


def log_level() -> str:
    return os.environ.get("LOG_LEVEL", "INFO").upper()


def _int_setting(name: str, default: int, minimum: int = 1,
                 maximum: int = 86400) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _float_setting(name: str, default: float, minimum: float = 0.1,
                   maximum: float = 1000.0) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def source_settings() -> dict:
    """Central reliability settings for the public procurement source."""
    return {
        "timeout_seconds": _int_setting("SOURCE_TIMEOUT_SECONDS", 30, 2, 120),
        "max_retries": _int_setting("SOURCE_MAX_RETRIES", 3, 0, 8),
        "requests_per_second": _float_setting(
            "SOURCE_REQUESTS_PER_SECOND", 1.5, 0.1, 20.0),
        "search_cache_ttl": _int_setting("SEARCH_CACHE_TTL_SECONDS", 120, 1),
        "tender_cache_ttl": _int_setting("TENDER_CACHE_TTL_SECONDS", 1800, 1),
        "result_cache_ttl": _int_setting("RESULT_CACHE_TTL_SECONDS", 900, 1),
        "document_cache_ttl": _int_setting("DOCUMENT_CACHE_TTL_SECONDS", 1800, 1),
        "sync_batch_size": _int_setting("SYNC_BATCH_SIZE", 10, 1, 100),
        "sync_max_concurrency": _int_setting("SYNC_MAX_CONCURRENCY", 2, 1, 10),
        "tender_stale_after": _int_setting(
            "TENDER_STALE_AFTER_SECONDS", 21600, 60, 604800),
        "circuit_failure_threshold": _int_setting(
            "SOURCE_CIRCUIT_FAILURE_THRESHOLD", 5, 2, 50),
        "circuit_cooldown_seconds": _int_setting(
            "SOURCE_CIRCUIT_COOLDOWN_SECONDS", 60, 5, 3600),
        "completed_job_retention_days": _int_setting(
            "SYNC_COMPLETED_RETENTION_DAYS", 14, 1, 365),
        "failed_job_retention_days": _int_setting(
            "SYNC_FAILED_RETENTION_DAYS", 45, 1, 730),
    }


def max_upload_bytes() -> int:
    try:
        mb = int(os.environ.get("MAX_USER_UPLOAD_MB", os.environ.get("MAX_UPLOAD_MB", "10")))
    except ValueError as exc:
        raise RuntimeError("MAX_UPLOAD_MB must be an integer.") from exc
    if not 1 <= mb <= 50:
        raise RuntimeError("MAX_UPLOAD_MB must be between 1 and 50.")
    return mb * 1024 * 1024


def max_document_download_bytes() -> int:
    return _int_setting("MAX_DOCUMENT_DOWNLOAD_MB", 25, 1, 100) * 1024 * 1024


def document_cache_days() -> int:
    return _int_setting("DOCUMENT_CACHE_DAYS", 30, 1, 365)


def inline_extraction_bytes() -> int:
    try:
        mb = int(os.environ.get("INLINE_EXTRACTION_MAX_MB", "3"))
    except ValueError as exc:
        raise RuntimeError("INLINE_EXTRACTION_MAX_MB must be an integer.") from exc
    if not 1 <= mb <= max_upload_bytes() // (1024 * 1024):
        raise RuntimeError("INLINE_EXTRACTION_MAX_MB must be between 1 and MAX_UPLOAD_MB.")
    return mb * 1024 * 1024


def storage_backend() -> str:
    backend = os.environ.get("STORAGE_BACKEND", "gcs" if production() else "local").strip().lower()
    if backend not in {"local", "gcs"}:
        raise RuntimeError("STORAGE_BACKEND must be local or gcs.")
    if production() and backend != "gcs":
        raise RuntimeError("Production document storage requires GCS.")
    if backend == "gcs" and not os.environ.get("GCS_BUCKET", "").strip():
        raise RuntimeError("GCS_BUCKET is required for GCS storage.")
    return backend


def ai_settings() -> dict:
    enabled = os.environ.get("AI_ENABLED", "false").strip().lower() == "true"
    provider = os.environ.get("AI_PROVIDER", "").strip().lower()
    model = os.environ.get("AI_MODEL", "").strip()
    configured = enabled and provider == "openai" and bool(model) and bool(os.environ.get("OPENAI_API_KEY"))
    try:
        limit = max(1, int(os.environ.get("AI_REQUESTS_PER_MINUTE", "10")))
    except ValueError:
        limit = 10
    return {"enabled": enabled, "configured": configured, "provider": provider,
            "model": model, "requests_per_minute": limit}
