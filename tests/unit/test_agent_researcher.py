"""S7 tests: school_research."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from core.agent.observer import observe
from core.agent.researcher import research

SEEDS = [
    "widget factory output increased",
    "widgets are produced in factories",
    "production line setup documented",
    "factory machines require maintenance",
]


@pytest.fixture
def worktree_factory() -> Iterator[Callable[[], str]]:
    """Factory of isolated worktrees via tempfile.mkdtemp (not tmp_path)."""
    created: list[str] = []

    def _make() -> str:
        wt = tempfile.mkdtemp(prefix="school_research_")
        created.append(wt)
        return wt

    try:
        yield _make
    finally:
        for wt in created:
            shutil.rmtree(wt, ignore_errors=True)


@pytest.fixture
def worktree(worktree_factory: Callable[[], str]) -> str:
    """Isolated worktree via tempfile.mkdtemp (not tmp_path: OneDrive-safe)."""
    return worktree_factory()


def _seed(wt: str, texts: list[str]) -> None:
    for text in texts:
        observe(wt, text, category="research")


class TestResearch:
    def test_research_basic(self, worktree: str) -> None:
        r = research(worktree, "how does routing work")
        assert r.ok is True
        assert "routing" in r.query
        assert isinstance(r.learnings, str)

    def test_research_rejects_empty(self, worktree: str) -> None:
        r = research(worktree, "")
        assert r.ok is False
        assert r.error == "empty query"

    def test_research_kill_switch(self, worktree: str, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_RESEARCH", "0")
        r = research(worktree, "anything")
        assert r.ok is True
        assert r.learnings == "research disabled"
        assert r.findings == []
        assert r.citations == []
        assert r.source == "disabled"

    def test_research_logs_to_observer(self, worktree: str) -> None:
        research(worktree, "test query")
        obs_file = Path(worktree) / ".school" / "agent" / "observations.jsonl"
        assert obs_file.exists()


class TestResearchCitations:
    def test_citations_present_when_cite_true(self, worktree: str) -> None:
        r = research(worktree, "test-driven teaching", cite=True)
        assert r.ok is True
        assert len(r.citations) > 0

    def test_citation_fields_complete(self, worktree: str) -> None:
        r = research(worktree, "test-driven teaching")
        assert r.citations
        ids = []
        for citation in r.citations:
            assert set(citation) == {"id", "title", "url", "relevance"}
            assert isinstance(citation["id"], int)
            assert citation["id"] >= 1
            assert isinstance(citation["title"], str) and citation["title"]
            assert isinstance(citation["url"], str) and citation["url"]
            assert 0.0 <= citation["relevance"] <= 1.0
            ids.append(citation["id"])
        assert ids == sorted(ids) and len(set(ids)) == len(ids)

    def test_internal_findings_cite_observations(self, worktree: str) -> None:
        _seed(worktree, ["widget factory output increased"])
        r = research(worktree, "widget factory")
        assert r.ok is True
        assert any(f["source"] == "internal" for f in r.findings)
        assert any(c["url"] == "internal://observations" for c in r.citations)
        assert r.source in {"internal", "cache", "hybrid"}

    def test_synthesized_findings_cite_query_hash(self, worktree: str) -> None:
        r = research(worktree, "quantum basket weaving")
        assert r.ok is True
        assert all(f["source"] == "synthesized" for f in r.findings)
        assert all(c["url"].startswith("synthesized://") for c in r.citations)

    def test_cite_false_returns_no_citations(self, worktree: str) -> None:
        r = research(worktree, "widget factory", cite=False)
        assert r.ok is True
        assert r.citations == []
        assert r.findings


class TestResearchFindings:
    def test_findings_have_confidence_scores(self, worktree: str) -> None:
        r = research(worktree, "how does routing work")
        assert r.findings
        for finding in r.findings:
            assert set(finding) == {"claim", "confidence", "source"}
            assert 0.0 <= finding["confidence"] <= 1.0
            assert finding["source"] in {"internal", "synthesized"}

    def test_depth_quick_fewer_findings_than_deep(
        self, worktree_factory: Callable[[], str]
    ) -> None:
        quick_wt = worktree_factory()
        deep_wt = worktree_factory()
        _seed(quick_wt, SEEDS)
        _seed(deep_wt, SEEDS)
        quick = research(quick_wt, "widget factory", depth="quick")
        deep = research(deep_wt, "widget factory", depth="deep")
        assert quick.ok is True and deep.ok is True
        assert len(quick.findings) < len(deep.findings)

    def test_unknown_depth_fmt_falls_back(self, worktree: str) -> None:
        r = research(worktree, "widget factory", depth="extreme", fmt="weird")
        assert r.ok is True
        assert r.depth == "standard"
        assert r.fmt == "summary"
        assert "fell back" in r.learnings


class TestResearchFormats:
    def test_fmt_summary_shorter_than_detailed(
        self, worktree_factory: Callable[[], str]
    ) -> None:
        summary_wt = worktree_factory()
        detailed_wt = worktree_factory()
        _seed(summary_wt, SEEDS)
        _seed(detailed_wt, SEEDS)
        summary = research(summary_wt, "widget factory", fmt="summary")
        detailed = research(detailed_wt, "widget factory", fmt="detailed")
        assert summary.ok is True and detailed.ok is True
        assert len(summary.learnings) < len(detailed.learnings)

    def test_raw_fmt_includes_citations(self, worktree: str) -> None:
        r = research(worktree, "widget factory", fmt="raw")
        assert r.ok is True
        assert "citations:" in r.learnings
        assert "[1]" in r.learnings

    def test_detailed_fmt_lists_findings(self, worktree: str) -> None:
        r = research(worktree, "widget factory", fmt="detailed")
        assert "findings:" in r.learnings
        assert "confidence=" in r.learnings


class TestResearchObserver:
    def test_research_records_observation(self, worktree: str) -> None:
        research(worktree, "test query")
        obs_file = Path(worktree) / ".school" / "agent" / "observations.jsonl"
        assert obs_file.exists()
        record = json.loads(obs_file.read_text(encoding="utf-8").splitlines()[-1])
        assert record["category"] == "research"
        assert "test query" in record["observation"]

    def test_research_findings_come_from_observations(self, worktree: str) -> None:
        _seed(worktree, SEEDS)
        r = research(worktree, "widget factory", depth="deep")
        claims = [f["claim"] for f in r.findings]
        assert any("production line" in claim for claim in claims)
