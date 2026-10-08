"""Bounded TTL cache for GitHub discovery (Phase 2).

Avoids repeat API calls for search results, repository metadata, trees, and
skill files. In-memory only: tokens and secrets are NEVER cached, and a
restart starts fresh (no stale data masquerading as current state). Bounded
by max entries; oldest entries are evicted first.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

DEFAULT_TTL_S = float(os.environ.get("SCHOOL_SKILLGEN_GITHUB_CACHE_TTL", "900") or 900)
DEFAULT_MAX_ENTRIES = int(os.environ.get("SCHOOL_SKILLGEN_GITHUB_CACHE_MAX", "200") or 200)


class TTLCache:
    """Bounded time-to-live cache keyed by strings (values are data only)."""

    def __init__(
        self,
        ttl: float | None = None,
        max_entries: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl = DEFAULT_TTL_S if ttl is None else ttl
        self.max_entries = DEFAULT_MAX_ENTRIES if max_entries is None else max_entries
        self._clock = clock
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if self.max_entries <= 0 or self.ttl <= 0:
            return
        self._store[key] = (self._clock() + self.ttl, value)
        self._store.move_to_end(key)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    @property
    def keys(self) -> list[str]:
        return list(self._store)


# Shared process-level cache (safe: read-only data, no credentials).
_SHARED = TTLCache()


def shared_cache() -> TTLCache:
    return _SHARED


__all__ = ["DEFAULT_TTL_S", "TTLCache", "shared_cache"]
