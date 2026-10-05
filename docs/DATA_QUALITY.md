# Data Quality Engine 4.8

The engine observes source records and stores reviewable findings. It does not merge entities or hide search results automatically. The admin workspace is `/admin/data-quality` (also shown within `/admin`). Ordinary signed-in users can only read the small quality status of a tender or source document they are viewing.

## Model

Migration 17 adds `data_quality_issues`, `duplicate_candidates`, `data_fix_log`, `entity_aliases`, and `data_quality_runs`; migration 18 adds `entity_merges`. Both leave existing tenders, plans, entities, snapshots, documents and account data in place. An issue identity is the hash of entity type, entity ID, rule and field. Repeated scans update the same issue; an issue no longer observed becomes `auto_resolved` without deleting its history. Ignored issues stay ignored while the condition persists. Admin review decisions write an audit event.

The registry in `server/data_quality/rules.py` defines stable codes and severities. Validators in `validators.py` report missing titles, invalid code/date/price, deadline before publish, price comparison, encoding damage, partial or stale records, sync failure, document hash/fetch issues, orphan relations and same-hash source documents. Strong-identifier duplicate candidates use matching contractor tax codes or investor/procurer identifiers; names alone never trigger a merge. Unicode normalization is used as a comparison key and does not overwrite original text. An entity status endpoint provides a transparent score breakdown: completeness is the proportion of six tender or four document fields present; validity subtracts 35/25/10/3 points per critical/error/warning/info finding; freshness is zero when a stale rule is open; consistency is 50 when a broken relation or document duplicate is open. The displayed score is the average of these four components and remains unavailable before a full scan has checked the record.

Plan validation covers title, code, date, price, stale observations and investor relation. The overview also reports the numerator and denominator of tenders with a nonnegative numeric package price; downstream analytics must display their own sample counts rather than silently treating missing prices as zero.

## Scanning

`POST /api/admin/data-quality/scan` queues `incremental` or `full`. Each call to `POST /internal/jobs/run-data-quality` processes at most `DATA_QUALITY_BATCH_SIZE` tender, plan or source-document records. The internal route requires the existing `X-Job-Secret`; an admin may process one batch from the UI. A Cloud Scheduler job can call the internal route repeatedly. A full scan is never run during a page request. Incremental scans use the last completed run as a watermark. A final pass checks persisted source-health transitions and creates pending duplicate candidates from exact strong identifiers. Name/address similarity does not trigger merges.

Admin APIs: `GET /api/admin/data-quality/summary`, `/issues`, `/issues/{id}`, `/duplicates`, `/runs`; `POST /scan`, `/scan/process`, `/issues/{id}/{review|resolve|ignore}`, `/duplicates/{id}/{not_duplicate|ignore|merge}`. The merge endpoint requires a target ID from the candidate pair and exact matching nonempty tax code or identifier. It reassigns relations transactionally, retains the source row, stores its snapshot in `entity_merges`, creates a searchable alias and audit entry. A later sync of the old identity resolves to the retained target. Issue lists are paginated and filtered. User-facing status is `GET /api/data-quality/tenders/{code}` or `/documents/{id}`. The overview's “records without open issues” rate appears only after a complete full scan and is a coverage metric, not a claim about contractor or investor merit. All admin mutations require an authenticated admin and pass the existing origin and rate-limit checks.

An admin-only, explicit safe fix is available for `TENDER_EXTRA_WHITESPACE`: `POST /api/admin/data-quality/issues/{id}/fix`. It trims and collapses whitespace in the title, updates the derived search text and records the exact old/new title in `data_fix_log`; `POST /api/admin/data-quality/fixes/{id}/revert` restores it only when the title has not changed again. The admin UI offers this action only on the matching issue and exposes an immediate Undo button. No price, deadline, code or legal identity is auto-fixed.

## Configuration

`.env.example` documents `DATA_QUALITY_ENABLED`, `DATA_QUALITY_BATCH_SIZE`, `STALE_TENDER_DAYS`, `STALE_DOCUMENT_DAYS`, `DUPLICATE_CONFIDENCE_THRESHOLD`, and `OUTLIER_DETECTION_ENABLED`. Outlier scoring is off by default. Thresholds are centralized in the rule settings.

## Current boundaries

Manual merge is restricted to exact strong-identifier matches; ambiguous names remain review candidates, never automatic merges. The overview reports counts of persisted findings; it is not a claim that every record has been fully validated before a scan completes. Parser schema warnings use persisted source-health transitions. `SOURCE_CONFLICT` compares the cache to its latest matching snapshot for selected fields; direct comparison of two independent authoritative feeds is not possible with the current source model. Duplicate detection caps its candidate pass to 10,000 entity rows per type. Cloud Scheduler must be configured separately for unattended progress.

Run `python -m unittest -q tests.test_data_quality tests.test_data_quality_http` for focused checks and `python -m unittest discover -s tests -p "test_*.py" -q` for the whole backend.
