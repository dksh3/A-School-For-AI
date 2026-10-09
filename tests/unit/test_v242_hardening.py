"""Comprehensive adversarial tests for V2.4.2 hardening features.

Tests:
- Token inverted index correctness
- Event-based maintenance triggers
- Semantic similarity integration
- Edge cases and failure modes
- Performance under adversarial conditions
"""

from __future__ import annotations

import random

import pytest

from core.learner.hybrid_memory import HybridExample, HybridMemory
from core.learner.knowledge_ops import (
    MergeCandidate,
    RedundancyResult,
    RedundancyType,
    TokenInvertedIndex,
    compute_semantic_similarity,
    find_merge_candidates,
)
from core.learner.lifecycle import (
    LifecycleConfig,
    MemoryState,
)
from core.learner.lifecycle_manager import (
    EventTriggerConfig,
    LifecycleManager,
    MaintenanceEvent,
    MaintenanceRecord,
    MemoryLifecycleState,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_memory(
    memory_id: int,
    input_text: str = "test input",
    output: str = "test output",
    success_count: int = 1,
    failure_count: int = 0,
    created_at: float = 0.0,
    use_count: int = 0,
    semantic_vector: list[float] | None = None,
) -> HybridExample:
    """Create a test memory."""
    return HybridExample(
        id=memory_id,
        input_text=input_text,
        output=output,
        lexical_vector=[],
        semantic_vector=semantic_vector,
        weight=1.0,
        success_count=success_count,
        failure_count=failure_count,
        use_count=use_count,
        created_at=created_at,
        last_used_at=created_at,
    )


# ---------------------------------------------------------------------------
# Token inverted index tests
# ---------------------------------------------------------------------------


class TestTokenInvertedIndex:
    """Test the token inverted index for merge candidate generation."""

    def test_basic_add_and_find(self) -> None:
        """Test basic add and find operations."""
        index = TokenInvertedIndex()
        index.add(0, "python test case")
        index.add(1, "javascript test case")
        index.add(2, "rust test case")

        candidates = index.find_candidates("python test case", min_overlap=2)
        assert len(candidates) >= 1
        assert candidates[0][0] == 0  # Should find exact match

    def test_no_false_positives(self) -> None:
        """Test that unrelated texts are not returned as candidates."""
        index = TokenInvertedIndex()
        index.add(0, "python test case")
        index.add(1, "java program example")
        index.add(2, "rust programming language")

        candidates = index.find_candidates("python test case", min_overlap=3)
        # Only exact match should have 3 overlapping tokens
        assert len(candidates) == 1
        assert candidates[0][0] == 0

    def test_remove(self) -> None:
        """Test removing a memory from the index."""
        index = TokenInvertedIndex()
        index.add(0, "python test case")
        index.add(1, "python example code")

        candidates = index.find_candidates("python", min_overlap=1)
        assert len(candidates) == 2

        index.remove(0, "python test case")
        candidates = index.find_candidates("python", min_overlap=1)
        assert len(candidates) == 1
        assert candidates[0][0] == 1

    def test_empty_query(self) -> None:
        """Test with empty query."""
        index = TokenInvertedIndex()
        index.add(0, "python test case")
        candidates = index.find_candidates("", min_overlap=1)
        assert len(candidates) == 0

    def test_exclude_ids(self) -> None:
        """Test excluding specific IDs from results."""
        index = TokenInvertedIndex()
        index.add(0, "python test case")
        index.add(1, "python example code")

        candidates = index.find_candidates(
            "python test case", min_overlap=2, exclude_ids={0}
        )
        # 0 excluded, 1 has 1 overlapping token (python) but needs 2
        assert not any(c[0] == 0 for c in candidates)

    def test_clear(self) -> None:
        """Test clearing the index."""
        index = TokenInvertedIndex()
        index.add(0, "python test case")
        index.add(1, "javascript test case")
        index.clear()

        candidates = index.find_candidates("python test case", min_overlap=2)
        assert len(candidates) == 0

    def test_duplicate_tokens(self) -> None:
        """Test with duplicate tokens in text."""
        index = TokenInvertedIndex()
        index.add(0, "test test test python")
        index.add(1, "test python code")

        candidates = index.find_candidates("test python", min_overlap=2)
        # Both should be found
        assert len(candidates) >= 2

    def test_large_vocabulary(self) -> None:
        """Test with a large vocabulary."""
        index = TokenInvertedIndex()
        words = [f"word{i}" for i in range(1000)]

        # Create memories with specific word patterns
        for i in range(100):
            # Memory 0 has words 0-9
            if i == 0:
                index.add(i, " ".join(words[:10]))
            else:
                # Other memories have different word sets
                rng = random.Random(i)
                mem_words = rng.sample(words[10:], 10)
                index.add(i, " ".join(mem_words))

        # Query with words that appear in memory 0
        candidates = index.find_candidates(" ".join(words[:3]), min_overlap=2)
        # Memory 0 should be found (has words 0, 1, 2)
        assert any(c[0] == 0 for c in candidates)


# ---------------------------------------------------------------------------
# Event-based maintenance trigger tests
# ---------------------------------------------------------------------------


class TestEventBasedMaintenance:
    """Test event-based maintenance triggers."""

    def test_record_event_triggers_after_threshold(self) -> None:
        """Test that events trigger maintenance after threshold."""
        manager = LifecycleManager(
            event_config=EventTriggerConfig(
                min_events_before_trigger=3,
                cooldown_seconds=0.0,
            ),
        )

        # Record events below threshold
        assert not manager.record_event(MaintenanceEvent.NEW_EVIDENCE, 0)
        assert not manager.record_event(MaintenanceEvent.REPEATED_SUCCESS, 1)

        # Record event at threshold
        assert manager.record_event(MaintenanceEvent.REPEATED_FAILURE, 2)

    def test_cooldown_prevents_rapid_triggers(self) -> None:
        """Test that cooldown prevents rapid repeated triggers."""
        manager = LifecycleManager(
            event_config=EventTriggerConfig(
                min_events_before_trigger=1,
                cooldown_seconds=100.0,
            ),
        )

        # First trigger
        assert manager.record_event(MaintenanceEvent.NEW_EVIDENCE, 0)

        # Second trigger blocked by cooldown
        assert not manager.record_event(MaintenanceEvent.REPEATED_SUCCESS, 1)

    def test_disabled_events_ignored(self) -> None:
        """Test that disabled events are ignored."""
        manager = LifecycleManager(
            event_config=EventTriggerConfig(
                enabled_events=set(),  # No events enabled
                min_events_before_trigger=1,
            ),
        )

        assert not manager.record_event(MaintenanceEvent.NEW_EVIDENCE, 0)
        assert not manager.record_event(MaintenanceEvent.REPEATED_SUCCESS, 1)

    def test_pending_event_ids_tracked(self) -> None:
        """Test that pending event IDs are tracked."""
        manager = LifecycleManager(
            event_config=EventTriggerConfig(
                min_events_before_trigger=100,  # High threshold
            ),
        )

        manager.record_event(MaintenanceEvent.NEW_EVIDENCE, 0)
        manager.record_event(MaintenanceEvent.REPEATED_SUCCESS, 1)

        pending = manager.get_pending_event_ids()
        assert 0 in pending
        assert 1 in pending

    def test_clear_pending_events(self) -> None:
        """Test clearing pending events."""
        manager = LifecycleManager()

        manager.record_event(MaintenanceEvent.NEW_EVIDENCE, 0)
        manager.clear_pending_events()

        assert len(manager.get_pending_event_ids()) == 0

    def test_event_counts_reset_after_trigger(self) -> None:
        """Test that event counts reset after triggering maintenance."""
        manager = LifecycleManager(
            event_config=EventTriggerConfig(
                min_events_before_trigger=2,
                cooldown_seconds=0.0,
            ),
        )

        # Trigger maintenance
        manager.record_event(MaintenanceEvent.NEW_EVIDENCE, 0)
        manager.record_event(MaintenanceEvent.REPEATED_SUCCESS, 1)

        # After trigger, counts should reset
        # Need 2 more events to trigger again
        assert not manager.record_event(MaintenanceEvent.REPEATED_FAILURE, 2)
        assert manager.record_event(MaintenanceEvent.SESSION_COMPLETE, 3)


# ---------------------------------------------------------------------------
# Semantic similarity tests
# ---------------------------------------------------------------------------


class TestSemanticSimilarity:
    """Test semantic similarity computation."""

    def test_identical_vectors(self) -> None:
        """Test identical vectors have similarity 1.0."""
        vec = [1.0, 0.0, 0.0]
        sim = compute_semantic_similarity(
            _make_memory(0, semantic_vector=vec),
            _make_memory(1, semantic_vector=vec),
        )
        assert sim is not None
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        """Test orthogonal vectors have similarity ~0."""
        sim = compute_semantic_similarity(
            _make_memory(0, semantic_vector=[1.0, 0.0]),
            _make_memory(1, semantic_vector=[0.0, 1.0]),
        )
        assert sim is not None
        assert abs(sim) < 1e-6

    def test_none_when_no_vectors(self) -> None:
        """Test None returned when vectors are missing."""
        sim = compute_semantic_similarity(
            _make_memory(0),
            _make_memory(1),
        )
        assert sim is None

    def test_none_when_mismatched_dimensions(self) -> None:
        """Test None returned for mismatched dimensions."""
        sim = compute_semantic_similarity(
            _make_memory(0, semantic_vector=[1.0, 0.0]),
            _make_memory(1, semantic_vector=[1.0, 0.0, 0.0]),
        )
        assert sim is None

    def test_negative_similarity_clamped(self) -> None:
        """Test that negative similarities are clamped to 0."""
        sim = compute_semantic_similarity(
            _make_memory(0, semantic_vector=[1.0, 0.0]),
            _make_memory(1, semantic_vector=[-1.0, 0.0]),
        )
        assert sim is not None
        assert sim >= 0.0

    def test_zero_vector_returns_zero(self) -> None:
        """Test that zero vectors return 0 similarity."""
        sim = compute_semantic_similarity(
            _make_memory(0, semantic_vector=[0.0, 0.0]),
            _make_memory(1, semantic_vector=[1.0, 0.0]),
        )
        assert sim is not None
        assert sim == 0.0


# ---------------------------------------------------------------------------
# Merge candidate indexing tests
# ---------------------------------------------------------------------------


class TestMergeCandidateIndexing:
    """Test indexed vs brute-force merge candidate generation."""

    def test_indexed_and_bruteforce_agree(self) -> None:
        """Test that indexed and brute-force find same candidates."""
        memories = [
            _make_memory(0, "python test case", "solution a", success_count=5),
            _make_memory(1, "python test example", "solution a", success_count=3),
            _make_memory(2, "java program", "solution b", success_count=4),
        ]
        config = LifecycleConfig(
            merge_similarity=0.3,
            merge_input_similarity=0.2,
            merge_min_evidence=1,
        )

        candidates_brute = find_merge_candidates(memories, config, use_index=False)
        candidates_index = find_merge_candidates(memories, config, use_index=True)

        # Both should find (0, 1) as a candidate
        ids_brute = {(c.id_a, c.id_b) for c in candidates_brute}
        ids_index = {(c.id_a, c.id_b) for c in candidates_index}
        assert ids_brute == ids_index

    def test_indexed_fallback_for_small_datasets(self) -> None:
        """Test that small datasets use brute-force even with use_index=True."""
        memories = [
            _make_memory(0, "python test case", "solution a"),
            _make_memory(1, "python test example", "solution a"),
        ]
        config = LifecycleConfig(merge_similarity=0.5, merge_min_evidence=1)

        # Should use brute-force for < 50 memories
        candidates = find_merge_candidates(memories, config, use_index=True)
        assert isinstance(candidates, list)


# ---------------------------------------------------------------------------
# Adversarial edge case tests
# ---------------------------------------------------------------------------


class TestAdversarialEdgeCases:
    """Test adversarial edge cases for the hardening features."""

    def test_duplicate_flood_with_index(self) -> None:
        """Test duplicate flood doesn't crash the index."""
        memories = [
            _make_memory(i, "same input", "same output", success_count=10)
            for i in range(100)
        ]
        config = LifecycleConfig(
            merge_similarity=0.9,
            merge_input_similarity=0.9,
            merge_min_evidence=1,
        )
        candidates = find_merge_candidates(memories, config, use_index=True)
        # Should find many candidates but not crash
        assert len(candidates) > 0

    def test_empty_text_memories(self) -> None:
        """Test with memories that have empty text."""
        memories = [
            _make_memory(0, "", "output"),
            _make_memory(1, "input", ""),
            _make_memory(2, "", ""),
        ]
        index = TokenInvertedIndex()
        for mem in memories:
            index.add(mem.id, mem.input_text)

        # Should not crash
        candidates = index.find_candidates("", min_overlap=0)
        assert isinstance(candidates, list)

    def test_unicode_text_indexing(self) -> None:
        """Test indexing with unicode text."""
        index = TokenInvertedIndex()
        index.add(0, "python programming 你好")
        index.add(1, "javascript coding 世界")

        candidates = index.find_candidates("python 你好", min_overlap=2)
        assert len(candidates) >= 1
        assert candidates[0][0] == 0

    def test_extreme_similarity_thresholds(self) -> None:
        """Test with extreme similarity thresholds."""
        memories = [
            _make_memory(0, "a b c", "x y z"),
            _make_memory(1, "a b c", "x y z"),
        ]

        # Very high threshold - should find only exact matches
        config_high = LifecycleConfig(
            merge_similarity=0.99,
            merge_input_similarity=0.99,
            merge_min_evidence=1,
        )
        candidates_high = find_merge_candidates(memories, config_high, use_index=False)
        assert len(candidates_high) >= 1

        # Very low threshold - should find everything
        config_low = LifecycleConfig(
            merge_similarity=0.0,
            merge_input_similarity=0.0,
            merge_min_evidence=0,
        )
        candidates_low = find_merge_candidates(memories, config_low, use_index=False)
        assert len(candidates_low) >= 1

    def test_health_precomputation_correctness(self) -> None:
        """Test that precomputed health data gives same results as non-precomputed."""
        memory = HybridMemory()
        examples = [
            _make_memory(0, "python test", "solution a", success_count=5),
            _make_memory(1, "python test", "solution a", success_count=3),
            _make_memory(2, "java test", "solution b", success_count=4),
        ]
        for ex in examples:
            memory.add(
                input_text=ex.input_text,
                output=ex.output,
                vector=ex.lexical_vector,
            )

        manager = LifecycleManager()

        # Without precomputation
        health_no_pre = manager.evaluate_health(examples[0], memory)

        # With precomputation
        precomputed = manager._precompute_health_data(memory)
        health_pre = manager.evaluate_health(examples[0], memory, _precomputed=precomputed)

        assert abs(health_no_pre - health_pre) < 1e-6

    def test_event_config_defaults(self) -> None:
        """Test that default event config has sensible defaults."""
        config = EventTriggerConfig()
        assert MaintenanceEvent.NEW_EVIDENCE in config.enabled_events
        assert MaintenanceEvent.REPEATED_SUCCESS in config.enabled_events
        assert config.min_events_before_trigger == 3
        assert config.cooldown_seconds == 60.0
        assert config.targeted_maintenance is True

    def test_maintenance_record_fields(self) -> None:
        """Test that MaintenanceRecord has all required fields."""
        record = MaintenanceRecord(
            timestamp=1000.0,
            memories_processed=10,
            transitions=2,
            duration_seconds=0.5,
            details={"test": True},
        )
        assert record.timestamp == 1000.0
        assert record.memories_processed == 10
        assert record.transitions == 2
        assert record.duration_seconds == 0.5
        assert record.details["test"] is True

    def test_memory_lifecycle_state_new_fields(self) -> None:
        """Test that MemoryLifecycleState has last_reinforced/last_decayed."""
        state = MemoryLifecycleState(
            memory_id=1,
            state=MemoryState.ACTIVE,
            health_score=0.8,
            last_health_check=1000.0,
            last_reinforced=900.0,
            last_decayed=800.0,
        )
        assert state.last_reinforced == 900.0
        assert state.last_decayed == 800.0

    def test_redundancy_result_semantic_similarity(self) -> None:
        """Test that RedundancyResult includes semantic similarity."""
        result = RedundancyResult(
            type=RedundancyType.EXACT_DUPLICATE,
            should_consolidate=True,
            reason="test",
            combined_evidence=10,
            semantic_similarity=0.95,
        )
        assert result.semantic_similarity == 0.95

    def test_merge_candidate_semantic_similarity(self) -> None:
        """Test that MergeCandidate includes semantic similarity."""
        candidate = MergeCandidate(
            id_a=0,
            id_b=1,
            output_similarity=0.9,
            input_similarity=0.8,
            combined_evidence=10,
            semantic_similarity=0.85,
        )
        assert candidate.semantic_similarity == 0.85

    def test_merge_candidate_none_semantic(self) -> None:
        """Test MergeCandidate with None semantic similarity."""
        candidate = MergeCandidate(
            id_a=0,
            id_b=1,
            output_similarity=0.9,
            input_similarity=0.8,
            combined_evidence=10,
        )
        assert candidate.semantic_similarity is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
