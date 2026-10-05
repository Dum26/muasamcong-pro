# Performance 4.9: local measurements and operating limits

Measurements below are from an isolated temporary SQLite database on the development machine. The benchmark scripts do not call e-GP or use production accounts. These numbers are evidence for the measured paths, not Cloud Run or PostgreSQL service-level guarantees.

## Before and after: Document Center search

`python -m tools.bench_document_catalog` seeds 100 private text documents, queries `needle`, returns a 100-row page, and repeats five times. SQLAlchemy counts all SQL statements during each catalog call.

| Version | SQL statements/request | p50 | p95 |
| --- | ---: | ---: | ---: |
| Before batched snippets | 102 | 37.78 ms | 40.03 ms |
| After batched snippets | 3 | 5.86 ms | 11.81 ms |

The former path fetched a text snippet separately for every row. The new path obtains one matching chunk per document with a window query, separately for uploaded and e-GP documents. The public-document path is covered by existing Document Center regression tests. This remains a simple `LIKE` search, not an indexed full-text implementation.

## Search baseline

`python -m tools.bench_search 10000` seeds 10,000 tenders in a temporary SQLite database. One run before and one run after exact-code routing yielded 36.2 ms → 27.8 ms for exact code, 27.4 ms → 27.9 ms for text, and 5.7 ms → 6.1 ms for a price filter. Single-run timings are noisy; the change only narrows exact IB/PL queries to the relevant entity type. Public search remains capped at 100 rows per page; fuzzy matching runs only as a bounded fallback.

The same fixture measured the existing analytics overview at 31.7 ms in a later run. Its aggregates are already computed in SQL; no materialized view or new analytics cache was added without a measured bottleneck.

## Concurrent local HTTP smoke test

`python -m tools.load_test --levels 10,25,50,100 --requests 100` started the actual HTTP handler against a temporary SQLite DB and exercised health, authenticated search, pagination, tender detail, watchlist, analytics, document list, notifications, and automation list. Source fetch and AI requests were excluded. Local rate limits were raised for this controlled test only.

| Concurrent clients | Requests | p50 | p95 | p99 | RPS | 5xx/timeout |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 100 | 58.02 ms | 154.55 ms | 216.02 ms | 144.04 | 0 |
| 25 | 100 | 57.78 ms | 551.13 ms | 555.68 ms | 93.30 | 0 |
| 50 | 100 | 113.13 ms | 1029.15 ms | 1072.18 ms | 85.75 | 0 |
| 100 | 100 | 182.42 ms | 1554.20 ms | 2048.42 ms | 47.01 | 0 |

This short smoke test is not a soak test. Throughput falls at high concurrency on local SQLite; production performance must be measured separately on PostgreSQL/Cloud Run. Do not extrapolate these RPS figures to e-GP or AI workloads.

A longer local pass with `--levels 10 --requests 1000` completed 1,000 requests at p50 67.69 ms, p95 224.09 ms, 114.98 RPS and 0 observed 5xx/timeouts. Its duration was about nine seconds, so it still does not establish long-term memory stability.

## Changes and controls

- PostgreSQL pool defaults to 3 persistent connections plus 2 overflow per instance, with a 10-second checkout timeout. `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, and `DB_POOL_TIMEOUT` are bounded. At `max-instances=4`, the default app-side ceiling is 20 database connections, excluding other services and admin tools.
- `/api/admin/performance` and `/admin/performance` show bounded, per-instance request samples, p50/p95, 5xx count, average SQL queries per route, and slow routes. Route identifiers and query strings are removed; raw SQL and request bodies are never stored. `SLOW_REQUEST_MS` controls sanitized slow-request logging.
- `/ready` checks only the local DB. `/health` stays lightweight and does not query e-GP.
- Static CSS/JS/images/fonts have a short 5-minute cache with ETag/304. HTML and private APIs remain no-store. Gzip is used only when the client requests it for sizeable text/JSON/JS/CSS; downloads and PDFs are not recompressed.
- Synchronous report export keeps its prior 5,000-row maximum by default and can be lowered with `EXPORT_SYNC_MAX_ROWS`; it refuses larger reports rather than retaining unbounded workbooks in memory.
- Existing frontend search already aborts stale requests and caps page size. No virtualization was added without evidence that 100-row pages lag.

## Deployment guidance and remaining limits

Start Cloud Run with a modest concurrency such as 20, `max-instances=4`, and a database connection budget that includes other workloads; tune only after PostgreSQL load tests. Keep source rate limiting and background-job limits enabled. Set memory/CPU and timeout from measured document/export workloads, not this SQLite smoke test. Cloud Run scale-out does not share the in-memory search cache or performance samples; durable data remains in the database. Redis is not required or implemented. A production PostgreSQL `EXPLAIN` review, long soak test, and Cloud Run load test remain necessary before claiming production latency targets.
