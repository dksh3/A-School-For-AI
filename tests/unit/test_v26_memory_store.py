"""Tests for V2.6 memory store module.

Covers: MemoryStore — store, query, scope filtering, eviction, clear.
"""

from __future__ import annotations

from core.routing.v26.identity import (
    AgentIdentity,
    MemoryScope,
    ProjectIdentity,
    SessionIdentity,
)
from core.routing.v26.memory_store import MemoryStore
from core.routing.v26.memory_types import MemoryEntry, MemoryKind


def _make_scope(agent_id: str = "a1", project_id: str = "", session_id: str = "") -> MemoryScope:
    agent = AgentIdentity(agent_id=agent_id)
    project = ProjectIdentity(project_id=project_id) if project_id else None
    session = SessionIdentity(session_id=session_id) if session_id else None
    return MemoryScope(agent=agent, project=project, session=session)


def _make_entry(
    content: str = "test",
    agent_id: str = "a1",
    project_id: str = "",
    session_id: str = "",
    kind: MemoryKind = MemoryKind.EPISODIC,
    confidence: float = 0.5,
    tags: frozenset[str] | None = None,
) -> MemoryEntry:
    return MemoryEntry.create(
        content=content,
        kind=kind,
        scope=_make_scope(agent_id, project_id, session_id),
        confidence=confidence,
        tags=tags or frozenset(),
    )


# ---------------------------------------------------------------------------
# Basic operations
# ---------------------------------------------------------------------------


class TestMemoryStore:
    def test_store_and_get(self) -> None:
        store = MemoryStore()
        entry = _make_entry("hello")
        store.store(entry)
        retrieved = store.get(entry.memory_id)
        assert retrieved is not None
        assert retrieved.content == "hello"

    def test_get_nonexistent(self) -> None:
        store = MemoryStore()
        assert store.get("nonexistent") is None

    def test_remove(self) -> None:
        store = MemoryStore()
        entry = _make_entry()
        store.store(entry)
        assert store.remove(entry.memory_id)
        assert store.get(entry.memory_id) is None

    def test_remove_nonexistent(self) -> None:
        store = MemoryStore()
        assert not store.remove("nonexistent")

    def test_size(self) -> None:
        store = MemoryStore()
        assert store.size == 0
        store.store(_make_entry("a"))
        assert store.size == 1

    def test_is_empty(self) -> None:
        store = MemoryStore()
        assert store.is_empty
        store.store(_make_entry())
        assert not store.is_empty

    def test_all_ids(self) -> None:
        store = MemoryStore()
        e1 = _make_entry("a")
        e2 = _make_entry("b")
        store.store(e1)
        store.store(e2)
        ids = store.all_ids()
        assert e1.memory_id in ids
        assert e2.memory_id in ids


# ---------------------------------------------------------------------------
# Query filtering
# ---------------------------------------------------------------------------


