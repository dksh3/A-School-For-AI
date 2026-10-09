"""Tests for V2.6 semantic retrieval scoring.

Tests blended TF-IDF similarity ranking for MemoryEntry retrieval.
"""

from __future__ import annotations

from core.routing.v26.identity import AgentIdentity, MemoryScope
from core.routing.v26.memory_types import MemoryEntry, MemoryKind


def _make_entry(content: str, agent_id: str = "test") -> MemoryEntry:
    agent = AgentIdentity.create(agent_id=agent_id)
    scope = MemoryScope(agent=agent)
    return MemoryEntry.create(content=content, kind=MemoryKind.EPISODIC, scope=scope)


def test_exact_query_returns_high_score():
    """An entry matching the query exactly should score highest."""
    from core.learner.feature_extractor import FeatureExtractor
    from core.routing.v26.semantic_retrieval import scored_query

    entries = [
        _make_entry("python is a programming language"),
        _make_entry("java is a programming language"),
        _make_entry("the weather is nice today"),
    ]
    extractor = FeatureExtractor()
    for e in entries:
        extractor.fit(e.content)

    results = scored_query(entries, "python programming", extractor, limit=3)
    assert len(results) > 0
    assert results[0].content == "python is a programming language"


def test_paraphrased_query_ranks_related_entry_higher():
    """A paraphrased query should rank semantically similar entries higher."""
    from core.learner.feature_extractor import FeatureExtractor
    from core.routing.v26.semantic_retrieval import scored_query

    entries = [
        _make_entry("the cat sat on the mat"),
        _make_entry("dogs are friendly animals"),
        _make_entry("the feline rested on the rug"),
    ]
    extractor = FeatureExtractor()
    for e in entries:
        extractor.fit(e.content)

    results = scored_query(entries, "cat on mat", extractor, limit=3)
    assert len(results) > 0
    # "cat sat on the mat" should rank higher than "dogs are friendly"
    contents = [r.content for r in results]
    assert contents.index("the cat sat on the mat") < contents.index("dogs are friendly animals")


def test_empty_query_returns_empty():
    """Empty query should return empty results."""
    from core.learner.feature_extractor import FeatureExtractor
    from core.routing.v26.semantic_retrieval import scored_query

    entries = [_make_entry("some content")]
    extractor = FeatureExtractor()
    results = scored_query(entries, "", extractor, limit=10)
    assert results == []


def test_limit_respects_bound():
    """Results should not exceed the limit."""
    from core.learner.feature_extractor import FeatureExtractor
    from core.routing.v26.semantic_retrieval import scored_query

    entries = [_make_entry(f"content number {i}") for i in range(20)]
    extractor = FeatureExtractor()
    for e in entries:
        extractor.fit(e.content)

    results = scored_query(entries, "content", extractor, limit=5)
    assert len(results) <= 5


def test_no_entries_returns_empty():
    """Empty entry list should return empty results."""
    from core.learner.feature_extractor import FeatureExtractor
    from core.routing.v26.semantic_retrieval import scored_query

    extractor = FeatureExtractor()
    results = scored_query([], "query", extractor, limit=5)
    assert results == []


def test_scoring_is_deterministic():
    """Same inputs should always produce same ranking."""
    from core.learner.feature_extractor import FeatureExtractor
    from core.routing.v26.semantic_retrieval import scored_query

    entries = [
        _make_entry("alpha programming language"),
        _make_entry("beta programming language"),
        _make_entry("unrelated content"),
    ]
    extractor = FeatureExtractor()
    for e in entries:
        extractor.fit(e.content)

    results1 = scored_query(entries, "alpha", extractor, limit=3)
    results2 = scored_query(entries, "alpha", extractor, limit=3)
    assert [r.content for r in results1] == [r.content for r in results2]
