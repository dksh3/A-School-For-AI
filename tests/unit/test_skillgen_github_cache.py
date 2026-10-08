"""1A-2Z Phase 2: bounded TTL cache for GitHub discovery data.

A fake monotonic clock makes expiry deterministic; no wall-clock sleeps.
"""

from __future__ import annotations

import pytest

from core.skillgen.github.cache import TTLCache, shared_cache


class FakeClock:
    """Deterministic monotonic clock driven by advance()."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


class TestSetAndGet:
    def test_set_then_get_returns_value(self, clock: FakeClock) -> None:
        cache = TTLCache(ttl=10, clock=clock)
        cache.set("search:pdf skill:8", [{"name": "repo"}])
        assert cache.get("search:pdf skill:8") == [{"name": "repo"}]
        assert len(cache) == 1

    def test_missing_key_returns_none(self, clock: FakeClock) -> None:
        cache = TTLCache(ttl=10, clock=clock)
        assert cache.get("nope") is None
        assert len(cache) == 0


class TestExpiry:
    def test_value_survives_until_ttl_then_expires(self, clock: FakeClock) -> None:
        cache = TTLCache(ttl=10, clock=clock)
        cache.set("k", "v")
        clock.advance(9.5)
        assert cache.get("k") == "v"
        clock.advance(0.5)
        assert cache.get("k") is None
        assert len(cache) == 0
        assert cache.keys == []


class TestBoundedEviction:
    def test_oldest_entry_is_evicted_at_max(self, clock: FakeClock) -> None:
        cache = TTLCache(ttl=60, max_entries=3, clock=clock)
        for key in ("a", "b", "c"):
            cache.set(key, key)
        cache.set("d", "d")
        assert len(cache) == 3
        assert cache.keys == ["b", "c", "d"]
        assert cache.get("a") is None
        assert cache.get("b") == "b"

    def test_get_refreshes_recency_before_eviction(self, clock: FakeClock) -> None:
        cache = TTLCache(ttl=60, max_entries=2, clock=clock)
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.get("a") == 1
        cache.set("c", 3)
        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3

    @pytest.mark.parametrize("bounds", [{"ttl": 0}, {"max_entries": 0}])
    def test_nonpositive_bounds_disable_storage(
        self, clock: FakeClock, bounds: dict[str, int]
    ) -> None:
        cache = TTLCache(clock=clock, **bounds)
        cache.set("k", "v")
        assert cache.get("k") is None
        assert len(cache) == 0


class TestCacheLifecycle:
    def test_clear_removes_every_entry(self, clock: FakeClock) -> None:
        cache = TTLCache(ttl=60, clock=clock)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0
        assert cache.keys == []
        assert cache.get("a") is None

    def test_shared_cache_is_singleton_and_defaults_are_positive(self) -> None:
        assert shared_cache() is shared_cache()
        assert isinstance(shared_cache(), TTLCache)
        default_cache = TTLCache()
        assert default_cache.ttl > 0
        assert default_cache.max_entries > 0
