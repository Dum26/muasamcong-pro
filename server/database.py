"""Portable PostgreSQL/SQLite schema and versioned database initialization."""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (JSON, Boolean, Column, ForeignKey, Index, Integer, LargeBinary,
                        MetaData, Numeric, String, Table, Text, UniqueConstraint, create_engine,
                        delete, event, func, insert, inspect, select, text, update)
from sqlalchemy.engine import Engine

from server.config import database_url, production

metadata = MetaData()
SCHEMA_VERSION = 18


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


schema_migrations = Table("schema_migrations", metadata,
    Column("version", Integer, primary_key=True), Column("applied_at", String(40), nullable=False))
users = Table("users", metadata,
    Column("id", String(32), primary_key=True),
    Column("email", String(320), unique=True, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("role", String(16), nullable=False, default="user"),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("last_login_at", String(40)),
    Column("is_active", Boolean, nullable=False, default=True))
sessions = Table("user_sessions", metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False, index=True),
    Column("created_at", String(40), nullable=False),
    Column("expires_at", String(40), nullable=False))
followed_tenders = Table("followed_tenders", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("tender_code", String(50), nullable=False),
    Column("tender_type", String(12), nullable=False),
    Column("title", Text, nullable=False, default=""),
    Column("investor", Text, nullable=False, default=""),
    Column("status", String(160), nullable=False, default=""),
    Column("deadline", String(60), nullable=False, default=""),
    Column("priority", String(20), nullable=False, default="Trung bình"),
    Column("internal_status", String(40), nullable=False, default="Mới"),
    Column("payload", JSON, nullable=False, default=dict),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("last_checked_at", String(40)),
    UniqueConstraint("user_id", "tender_code", name="uq_followed_user_code"),
    Index("ix_followed_user_updated", "user_id", "updated_at"))
user_notes = Table("user_notes", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("tender_code", String(50), nullable=False),
    Column("note", Text, nullable=False, default=""),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    UniqueConstraint("user_id", "tender_code", name="uq_note_user_code"))
tags = Table("tags", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("name", String(30), nullable=False),
    UniqueConstraint("user_id", "name", name="uq_tag_user_name"))
tender_tags = Table("tender_tags", metadata,
    Column("tender_id", String(32), ForeignKey("followed_tenders.id"), primary_key=True),
    Column("tag_id", String(32), ForeignKey("tags.id"), primary_key=True))
