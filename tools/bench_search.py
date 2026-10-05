"""Synthetic local search benchmark; never touches the configured database."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from time import perf_counter

from sqlalchemy import insert

from server.database import get_db, reset_db, tenders
from server.search_engine import search
from server.bi_analytics import overview


def main(count: int = 10_000) -> None:
    with tempfile.TemporaryDirectory() as folder:
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "sqlite:///" + (Path(folder) / "benchmark.db").as_posix()
        reset_db()
        try:
            engine = get_db().engine
            for start in range(0, count, 1000):
                with engine.begin() as conn:
                    conn.execute(insert(tenders), [{
                        "tender_code": f"IB26{n:08d}", "title": f"Gói thiết bị y tế {n}",
                        "search_text": f"goi thiet bi y te {n} benh vien a",
                        "investor_name": "Bệnh viện A", "publish_date": "2026-09-20",
                        "package_price": n * 1000, "first_seen_at": "2026-09-20",
                        "last_seen_at": "2026-09-20"}
                        for n in range(start, min(start + 1000, count))])
            for label, query in (("exact", {"q": f"IB26{count-1:08d}"}),
                                 ("text", {"q": "thiet bi y te", "kind": "tender"}),
                                 ("filtered", {"kind": "tender", "price_min": str(count * 500)})):
                started = perf_counter()
                result = search(**query)
                print(f"{count:,} rows | {label}: {(perf_counter()-started)*1000:.1f} ms | {result['total']} hits")
            started = perf_counter()
            overview()
            print(f"{count:,} rows | analytics overview: {(perf_counter()-started)*1000:.1f} ms")
        finally:
            reset_db()
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10_000)
