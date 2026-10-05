"""Explicit result metadata so callers can distinguish stale/error/empty data."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class SourceResult:
    data: Any = None
    status: str = "success"
    source: str = "egp-public"
    fetched_at: str | None = None
    last_success_at: str | None = None
    cached: bool = False
    stale: bool = False
    partial: bool = False
    error: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)