saved_searches = Table("saved_searches", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("name", String(80), nullable=False),
    Column("query", Text, nullable=False, default=""),
    Column("filters", JSON, nullable=False, default=dict),
    Column("is_watch_enabled", Boolean, nullable=False, default=False),
    Column("pinned", Boolean, nullable=False, default=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("last_run_at", String(40)),
    UniqueConstraint("user_id", "name", name="uq_saved_user_name"),
    Index("ix_saved_user_watch", "user_id", "is_watch_enabled"))
search_history = Table("search_history", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("name", String(80), nullable=False),
    Column("query", Text, nullable=False, default=""),
    Column("filters", JSON, nullable=False, default=dict),
    Column("result_count", Integer),
    Column("pinned", Boolean, nullable=False, default=False),
    Column("created_at", String(40), nullable=False),
    Index("ix_history_user_created", "user_id", "created_at"))
tender_change_history = Table("tender_change_history", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("tender_code", String(50), nullable=False),
    Column("field_name", String(80), nullable=False),
    Column("old_value", Text, nullable=False, default=""),
    Column("new_value", Text, nullable=False, default=""),
    Column("detected_at", String(40), nullable=False),
    Index("ix_changes_user_code", "user_id", "tender_code"))
user_notifications = Table("user_notifications", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("type", String(40), nullable=False),
    Column("title", String(200), nullable=False),
    Column("message", Text, nullable=False),
    Column("tender_code", String(50)),
    Column("is_read", Boolean, nullable=False, default=False),
    Column("created_at", String(40), nullable=False),
    Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"))
download_history = Table("download_history", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("filename", String(200), nullable=False),
    Column("type", String(50), nullable=False),
    Column("status", String(30), nullable=False),
    Column("size", Integer, nullable=False, default=0),
    Column("error", String(300), nullable=False, default=""),
    Column("created_at", String(40), nullable=False),
    Index("ix_downloads_user_created", "user_id", "created_at"))
download_files = Table("download_files", metadata,
    Column("download_id", String(32), ForeignKey("download_history.id"), primary_key=True),
    Column("data", LargeBinary, nullable=False),
    Column("expires_at", String(40), nullable=False))
saved_search_seen = Table("saved_search_seen", metadata,
    Column("search_id", String(32), ForeignKey("saved_searches.id"), primary_key=True),
    Column("tender_code", String(50), primary_key=True))
job_runs = Table("job_runs", metadata,
    Column("id", String(32), primary_key=True),
    Column("kind", String(50), nullable=False),
    Column("status", String(30), nullable=False),
    Column("details", Text, nullable=False, default=""),
    Column("created_at", String(40), nullable=False))

# Version 2: private document workflow. Object bytes stay in local/GCS storage,
# while extracted chunks and user-owned analysis history stay in the database.
documents = Table("documents", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("tender_code", String(50)),
    Column("filename", String(200), nullable=False),
    Column("original_filename", String(200), nullable=False),
    Column("mime_type", String(120), nullable=False),
    Column("size", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("storage_key", String(200), nullable=False),
    Column("status", String(24), nullable=False),
    Column("scan_likely", Boolean, nullable=False, default=False),
    Column("error", String(300), nullable=False, default=""),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Index("ix_documents_user_created", "user_id", "created_at"),
    Index("ix_documents_user_tender", "user_id", "tender_code"))
document_text = Table("document_text", metadata,
    Column("id", String(32), primary_key=True),
    Column("document_id", String(32), ForeignKey("documents.id"), nullable=False),
    Column("source_id", String(100), nullable=False),
    Column("label", String(240), nullable=False),
    Column("page_number", Integer),
    Column("section", String(200)),
    Column("sheet_name", String(120)),
    Column("row_start", Integer),
    Column("row_end", Integer),
    Column("text", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    Index("ix_doc_text_document", "document_id"),
    UniqueConstraint("document_id", "source_id", name="uq_doc_text_source"))
document_analyses = Table("document_analyses", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("document_id", String(32), ForeignKey("documents.id"), nullable=False),
    Column("related_document_id", String(32), ForeignKey("documents.id")),
    Column("analysis_type", String(40), nullable=False),
    Column("question", Text, nullable=False, default=""),
    Column("result_json", JSON, nullable=False),
    Column("model", String(120), nullable=False),
    Column("status", String(24), nullable=False, default="completed"),
    Column("created_at", String(40), nullable=False),
    Index("ix_analyses_user_document", "user_id", "document_id", "created_at"))
ai_conversations = Table("ai_conversations", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("document_id", String(32), ForeignKey("documents.id")),
    Column("title", String(200), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Index("ix_ai_conversations_user", "user_id", "created_at"))
ai_messages = Table("ai_messages", metadata,
    Column("id", String(32), primary_key=True),
    Column("conversation_id", String(32), ForeignKey("ai_conversations.id"), nullable=False),
    Column("role", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    Index("ix_ai_messages_conversation", "conversation_id", "created_at"))
ai_usage = Table("ai_usage", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("model", String(120), nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("estimated_cost", String(40)),
    Column("operation", String(40), nullable=False),
    Column("created_at", String(40), nullable=False),
    Index("ix_ai_usage_user_created", "user_id", "created_at"))

# Version 3 records actual extraction attempts for admin failure/latency metrics.
document_processing = Table("document_processing", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("document_id", String(32), nullable=False),
    Column("status", String(24), nullable=False),
    Column("duration_ms", Integer),
    Column("created_at", String(40), nullable=False),
    Index("ix_doc_processing_user_created", "user_id", "created_at"))

# Version 4: public e-GP observations shared across accounts. Private notes,
# follows and document bytes remain in their existing user-scoped tables.
investors = Table("investors", metadata,
    Column("id", String(32), primary_key=True),
    Column("name", String(320), nullable=False),
    Column("search_text", Text, nullable=False, default=""),
    Column("normalized_name", String(320), nullable=False, unique=True),
    Column("identifier", String(50)), Column("address", Text),
    Column("first_seen_at", String(40), nullable=False),
    Column("last_seen_at", String(40), nullable=False))
procuring_entities = Table("procuring_entities", metadata,
    Column("id", String(32), primary_key=True),
    Column("name", String(320), nullable=False),
    Column("search_text", Text, nullable=False, default=""),
    Column("normalized_name", String(320), nullable=False, unique=True),
    Column("identifier", String(50)), Column("address", Text),
    Column("first_seen_at", String(40), nullable=False),
    Column("last_seen_at", String(40), nullable=False))
contractors = Table("contractors", metadata,
    Column("id", String(32), primary_key=True),
    Column("name", String(320), nullable=False),
    Column("search_text", Text, nullable=False, default=""),
    Column("normalized_name", String(320), nullable=False),
    Column("tax_code", String(50)), Column("identity_key", String(380), nullable=False, unique=True),
    Column("address", Text),
    Column("first_seen_at", String(40), nullable=False),
    Column("last_seen_at", String(40), nullable=False))
plans = Table("plans", metadata,
    Column("plan_code", String(50), primary_key=True),
    Column("title", Text, nullable=False, default=""),
    Column("search_text", Text, nullable=False, default=""),
    Column("investor_id", String(32), ForeignKey("investors.id")),
    Column("investor_name", String(320)),
    Column("package_price", Numeric(24, 2)), Column("currency", String(12)),
    Column("publish_date", String(40)), Column("source_url", Text),
    Column("first_seen_at", String(40), nullable=False),
    Column("last_seen_at", String(40), nullable=False),
    Index("ix_plans_investor", "investor_id"),
    Index("ix_plans_publish", "publish_date"))
tenders = Table("tenders", metadata,
    Column("tender_code", String(50), primary_key=True),
    Column("khlcnt_code", String(50), ForeignKey("plans.plan_code")),
    Column("title", Text, nullable=False, default=""),
    Column("search_text", Text, nullable=False, default=""),
    Column("investor_id", String(32), ForeignKey("investors.id")),
    Column("investor_name", String(320)),
    Column("procuring_entity_id", String(32), ForeignKey("procuring_entities.id")),
    Column("procuring_entity_name", String(320)),
    Column("contractor_id", String(32), ForeignKey("contractors.id")),
    Column("winning_contractor", String(320)),
    Column("package_price", Numeric(24, 2)), Column("winning_price", Numeric(24, 2)),
    Column("currency", String(12)),
    Column("publish_date", String(40)), Column("bid_closing_date", String(40)),
    Column("result_date", String(40)), Column("status", String(160)),
    Column("selection_method", String(160)), Column("contract_type", String(160)),
    Column("location", String(320)), Column("result_status", String(160)),
    Column("source_url", Text), Column("raw_hash", String(64)),
    Column("first_seen_at", String(40), nullable=False),
    Column("last_seen_at", String(40), nullable=False),
    Column("last_synced_at", String(40)),
    Column("sync_error", String(300)),
    Column("last_success_at", String(40)), Column("last_error_at", String(40)),
    Column("sync_status", String(24), nullable=False, default="stale"),
    Column("sync_error_code", String(40)),
    Index("ix_tenders_plan", "khlcnt_code"),
    Index("ix_tenders_investor", "investor_id"),
    Index("ix_tenders_contractor", "contractor_id"),
    Index("ix_tenders_publish", "publish_date"),
    Index("ix_tenders_deadline", "bid_closing_date"),
    Index("ix_tenders_status", "status"))
tender_snapshots = Table("tender_snapshots", metadata,
    Column("id", String(32), primary_key=True),
    Column("tender_code", String(50), ForeignKey("tenders.tender_code"), nullable=False),
    Column("snapshot_json", JSON, nullable=False),
    Column("snapshot_hash", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("tender_code", "version", name="uq_tender_snapshot_version"),
    Index("ix_tender_snapshots_code_created", "tender_code", "created_at"))
tender_changes = Table("tender_changes", metadata,
    Column("id", String(32), primary_key=True),
    Column("tender_code", String(50), ForeignKey("tenders.tender_code"), nullable=False),
    Column("field_name", String(80), nullable=False),
    Column("old_value", JSON), Column("new_value", JSON),
    Column("detected_at", String(40), nullable=False),
    Index("ix_tender_changes_code_date", "tender_code", "detected_at"))
tender_events = Table("tender_events", metadata,
    Column("id", String(32), primary_key=True),
    Column("tender_code", String(50), ForeignKey("tenders.tender_code"), nullable=False),
    Column("event_type", String(50), nullable=False),
    Column("label", String(200), nullable=False),
    Column("event_at", String(40), nullable=False),
    Column("details", JSON, nullable=False, default=dict),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("tender_code", "event_type", "event_at", name="uq_tender_event"),
    Index("ix_tender_events_code_date", "tender_code", "event_at"))
tender_source_documents = Table("tender_source_documents", metadata,
    Column("id", String(32), primary_key=True),
    Column("tender_code", String(50), ForeignKey("tenders.tender_code"), nullable=False),
    Column("document_name", String(240), nullable=False),
    Column("document_type", String(80)), Column("source_url", Text, nullable=False),
    Column("published_at", String(40)), Column("file_size", Integer),
    Column("content_hash", String(64)), Column("metadata_hash", String(64)),
    Column("mime_type", String(120)), Column("storage_key", String(200)),
    Column("status", String(24), nullable=False, default="metadata_only"),
    Column("error", String(300)), Column("downloaded_at", String(40)),
    Column("document_group_id", String(32), nullable=False),
    Column("version", Integer, nullable=False),
    Column("first_seen_at", String(40), nullable=False),
    Column("last_seen_at", String(40), nullable=False),
    UniqueConstraint("tender_code", "source_url", name="uq_tender_document_url"),
    Index("ix_tender_documents_code", "tender_code"))
document_versions = Table("document_versions", metadata,
    Column("id", String(32), primary_key=True),
    Column("document_group_id", String(32), nullable=False),
    Column("version", Integer, nullable=False),
    Column("storage_key", String(200)), Column("source_url", Text),
    Column("content_hash", String(64)), Column("metadata_hash", String(64)),
    Column("metadata_json", JSON),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("document_group_id", "version", name="uq_document_group_version"))
source_document_text = Table("source_document_text", metadata,
    Column("id", String(32), primary_key=True),
    Column("version_id", String(32), ForeignKey("document_versions.id"), nullable=False),
    Column("source_id", String(100), nullable=False),
    Column("label", String(240), nullable=False),
    Column("page_number", Integer), Column("section", String(200)),
    Column("sheet_name", String(120)), Column("row_start", Integer),
    Column("row_end", Integer), Column("text", Text, nullable=False),
    Column("text_hash", String(64), nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("version_id", "source_id", name="uq_source_doc_text"),
    Index("ix_source_doc_text_version", "version_id"))
user_document_state = Table("user_document_state", metadata,
    Column("user_id", String(32), ForeignKey("users.id"), primary_key=True),
    Column("document_id", String(32), ForeignKey("tender_source_documents.id"), primary_key=True),
    Column("last_viewed_at", String(40), nullable=False),
    Column("is_read", Boolean, nullable=False, default=True))
document_notification_seen = Table("document_notification_seen", metadata,
    Column("user_id", String(32), ForeignKey("users.id"), primary_key=True),
    Column("document_id", String(32), ForeignKey("tender_source_documents.id"), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("created_at", String(40), nullable=False))
background_jobs = Table("background_jobs", metadata,
    Column("id", String(32), primary_key=True),
    Column("job_type", String(50), nullable=False),
    Column("entity_type", String(50), nullable=False),
    Column("entity_id", String(100), nullable=False),
    Column("status", String(24), nullable=False),
    Column("priority", String(12), nullable=False, default="normal"),
    Column("attempts", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False, default=3),
    Column("last_error", String(300)),
    Column("next_retry_at", String(40)),
    Column("locked_at", String(40)), Column("locked_by", String(80)),
    Column("created_at", String(40), nullable=False),
    Column("started_at", String(40)), Column("finished_at", String(40)),
    Index("ix_background_jobs_status_retry", "status", "next_retry_at"),
    Index("ix_background_jobs_priority_created", "priority", "created_at"),
    Index("ix_background_jobs_entity", "entity_type", "entity_id"),
    Index("ix_background_jobs_type_entity_status", "job_type", "entity_id", "status"))
alert_rules = Table("alert_rules", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("rule_type", String(40), nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("threshold_days", Integer),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("user_id", "rule_type", name="uq_alert_user_type"))
user_preferences = Table("user_preferences", metadata,
    Column("user_id", String(32), ForeignKey("users.id"), primary_key=True),
    Column("notifications", JSON, nullable=False, default=dict),
    Column("table_view", JSON, nullable=False, default=dict),
    Column("updated_at", String(40), nullable=False))
audit_logs = Table("audit_logs", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id")),
    Column("action", String(60), nullable=False),
    Column("entity_type", String(50)), Column("entity_id", String(100)),
    Column("created_at", String(40), nullable=False),
    Index("ix_audit_user_created", "user_id", "created_at"))

# Version 5: private BI configurations. Public source observations remain in
# the version 4 tender tables; report definitions and layouts are user-scoped.
saved_reports = Table("saved_reports", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("name", String(120), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("dataset", String(32), nullable=False),
    Column("columns_json", JSON, nullable=False),
    Column("filters_json", JSON, nullable=False),
    Column("group_by_json", JSON, nullable=False),
    Column("metrics_json", JSON, nullable=False),
    Column("sort_json", JSON, nullable=False),
    Column("pinned", Boolean, nullable=False, default=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Index("ix_saved_reports_user_updated", "user_id", "updated_at"))
report_runs = Table("report_runs", metadata,
    Column("id", String(32), primary_key=True),
    Column("report_id", String(32), ForeignKey("saved_reports.id")),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("status", String(24), nullable=False),
    Column("row_count", Integer, nullable=False, default=0),
    Column("duration_ms", Integer),
    Column("created_at", String(40), nullable=False),
    Column("error_message", String(300)),
    Index("ix_report_runs_user_created", "user_id", "created_at"))
user_dashboards = Table("user_dashboards", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("name", String(120), nullable=False),
    Column("is_default", Boolean, nullable=False, default=False),
    Column("layout_json", JSON, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Index("ix_user_dashboards_user_updated", "user_id", "updated_at"))

# Version 6: private automation definitions, executions and deduplicated actions.
automation_rules = Table("automation_rules", metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("name", String(120), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("is_enabled", Boolean, nullable=False, default=False),
    Column("trigger_type", String(40), nullable=False),
    Column("conditions_json", JSON, nullable=False),
    Column("actions_json", JSON, nullable=False),
    Column("run_frequency", String(24), nullable=False, default="manual"),
    Column("priority", String(12), nullable=False, default="normal"),
    Column("last_run_at", String(40)), Column("next_run_at", String(40)),
    Column("lock_until", String(40)),
    Column("cursor_json", JSON), Column("deleted_at", String(40)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Index("ix_automation_due", "is_enabled", "next_run_at", "priority"),
    Index("ix_automation_user_trigger", "user_id", "trigger_type", "created_at"))
automation_runs = Table("automation_runs", metadata,
    Column("id", String(32), primary_key=True),
    Column("automation_id", String(32), ForeignKey("automation_rules.id"), nullable=False),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("started_at", String(40), nullable=False),
    Column("finished_at", String(40)),
    Column("status", String(24), nullable=False),
    Column("matched_count", Integer, nullable=False, default=0),
    Column("action_count", Integer, nullable=False, default=0),
    Column("error_message", String(300)),
    Column("duration_ms", Integer),
    Index("ix_automation_runs_user_started", "user_id", "started_at"),
    Index("ix_automation_runs_rule_status", "automation_id", "status"))
automation_events = Table("automation_events", metadata,
    Column("id", String(32), primary_key=True),
    Column("automation_id", String(32), ForeignKey("automation_rules.id"), nullable=False),
    Column("run_id", String(32), ForeignKey("automation_runs.id")),
    Column("user_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("entity_type", String(24), nullable=False),
    Column("entity_id", String(100), nullable=False),
    Column("trigger", String(40), nullable=False),
    Column("action", String(40), nullable=False),
    Column("status", String(24), nullable=False),
    Column("dedup_key", String(64), nullable=False, unique=True),
    Column("details_json", JSON, nullable=False, default=dict),
    Column("created_at", String(40), nullable=False),
    Index("ix_automation_events_run", "run_id", "created_at"),
    Index("ix_automation_events_user_entity", "user_id", "entity_id"))

# Version 7: durable, source-aware data synchronization orchestration.
sync_sources = Table("sync_sources", metadata,
    Column("id", String(32), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("kind", String(40), nullable=False),
    Column("is_enabled", Boolean, nullable=False, default=True),
    Column("schedule_minutes", Integer, nullable=False, default=30),
    Column("config_json", JSON, nullable=False, default=dict),
    Column("last_run_at", String(40)), Column("next_run_at", String(40)),
    Column("next_request_at", String(40)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Index("ix_sync_sources_due", "is_enabled", "next_run_at"))
sync_runs = Table("sync_runs", metadata,
    Column("id", String(32), primary_key=True),
    Column("source_id", String(32), ForeignKey("sync_sources.id"), nullable=False),
    Column("requested_by", String(32), ForeignKey("users.id")),
    Column("trigger", String(24), nullable=False),
    Column("mode", String(24), nullable=False),
    Column("status", String(24), nullable=False),
    Column("discovered_count", Integer, nullable=False, default=0),
    Column("queued_count", Integer, nullable=False, default=0),
    Column("processed_count", Integer, nullable=False, default=0),
    Column("success_count", Integer, nullable=False, default=0),
    Column("failed_count", Integer, nullable=False, default=0),
    Column("cursor_json", JSON), Column("error_message", String(300)),
    Column("started_at", String(40)), Column("finished_at", String(40)),
    Column("created_at", String(40), nullable=False),
    Index("ix_sync_runs_source_created", "source_id", "created_at"),
    Index("ix_sync_runs_status_started", "status", "started_at"))
sync_run_items = Table("sync_run_items", metadata,
    Column("id", String(32), primary_key=True),
    Column("run_id", String(32), ForeignKey("sync_runs.id"), nullable=False),
    Column("job_id", String(32), ForeignKey("background_jobs.id")),
    Column("entity_type", String(24), nullable=False),
    Column("entity_id", String(100), nullable=False),
    Column("status", String(24), nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("error_message", String(300)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    UniqueConstraint("run_id", "entity_type", "entity_id", name="uq_sync_run_entity"),
    Index("ix_sync_items_run_status", "run_id", "status"))
sync_checkpoints = Table("sync_checkpoints", metadata,
    Column("source_id", String(32), ForeignKey("sync_sources.id"), primary_key=True),
    Column("stream", String(40), primary_key=True),
    Column("cursor_json", JSON), Column("last_success_at", String(40)),
    Column("last_error", String(300)), Column("updated_at", String(40), nullable=False))

# Version 8: persisted source-health transitions. Rolling metrics stay in memory.
source_health_events = Table("source_health_events", metadata,
    Column("id", String(32), primary_key=True),
    Column("source_name", String(80), nullable=False),
    Column("event_type", String(40), nullable=False),
    Column("status", String(24), nullable=False),
    Column("details_json", JSON, nullable=False, default=dict),
    Column("created_at", String(40), nullable=False),
    Index("ix_source_health_source_created", "source_name", "created_at"))
search_metrics_daily = Table("search_metrics_daily", metadata,
    Column("day", String(10), primary_key=True),
    Column("kind", String(20), primary_key=True),
    Column("searches", Integer, nullable=False, default=0),
    Column("zero_results", Integer, nullable=False, default=0),
    Column("latency_total_ms", Integer, nullable=False, default=0),
    Column("cache_hits", Integer, nullable=False, default=0))

# Version 17: observations and review decisions, separate from source records.
data_quality_issues = Table("data_quality_issues", metadata,
    Column("id", String(32), primary_key=True),
    Column("identity_key", String(64), nullable=False, unique=True),
    Column("entity_type", String(32), nullable=False),
    Column("entity_id", String(100), nullable=False),
    Column("field_name", String(80)),
    Column("rule_code", String(80), nullable=False),
    Column("severity", String(12), nullable=False),
    Column("status", String(20), nullable=False, default="open"),
    Column("message", String(400), nullable=False),
    Column("details_json", JSON, nullable=False, default=dict),
    Column("detected_at", String(40), nullable=False),
    Column("last_detected_at", String(40), nullable=False),
    Column("resolved_at", String(40)),
    Column("resolution_type", String(40)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Index("ix_dq_issue_status_severity", "status", "severity"),
    Index("ix_dq_issue_entity", "entity_type", "entity_id"),
    Index("ix_dq_issue_rule_date", "rule_code", "detected_at"))
duplicate_candidates = Table("duplicate_candidates", metadata,
    Column("id", String(32), primary_key=True),
    Column("entity_type", String(32), nullable=False),
    Column("entity_id_a", String(100), nullable=False),
    Column("entity_id_b", String(100), nullable=False),
    Column("confidence", Numeric(4, 3), nullable=False),
    Column("reason_json", JSON, nullable=False, default=dict),
    Column("status", String(20), nullable=False, default="pending"),
    Column("created_at", String(40), nullable=False),
    Column("reviewed_at", String(40)),
    UniqueConstraint("entity_type", "entity_id_a", "entity_id_b", name="uq_dq_candidate_pair"),
    Index("ix_dq_candidate_status_confidence", "status", "confidence"))
data_fix_log = Table("data_fix_log", metadata,
    Column("id", String(32), primary_key=True),
    Column("entity_type", String(32), nullable=False),
    Column("entity_id", String(100), nullable=False),
    Column("field_name", String(80), nullable=False),
    Column("old_value", Text), Column("new_value", Text),
    Column("rule_code", String(80), nullable=False),
    Column("auto", Boolean, nullable=False, default=False),
    Column("actor_id", String(32), ForeignKey("users.id")),
    Column("created_at", String(40), nullable=False),
    Index("ix_dq_fix_entity", "entity_type", "entity_id"))
entity_aliases = Table("entity_aliases", metadata,
    Column("id", String(32), primary_key=True),
    Column("entity_type", String(32), nullable=False),
    Column("entity_id", String(100), nullable=False),
    Column("alias", String(320), nullable=False),
    Column("normalized_alias", String(320), nullable=False),
    Column("source", String(40), nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("entity_type", "entity_id", "normalized_alias", name="uq_dq_entity_alias"))
entity_merges = Table("entity_merges", metadata,
    Column("id", String(32), primary_key=True),
    Column("entity_type", String(32), nullable=False),
    Column("source_id", String(32), nullable=False),
    Column("target_id", String(32), nullable=False),
    Column("candidate_id", String(32), nullable=False),
    Column("actor_id", String(32), ForeignKey("users.id"), nullable=False),
    Column("source_snapshot_json", JSON, nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("entity_type", "source_id", name="uq_dq_merge_source"),
    Index("ix_dq_merge_target", "entity_type", "target_id"))
data_quality_runs = Table("data_quality_runs", metadata,
    Column("id", String(32), primary_key=True),
    Column("run_type", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("cursor_json", JSON, nullable=False, default=dict),
    Column("started_at", String(40)), Column("finished_at", String(40)),
    Column("entities_scanned", Integer, nullable=False, default=0),
    Column("issues_found", Integer, nullable=False, default=0),
    Column("issues_resolved", Integer, nullable=False, default=0),
    Column("created_at", String(40), nullable=False),
    Index("ix_dq_runs_status_created", "status", "created_at"))


def pool_options(url: str) -> dict:
    """Keep Cloud Run's per-instance PostgreSQL connection budget bounded."""
    if not url.startswith(("postgresql://", "postgresql+")):
        return {}
    def bounded(name: str, default: int, low: int, high: int) -> int:
        try:
            return max(low, min(int(os.environ.get(name, default)), high))
        except ValueError:
            return default
    return {"pool_size": bounded("DB_POOL_SIZE", 3, 1, 20),
            "max_overflow": bounded("DB_MAX_OVERFLOW", 2, 0, 20),
            "pool_timeout": bounded("DB_POOL_TIMEOUT", 10, 1, 120),
            "pool_recycle": bounded("DB_POOL_RECYCLE", 1800, 60, 7200)}


class Database:
    def __init__(self, url: str, *, migrate_schema: bool | None = None):
        self.url = url
        if url.startswith("sqlite:///") and ":memory:" not in url:
            Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        args = {"check_same_thread": False} if url.startswith("sqlite:") else {}
        self.engine: Engine = create_engine(url, pool_pre_ping=True,
            connect_args=args, **pool_options(url))
        from server.performance import after_sql, before_sql
        event.listen(self.engine, "before_cursor_execute", before_sql)
        event.listen(self.engine, "after_cursor_execute", after_sql)
        if url.startswith("sqlite:"):
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_connection, _connection_record):
                dbapi_connection.execute("PRAGMA foreign_keys=ON")
        if migrate_schema is None:
            migrate_schema = (not production()) or (os.environ.get("AUTO_MIGRATE") == "1")
        try:
            if migrate_schema:
                self.migrate()
            else:
                self.require_current_schema()
        except Exception:
            self.engine.dispose()
            raise

    def schema_version(self) -> int:
        if not inspect(self.engine).has_table("schema_migrations"):
            return 0
        with self.engine.connect() as conn:
            return conn.scalar(select(func.max(schema_migrations.c.version))) or 0

    def require_current_schema(self) -> None:
        version = self.schema_version()
        if version != SCHEMA_VERSION:
            raise RuntimeError(f"Database schema is version {version}; run migration to version {SCHEMA_VERSION} before startup.")

    def migrate(self) -> None:
        """Create or extend the schema in place; never drop existing account data."""
        schema_migrations.create(self.engine, checkfirst=True)
        with self.engine.begin() as conn:
            version = conn.scalar(select(func.max(schema_migrations.c.version))) or 0
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"Database schema version {version} is newer than this application.")
        if 1 <= version < 8:
            # Add columns before create_all sees indexes that depend on them.
            # This also supports an older database whose version 7 tables are
            # being restored after an interrupted migration.
            inspector = inspect(self.engine)
            table_names = set(inspector.get_table_names())
            existing = ({column["name"] for column in inspector.get_columns("background_jobs")}
                        if "background_jobs" in table_names else set())
            tender_existing = ({column["name"] for column in inspector.get_columns("tenders")}
                               if "tenders" in table_names else set())
            with self.engine.begin() as conn:
                job_columns = {
                    "priority": "VARCHAR(12) NOT NULL DEFAULT 'normal'",
                    "max_attempts": "INTEGER NOT NULL DEFAULT 3",
                    "locked_at": "VARCHAR(40)", "locked_by": "VARCHAR(80)",
                }
                tender_columns = {
                    "last_success_at": "VARCHAR(40)", "last_error_at": "VARCHAR(40)",
                    "sync_status": "VARCHAR(24) NOT NULL DEFAULT 'stale'",
                    "sync_error_code": "VARCHAR(40)",
                }
                for name, definition in job_columns.items():
                    if "background_jobs" in table_names and name not in existing:
                        conn.execute(text(f"ALTER TABLE background_jobs ADD COLUMN {name} {definition}"))
                for name, definition in tender_columns.items():
                    if "tenders" in table_names and name not in tender_existing:
                        conn.execute(text(f"ALTER TABLE tenders ADD COLUMN {name} {definition}"))
        if version < 1:
            metadata.create_all(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=1, applied_at=now()))
        if version < 2:
            metadata.create_all(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=2, applied_at=now()))
        if version < 3:
            metadata.create_all(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=3, applied_at=now()))
        if version < 4:
            metadata.create_all(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=4, applied_at=now()))
        if version < 5:
            metadata.create_all(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=5, applied_at=now()))
        if version < 6:
            metadata.create_all(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=6, applied_at=now()))
        if version < 7:
            metadata.create_all(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=7, applied_at=now()))
        if version < 8:
            metadata.create_all(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_background_jobs_priority_created ON background_jobs (priority, created_at)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_background_jobs_entity ON background_jobs (entity_type, entity_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenders_last_synced ON tenders (last_synced_at)"))
                conn.execute(insert(schema_migrations).values(version=8, applied_at=now()))
        if version < 9:
            columns = {column["name"] for column in inspect(self.engine).get_columns("sync_sources")}
            with self.engine.begin() as conn:
                if "next_request_at" not in columns:
                    conn.execute(text("ALTER TABLE sync_sources ADD COLUMN next_request_at VARCHAR(40)"))
                conn.execute(insert(schema_migrations).values(version=9, applied_at=now()))
        if version < 10:
            with self.engine.begin() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_background_jobs_type_entity_status ON background_jobs (job_type, entity_id, status)"))
                conn.execute(insert(schema_migrations).values(version=10, applied_at=now()))
        if version < 11:
            from server.search_engine import normalize_search
            with self.engine.begin() as conn:
                for table in ("tenders", "plans", "investors", "procuring_entities", "contractors"):
                    columns = {item["name"] for item in inspect(self.engine).get_columns(table)}
                    if "search_text" not in columns:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN search_text TEXT NOT NULL DEFAULT ''"))
                for table, key, fields in (("tenders", "tender_code", ("title", "investor_name", "procuring_entity_name", "winning_contractor", "location")),
                                           ("plans", "plan_code", ("title", "investor_name")),
                                           ("investors", "id", ("name", "identifier")),
                                           ("procuring_entities", "id", ("name", "identifier")),
                                           ("contractors", "id", ("name", "tax_code"))):
                    rows = conn.execute(text(f"SELECT {key}, {', '.join(fields)} FROM {table}")).mappings()
                    for row in rows:
                        value = normalize_search(" ".join(str(row[field] or "") for field in fields))
                        conn.execute(text(f"UPDATE {table} SET search_text=:value WHERE {key}=:code"),
                                     {"value": value, "code": row[key]})
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenders_last_seen ON tenders (last_seen_at)"))
                conn.execute(insert(schema_migrations).values(version=11, applied_at=now()))
        if version < 12:
            search_metrics_daily.create(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=12, applied_at=now()))
        if version < 13:
            with self.engine.begin() as conn:
                if self.engine.dialect.name == "postgresql":
                    for table in ("tenders", "plans", "investors", "procuring_entities", "contractors"):
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_search_fts ON {table} USING GIN (to_tsvector('simple', search_text))"))
                conn.execute(insert(schema_migrations).values(version=13, applied_at=now()))
        if version < 14:
            with self.engine.begin() as conn:
                for table in ("tender_source_documents", "document_versions"):
                    columns = {item["name"] for item in inspect(self.engine).get_columns(table)}
                    if "metadata_hash" not in columns:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN metadata_hash VARCHAR(64)"))
                conn.execute(insert(schema_migrations).values(version=14, applied_at=now()))
        if version < 15:
            with self.engine.begin() as conn:
                columns = {item["name"] for item in inspect(self.engine).get_columns("tender_source_documents")}
                definitions = {"mime_type": "VARCHAR(120)", "storage_key": "VARCHAR(200)",
                    "status": "VARCHAR(24) NOT NULL DEFAULT 'metadata_only'", "error": "VARCHAR(300)",
                    "downloaded_at": "VARCHAR(40)"}
                for name, definition in definitions.items():
                    if name not in columns:
                        conn.execute(text(f"ALTER TABLE tender_source_documents ADD COLUMN {name} {definition}"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_source_docs_group ON tender_source_documents (document_group_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_source_docs_seen ON tender_source_documents (first_seen_at)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_source_docs_status ON tender_source_documents (status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_source_docs_type ON tender_source_documents (document_type)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_source_docs_hash ON tender_source_documents (content_hash)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_private_docs_hash ON documents (user_id, sha256)"))
            source_document_text.create(self.engine, checkfirst=True)
            user_document_state.create(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=15, applied_at=now()))
        if version < 16:
            with self.engine.begin() as conn:
                columns = {item["name"] for item in inspect(self.engine).get_columns("document_versions")}
                if "metadata_json" not in columns:
                    conn.execute(text("ALTER TABLE document_versions ADD COLUMN metadata_json JSON"))
            document_notification_seen.create(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=16, applied_at=now()))
        if version < 17:
            for table in (data_quality_issues, duplicate_candidates, data_fix_log,
                          entity_aliases, data_quality_runs):
                table.create(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=17, applied_at=now()))
        if version < 18:
            entity_merges.create(self.engine, checkfirst=True)
            with self.engine.begin() as conn:
                conn.execute(insert(schema_migrations).values(version=18, applied_at=now()))

    def health(self) -> bool:
        return self.schema_version() == SCHEMA_VERSION


_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    global _db
    url = database_url()
    with _db_lock:
        if _db is None or _db.url != url:
            if _db is not None:
                _db.engine.dispose()
            _db = Database(url)
        return _db


def reset_db() -> None:
    """Test helper: drop the cached engine, never database tables."""
    global _db
    with _db_lock:
        if _db is not None:
            _db.engine.dispose()
            _db = None


def migrate_command() -> None:
    from server.config import validate_production_config
    validate_production_config()
    database = Database(database_url(), migrate_schema=True)
    try:
        database.require_current_schema()
        print(f"Schema migration complete: version {SCHEMA_VERSION}")
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["migrate"]:
        raise SystemExit("Usage: python -m server.database migrate")
    migrate_command()
