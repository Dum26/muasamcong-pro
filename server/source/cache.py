"""Thread-safe TTL cache abstraction; replaceable by Redis without caller changes."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Protocol


class CacheBackend(Protocol):
    def get(self, key: str, *, allow_stale: bool = False) -> tuple[Any, bool] | None: ...
    def set(self, key: str, value: Any, ttl: int) -> None: ...
    def delete(self, key: str) -> None: ...


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float
    stale_until: float


class MemoryTTLCache:
    def __init__(self, max_items: int = 2048, stale_seconds: int = 3600):
        self.max_items, self.stale_seconds = max_items, stale_seconds
        self._items: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str, *, allow_stale: bool = False) -> tuple[Any, bool] | None:
        with self._lock:
            entry = self._items.get(key)
            if not entry:
                return None
            stamp = time.monotonic()
            stale = stamp > entry.expires_at
            if stale and stamp > entry.stale_until:
                self._items.pop(key, None)
                return None
            if stale and not allow_stale:
                return None
            self._items.move_to_end(key)
            return entry.value, stale

    def set(self, key: str, value: Any, ttl: int) -> None:
        stamp = time.monotonic()
        with self._lock:
            self._items[key] = _Entry(value, stamp + ttl,
                                      stamp + ttl + self.stale_seconds)
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
