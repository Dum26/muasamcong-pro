# Document Center 2.0 (MuaSamCong Pro 4.7)

Open `/app/documents` after signing in. The workspace combines e-GP document metadata with each account's private uploads. The e-GP sync discovers metadata only; it never downloads files in bulk. A person can fetch a source file, extract its text, compare observed versions, or explicitly copy it into their private AI workspace.

## Data and storage

- `tender_source_documents` keeps source metadata, current version, fetch/extraction state, SHA-256 and the storage key. `document_versions` stores observed metadata and file revisions. Legacy rows remain valid; new groups are keyed by tender code and source URL so two HSMT files in the same package do not share a version history.
- `source_document_text` keeps extraction chunks and citation labels per version. `user_document_state` records reads per account; `document_notification_seen` deduplicates followed-tender alerts. Existing private `documents` and `document_text` tables remain separate and owner-scoped.
- `STORAGE_BACKEND=local` is for local development. Set `STORAGE_BACKEND=gcs` and `GCS_BUCKET` for Cloud Run. The database owns metadata; the storage provider owns bytes. No Windows-specific path is used for source files.
- `MAX_USER_UPLOAD_MB` (default 10) limits private uploads. `MAX_DOCUMENT_DOWNLOAD_MB` (default 25) limits source fetches. `DOCUMENT_CACHE_DAYS` (default 30) records the intended cache retention period; automatic eviction is not enabled, so retained versions stay available for comparison.

## Discovery and versions

The tender detail sync calls `_sync_documents` with the source's document metadata. Source URL and tender identify an observed document; changes to published metadata create a version. Downloading computes SHA-256. Re-fetching the same hash reuses the earlier version; a different hash creates a new one. Historical versions and records removed at the source remain in the database. A complete source list is required before a missing URL is marked `deleted_at_source`.

Source fetches go through the Data Sync request manager with its rate limit, timeout and circuit breaker. Fetch accepts only HTTPS URLs on the configured e-GP host, rejects redirects and oversized or unsupported files, and never trusts a storage path supplied by the browser. A database claim prevents concurrent workers from fetching the same document at once. Source text extraction is cached by version. Existing PDF, DOCX, XLSX, CSV and TXT extraction is reused; scanned PDFs need OCR to yield text. ZIP files are not extracted.

## API and access

All Document Center routes require an authenticated account. Private uploads, their text and downloads are restricted to their owner; source records follow the application's authenticated source-data policy.

| Route | Purpose |
| --- | --- |
| `GET /api/document-center` | Paginated catalog; `q`, `source`, `tender_code`, `plan_code`, `type`, `status`, `sort`, `page`, `page_size` |
| `GET /api/document-center/export` | Export matching metadata as XLSX |
| `GET /api/document-center/{upload|egp}/{id}` | Detail, extracted text and version history |
| `GET /api/document-center/compare?first=&second=` | Compare two owned uploads |
| `POST /api/document-center/egp/{id}/fetch` | Explicit source download; body `{"force": true}` checks for a changed file |
| `POST /api/document-center/egp/{id}/extract` | Extract and cache current version text |
| `GET /api/document-center/egp/{id}/download` | Download cached source file |
| `GET /api/document-center/egp/{id}/preview` | Inline cached PDF, or attachment for other types |
| `GET /api/document-center/egp/{id}/compare?first=&second=` | Metadata and raw extracted-text diff |
| `POST /api/document-center/egp/{id}/ai-import` | Explicitly copy a cached source file into the caller's private AI documents |

Source fetch, extraction, preview, download and version compare are audited without logging document contents. Followed tenders receive deduplicated alerts for newly discovered source documents and observed revisions. The existing Automation Engine's `NEW_DOCUMENT` trigger remains available.

## Current boundaries

Source metadata depends on what e-GP publishes and what the existing tender-detail fetch returns. A missing or protected source file shows a fetch error; no document metadata is invented. Raw diff requires both versions to have extracted text. The UI previews PDFs directly and shows extracted text for other formats; it does not render DOCX/XLSX pixel-perfect. Source download is capped by configuration and handled in memory after bounded streaming from e-GP, so increase the cap cautiously. Automatic retention cleanup and bulk AI/download queues are not enabled.

## Verification

Run `python -m unittest discover -s tests -p "test_*.py" -q` and `npm test`. The Document Center tests cover discovery, version/hash deduplication, two same-type files, private ownership, search, pagination, source validation, extraction, AI import isolation, notifications and HTTP routes.
