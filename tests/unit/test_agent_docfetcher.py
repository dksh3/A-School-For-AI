"""S7 tests: school_fetch_docs."""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.error
from collections.abc import Iterator
from pathlib import Path

import pytest

from core.agent import docfetcher
from core.agent.docfetcher import fetch_docs


@pytest.fixture
def worktree() -> Iterator[str]:
    """Isolated worktree via tempfile.mkdtemp (not tmp_path: OneDrive-safe)."""
    wt = tempfile.mkdtemp(prefix="school_docs_")
    try:
        yield wt
    finally:
        shutil.rmtree(wt, ignore_errors=True)


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(docfetcher, "_fetch_url", lambda url, timeout=5.0: text)


def _boom(url: str, timeout: float = 5.0) -> str:
    raise urllib.error.URLError("network unavailable")


def _patch_boom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docfetcher, "_fetch_url", _boom)


def _cache(wt: str) -> dict[str, object]:
    path = Path(wt) / ".school" / "agent" / "docs_cache.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TestFetchDocs:
    def test_network_unavailable_fail_open(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_boom(monkeypatch)
        r = fetch_docs(worktree, "how do pytest fixtures work")
        assert r.ok is False
        assert r.error is not None
        assert "fetch failed" in r.error
        assert r.cached is False
        assert r.content == ""

    def test_cache_hit_on_second_call(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_fetch(monkeypatch, "pytest fixtures share setup state between tests.")
        r1 = fetch_docs(worktree, "pytest fixtures")
        assert r1.ok is True
        assert r1.cached is False
        r2 = fetch_docs(worktree, "pytest fixtures")
        assert r2.ok is True
        assert r2.cached is True
        assert r2.source == "cache"
        assert "pytest fixtures" in r2.content

    def test_use_cache_false_refetches(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_fetch(monkeypatch, "FIRST")
        fetch_docs(worktree, "q1")
        _patch_fetch(monkeypatch, "SECOND")
        r = fetch_docs(worktree, "q1", use_cache=False)
        assert r.ok is True
        assert r.cached is False
        assert r.content == "SECOND"

    def test_large_content_skeletonized(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        big = "x" * 5000
        _patch_fetch(monkeypatch, big)
        r = fetch_docs(worktree, "big doc")
        assert r.ok is True
        assert r.tokens_saved > 0
        assert "[... " in r.content
        assert "tokens compressed" in r.content
        assert len(r.content) < 2000
        assert r.content.startswith(big[:200])
        assert r.content.endswith(big[-200:])

    def test_fallback_to_cache_on_fetch_failure(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_fetch(monkeypatch, "STALE BUT USABLE")
        fetch_docs(worktree, "q")
        _patch_boom(monkeypatch)
        r = fetch_docs(worktree, "q", use_cache=False)
        assert r.ok is True
        assert r.cached is True
        assert "STALE" in r.content

    def test_empty_query(self, worktree: str) -> None:
        r = fetch_docs(worktree, "")
        assert r.ok is False
        assert r.error == "empty query"
        r = fetch_docs(worktree, "   ")
        assert r.ok is False
        assert r.error == "empty query"

    def test_kill_switch(self, worktree: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOOL_DOCS", "0")
        r = fetch_docs(worktree, "anything")
        assert r.ok is True
        assert r.source == "disabled"
        assert r.content == ""
        assert r.cached is False
        assert r.tokens_saved == 0

    def test_cache_bounded_to_100(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_fetch(monkeypatch, "doc body")
        for i in range(105):
            r = fetch_docs(worktree, f"query-{i}")
            assert r.ok is True
        cache = _cache(worktree)
        assert len(cache) <= 100
        assert len(cache) == 100

    def test_observer_recorded_after_fetch(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_fetch(monkeypatch, "content")
        r = fetch_docs(worktree, "observed query")
        obs = Path(worktree) / ".school" / "agent" / "observations.jsonl"
        lines = obs.read_text(encoding="utf-8").splitlines()
        assert any("docs fetched: observed query" in ln for ln in lines)
        assert any('"research"' in ln for ln in lines)
        assert r.learnings is not None

    def test_observer_recorded_after_failed_fetch(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_boom(monkeypatch)
        fetch_docs(worktree, "doomed query")
        obs = Path(worktree) / ".school" / "agent" / "observations.jsonl"
        lines = obs.read_text(encoding="utf-8").splitlines()
        assert any("docs fetched: doomed query" in ln for ln in lines)

    def test_version_pinning_separate_cache_entries(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_fetch(monkeypatch, "VERSION-DOC")
        r1 = fetch_docs(worktree, "api", library="requests", version="2.31.0")
        r2 = fetch_docs(worktree, "api", library="requests", version="2.25.0")
        assert r1.ok is True and r2.ok is True
        assert r1.cached is False and r2.cached is False
        assert len(_cache(worktree)) == 2
        # same pinned version hits the cache
        r3 = fetch_docs(worktree, "api", library="requests", version="2.31.0")
        assert r3.cached is True