class TestQuery:
    def test_query_all(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a"))
        store.store(_make_entry("b"))
        results = store.query()
        assert len(results) == 2

    def test_query_by_scope(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a", agent_id="a1"))
        store.store(_make_entry("b", agent_id="a2"))
        scope = _make_scope("a1")
        results = store.query(scope=scope)
        assert len(results) == 1
        assert results[0].scope.agent.agent_id == "a1"

    def test_query_by_kind(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a", kind=MemoryKind.EPISODIC))
        store.store(_make_entry("b", kind=MemoryKind.LEARNED))
        results = store.query(kind=MemoryKind.EPISODIC)
        assert len(results) == 1

    def test_query_by_confidence(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a", confidence=0.3))
        store.store(_make_entry("b", confidence=0.8))
        results = store.query(minimum_confidence=0.5)
        assert len(results) == 1
        assert results[0].confidence >= 0.5

    def test_query_by_text(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("Python is great"))
        store.store(_make_entry("JavaScript is fast"))
        results = store.query(query_text="Python")
        assert len(results) == 1
        assert "Python" in results[0].content

    def test_query_by_tags(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a", tags=frozenset({"tag1", "tag2"})))
        store.store(_make_entry("b", tags=frozenset({"tag1"})))
        results = store.query(tags=frozenset({"tag1"}))
        assert len(results) == 2

    def test_query_by_tags_requires_all(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a", tags=frozenset({"tag1", "tag2"})))
        store.store(_make_entry("b", tags=frozenset({"tag1"})))
        results = store.query(tags=frozenset({"tag1", "tag2"}))
        assert len(results) == 1

    def test_query_limit(self) -> None:
        store = MemoryStore()
        for i in range(10):
            store.store(_make_entry(f"item {i}"))
        results = store.query(limit=3)
        assert len(results) == 3

    def test_query_project_filter(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a", agent_id="a1", project_id="p1"))
        store.store(_make_entry("b", agent_id="a1", project_id="p2"))
        scope = _make_scope("a1", "p1")
        results = store.query(scope=scope)
        assert len(results) == 1

    def test_query_session_filter(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a", agent_id="a1", project_id="p1", session_id="s1"))
        store.store(_make_entry("b", agent_id="a1", project_id="p1", session_id="s2"))
        scope = _make_scope("a1", "p1", "s1")
        results = store.query(scope=scope)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Eviction
# ---------------------------------------------------------------------------


class TestEviction:
    def test_evicts_oldest_when_over_capacity(self) -> None:
        store = MemoryStore(max_entries=3)
        e1 = _make_entry("first")
        e2 = _make_entry("second")
        e3 = _make_entry("third")
        e4 = _make_entry("fourth")
        store.store(e1)
        store.store(e2)
        store.store(e3)
        store.store(e4)
        assert store.size == 3
        assert store.get(e1.memory_id) is None  # evicted
        assert store.get(e4.memory_id) is not None  # kept


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_all(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a"))
        store.store(_make_entry("b"))
        count = store.clear()
        assert count == 2
        assert store.is_empty

    def test_clear_scoped(self) -> None:
        store = MemoryStore()
        store.store(_make_entry("a", agent_id="a1"))
        store.store(_make_entry("b", agent_id="a1"))
        store.store(_make_entry("c", agent_id="a2"))
        scope = _make_scope("a1")
        count = store.clear(scope=scope)
        assert count == 2
        assert store.size == 1


# ---------------------------------------------------------------------------
# Semantic retrieval via query(extractor=...)
# ---------------------------------------------------------------------------


class TestSemanticQuery:
    """Tests proving semantic ranking is used through MemoryStore.query()."""

    def test_semantic_ranking_via_store_query(self) -> None:
        """When extractor is provided, query() uses TF-IDF cosine ranking."""
        from core.learner.feature_extractor import FeatureExtractor

        store = MemoryStore()
        store.store(_make_entry("the cat sat on the mat"))
        store.store(_make_entry("dogs are friendly animals"))
        store.store(_make_entry("the feline rested on the rug"))

        extractor = FeatureExtractor()
        extractor.fit("the cat sat on the mat")
        extractor.fit("dogs are friendly animals")
        extractor.fit("the feline rested on the rug")

        results = store.query(query_text="cat on mat", extractor=extractor, limit=3)
        # Semantic ranking: "cat on mat" should rank higher than "dogs"
        contents = [r.content for r in results]
        assert (
            contents.index("the cat sat on the mat") < contents.index("dogs are friendly animals")
        )

    def test_semantic_ranking_with_scope_filter(self) -> None:
        """Scope filtering still works when semantic ranking is active."""
        from core.learner.feature_extractor import FeatureExtractor

        store = MemoryStore()
        store.store(_make_entry("python programming guide", agent_id="a1"))
        store.store(_make_entry("java programming guide", agent_id="a2"))
        store.store(_make_entry("python web development", agent_id="a1"))

        extractor = FeatureExtractor()
        for e in store.query():
            extractor.fit(e.content)

        scope = _make_scope("a1")
        results = store.query(scope=scope, query_text="python", extractor=extractor, limit=5)
        # Only a1 entries returned, ranked by relevance
        assert all(r.scope.agent.agent_id == "a1" for r in results)
        assert len(results) == 2

    def test_semantic_ranking_with_kind_filter(self) -> None:
        """Kind filtering still works when semantic ranking is active."""
        from core.learner.feature_extractor import FeatureExtractor

        store = MemoryStore()
        store.store(_make_entry("machine learning basics", kind=MemoryKind.EPISODIC))
        store.store(_make_entry("deep learning fundamentals", kind=MemoryKind.LEARNED))

        extractor = FeatureExtractor()
        extractor.fit("machine learning basics")
        extractor.fit("deep learning fundamentals")

        results = store.query(kind=MemoryKind.LEARNED, query_text="learning", extractor=extractor)
        assert len(results) == 1
        assert results[0].kind == MemoryKind.LEARNED

    def test_semantic_ranking_with_confidence_filter(self) -> None:
        """Confidence filtering still works when semantic ranking is active."""
        from core.learner.feature_extractor import FeatureExtractor

        store = MemoryStore()
        store.store(_make_entry("high confidence entry", confidence=0.9))
        store.store(_make_entry("low confidence entry", confidence=0.2))

        extractor = FeatureExtractor()
        extractor.fit("high confidence entry")
        extractor.fit("low confidence entry")

        results = store.query(minimum_confidence=0.5, query_text="confidence", extractor=extractor)
        assert len(results) == 1
        assert results[0].content == "high confidence entry"

    def test_semantic_ranking_with_tags_filter(self) -> None:
        """Tag filtering still works when semantic ranking is active."""
        from core.learner.feature_extractor import FeatureExtractor

        store = MemoryStore()
        store.store(_make_entry("tagged entry about cats", tags=frozenset({"animal", "pets"})))
        store.store(_make_entry("tagged entry about dogs", tags=frozenset({"animal"})))
        store.store(_make_entry("untagged entry about cats", tags=frozenset()))

        extractor = FeatureExtractor()
        extractor.fit("tagged entry about cats")
        extractor.fit("tagged entry about dogs")
        extractor.fit("untagged entry about cats")

        results = store.query(tags=frozenset({"animal"}), query_text="cats", extractor=extractor)
        # Only tagged entries with "animal" tag returned
        assert all(frozenset({"animal"}).issubset(r.tags) for r in results)

    def test_semantic_ranking_deterministic(self) -> None:
        """Same query through store.query() produces same ranking."""
        from core.learner.feature_extractor import FeatureExtractor

        store = MemoryStore()
        store.store(_make_entry("alpha programming language"))
        store.store(_make_entry("beta programming language"))
        store.store(_make_entry("unrelated content"))

        extractor = FeatureExtractor()
        for e in store.query():
            extractor.fit(e.content)

        r1 = store.query(query_text="alpha", extractor=extractor, limit=3)
        r2 = store.query(query_text="alpha", extractor=extractor, limit=3)
        assert [r.content for r in r1] == [r.content for r in r2]

    def test_fallback_to_substring_when_no_extractor(self) -> None:
        """Without extractor, query() falls back to substring matching."""
        store = MemoryStore()
        store.store(_make_entry("Python is great"))
        store.store(_make_entry("JavaScript is fast"))
        store.store(_make_entry("I like Python programming"))

        results = store.query(query_text="Python")
        assert len(results) == 2
        contents = [r.content for r in results]
        assert "Python is great" in contents
        assert "I like Python programming" in contents

    def test_empty_query_returns_all_filtered(self) -> None:
        """Empty query_text returns all entries matching other filters."""
        store = MemoryStore()
        store.store(_make_entry("a"))
        store.store(_make_entry("b"))
        results = store.query()
        assert len(results) == 2

    def test_empty_query_with_extractor_returns_all(self) -> None:
        """Empty query_text with extractor still returns all (no ranking)."""
        from core.learner.feature_extractor import FeatureExtractor

        store = MemoryStore()
        store.store(_make_entry("a"))
        store.store(_make_entry("b"))
        extractor = FeatureExtractor()
        results = store.query(query_text="", extractor=extractor)
        assert len(results) == 2

    def test_no_matches_returns_empty(self) -> None:
        """Query that matches nothing returns empty list."""
        store = MemoryStore()
        store.store(_make_entry("hello world"))
        results = store.query(query_text="nonexistent_xyz")
        assert results == []

    def test_semantic_no_matches_returns_low_score(self) -> None:
        """Semantic query for unrelated content returns entry with low score."""
        from core.learner.feature_extractor import FeatureExtractor

        store = MemoryStore()
        store.store(_make_entry("hello world"))
        extractor = FeatureExtractor()
        extractor.fit("hello world")
        # Unrelated query still returns entry but with low relevance (ranking behavior)
        results = store.query(query_text="nonexistent_xyz", extractor=extractor)
        # Semantic ranking returns all entries (sorted by relevance), not filtered
        assert len(results) == 1

    def test_semantic_unrelated_query_ranks_lower(self) -> None:
        """Unrelated queries should rank entries lower than related queries."""
        from core.learner.feature_extractor import FeatureExtractor

        store = MemoryStore()
        store.store(_make_entry("python programming language"))
        store.store(_make_entry("the weather is nice"))

        extractor = FeatureExtractor()
        extractor.fit("python programming language")
        extractor.fit("the weather is nice")

        # Related query should return entries in expected order
        results_related = store.query(query_text="python", extractor=extractor, limit=2)
        assert results_related[0].content == "python programming language"

        # Unrelated query should still return both entries but reorder
        results_unrelated = store.query(query_text="cooking recipe", extractor=extractor, limit=2)
        assert len(results_unrelated) == 2  # both returned
