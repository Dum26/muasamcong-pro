"""Offline, reproducible catalog benchmark; never contacts the e-GP source."""
from __future__ import annotations

import json
import os
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event, insert

from server.auth import register
from server.database import document_text, documents, get_db, now, reset_db
from server.document_center import catalog


def run(records: int = 100, page_size: int = 100, iterations: int = 5) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        url = "sqlite:///" + (Path(folder) / "bench.db").as_posix()
        with patch.dict(os.environ, {"DATABASE_URL": url, "ENV": "development"}):
            reset_db()
            user_id = register("bench@example.test", "safe-long-password-123")["id"]
            stamp = now()
            with get_db().engine.begin() as conn:
                for index in range(records):
                    doc_id = f"{index + 1:032x}"
                    conn.execute(insert(documents).values(id=doc_id, user_id=user_id,
                        filename=f"file-{index}.txt", original_filename=f"file-{index}.txt",
                        mime_type="text/plain", size=16, sha256="a" * 64,
                        storage_key=f"benchmark/{index}", status="ready",
                        created_at=stamp, updated_at=stamp))
                    conn.execute(insert(document_text).values(id=f"{index + 1 + records:032x}",
                        document_id=doc_id, source_id="body", label="Body",
                        text=f"needle document {index}", created_at=stamp))
            query_counts, elapsed = [], []
            for _ in range(iterations):
                count = 0

                def before_cursor(*_args):
                    nonlocal count
                    count += 1

                event.listen(get_db().engine, "before_cursor_execute", before_cursor)
                try:
                    started = time.perf_counter()
                    result = catalog(user_id, source="upload", query="needle",
                                     page_size=page_size)
                    elapsed.append((time.perf_counter() - started) * 1000)
                    query_counts.append(count)
                    assert result["total"] == records
                    assert len(result["items"]) == min(records, page_size)
                finally:
                    event.remove(get_db().engine, "before_cursor_execute", before_cursor)
            reset_db()
    times = sorted(elapsed)
    return {"records": records, "page_size": page_size, "iterations": iterations,
            "queries": query_counts, "p50_ms": round(statistics.median(times), 2),
            "p95_ms": round(times[min(len(times)-1, int(.95 * len(times)))], 2)}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
