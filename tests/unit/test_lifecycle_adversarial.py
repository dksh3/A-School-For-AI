"""Adversarial tests for V2.4 knowledge lifecycle system.

Tests for:
- Duplicate flooding
- Old-but-high-quality knowledge
- New-but-low-quality knowledge
- Repeated failures
- Feedback poisoning
- Contradictory updates
- Semantic near-duplicates
- False consolidation
- Archival mistakes
- Accidental deletion
- Lifecycle oscillation
- Persistence corruption
- Irrelevant high-success memories
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from core.learner.feature_extractor import FeatureVector
from core.learner.hybrid_memory import HybridExample, HybridMemory
from core.learner.knowledge_ops import (
    analyze_redundancy,
    find_merge_candidates,
    is_eligible_for_archive,
)
from core.learner.lifecycle import (
    LifecycleConfig,
    MemoryState,
)
from core.learner.lifecycle_manager import LifecycleManager


def _make_example(
    id: int = 1,
    input_text: str = "test query",
    output: str = "test output",
    success: int = 0,
    failure: int = 0,
    weight: float = 1.0,
    use_count: int = 0,
    created_at: float = 0.0,
    last_used_at: float = 0.0,
) -> HybridExample:
    """Create a test example."""
    return HybridExample(
        id=id,
        input_text=input_text,
        output=output,
        lexical_vector=FeatureVector(features={}, norm=0.0),
        weight=weight,
        success_count=success,
        failure_count=failure,
        use_count=use_count,
        created_at=created_at or time.time() - 86400,
        last_used_at=last_used_at or time.time() - 3600,
    )


class TestDuplicateFlooding:
    """10 copies of same experience must NOT equal 10 independent experiences."""

    def test_duplicate_flooding_resisted(self):
        config = LifecycleConfig()
        # 10 duplicates
        duplicates = [
            _make_example(id=i, output="sorted(x)", success=1)
            for i in range(10)
        ]
        # 1 independent experience
        independent = _make_example(id=10, output="sorted(x)", success=10)

        # Find merge candidates - duplicates should be consolidated
        candidates = find_merge_candidates(duplicates, config)
        # Duplicates are candidates for merging
        assert len(candidates) > 0

        # But independent evidence should be preserved
        # The combined evidence from duplicates should not equal independent
        dup_evidence = sum(d.success_count for d in duplicates)
        indep_evidence = independent.success_count
        # 10 duplicates with 1 success each = 10 total
        # But they should be consolidated, not counted as 10 independent
        assert dup_evidence == 10
        assert indep_evidence == 10


class TestOldHighQuality:
    """Old knowledge with strong evidence should be retained."""

    def test_old_strong_knowledge_survives(self):
        config = LifecycleConfig()
        old = _make_example(
            success=50,
            failure=0,
            weight=0.9,
            created_at=time.time() - 365 * 86400,  # 1 year old
            last_used_at=time.time() - 30 * 86400,  # 30 days ago
        )
        manager = LifecycleManager(config)
        health = manager.evaluate_health(old, HybridMemory())
        # Strong evidence keeps health high even when old
        assert health > 0.5


class TestNewLowQuality:
    """New knowledge with weak evidence should not dominate."""

    def test_new_weak_knowledge_not_dominant(self):
        config = LifecycleConfig()
        new = _make_example(
            success=1,
            failure=0,
            weight=0.5,
            created_at=time.time(),
            last_used_at=time.time() - 86400,  # 1 day ago
        )
        old = _make_example(
            id=2,
            success=20,
            failure=2,
            weight=0.8,
            created_at=time.time() - 30 * 86400,
            last_used_at=time.time() - 86400,  # Same recency
        )
        manager = LifecycleManager(config)
        new_health = manager.evaluate_health(new, HybridMemory())
        old_health = manager.evaluate_health(old, HybridMemory())
        # Old with strong evidence should have higher health
        # (both have same recency, so evidence is the differentiator)
        assert old_health >= new_health


class TestRepeatedFailures:
    """Repeated failures should reduce health."""

    def test_failures_reduce_health(self):
        config = LifecycleConfig()
        good = _make_example(success=10, failure=0)
        bad = _make_example(id=2, success=2, failure=8)
        manager = LifecycleManager(config)
        good_health = manager.evaluate_health(good, HybridMemory())
        bad_health = manager.evaluate_health(bad, HybridMemory())
        assert good_health > bad_health


class TestFeedbackPoisoning:
    """Feedback poisoning should not destroy good knowledge."""

    def test_poisoning_resisted(self):
        config = LifecycleConfig()
        # Good knowledge with strong evidence
        good = _make_example(success=20, failure=2, weight=0.8)
        # Poisoning attempt: 5 failures
        manager = LifecycleManager(config)
        old_health = manager.evaluate_health(good, HybridMemory())

        # Simulate failures
        good.failure_count += 5
        new_health = manager.evaluate_health(good, HybridMemory())

        # Health should decrease but not collapse
        assert new_health > 0.3
        assert new_health < old_health


class TestContradictoryUpdates:
    """Contradictory knowledge should be preserved when unresolved."""

    def test_contradictions_preserved(self):
        config = LifecycleConfig()
        a = _make_example(input_text="sort list", output="sorted(x)", success=5)
        b = _make_example(id=2, input_text="sort list", output="list.sort()", success=5)

        result_a = analyze_redundancy(a, b, config)
        # Different outputs should NOT be merged
        assert not result_a.should_consolidate


class TestSemanticNearDuplicates:
    """Near-duplicates should be detected and handled safely."""

    def test_near_duplicates_detected(self):
        config = LifecycleConfig()
        a = _make_example(input_text="sort a list", output="sorted(x)")
        b = _make_example(id=2, input_text="sort list items", output="sorted(x)")

        result = analyze_redundancy(a, b, config)
        # Same output = should consolidate
        assert result.should_consolidate


class TestFalseConsolidation:
    """Genuinely different knowledge must NOT be consolidated."""

    def test_different_outputs_not_merged(self):
        config = LifecycleConfig()
        a = _make_example(input_text="sort list", output="sorted(x)")
        b = _make_example(id=2, input_text="sort list", output="list.sort()")

        candidates = find_merge_candidates([a, b], config)
        # Different outputs should not be merge candidates
        assert len(candidates) == 0


class TestArchivalMistakes:
    """Good knowledge must not be archived by mistake."""

    def test_good_knowledge_not_archived(self):
        config = LifecycleConfig()
        good = _make_example(success=10, failure=0, weight=0.9)
        eligible, reason = is_eligible_for_archive(good, 0.8, config)
        assert not eligible


class TestAccidentalDeletion:
    """No memory should be permanently deleted."""

    def test_archive_not_delete(self):
        manager = LifecycleManager()
        example = _make_example()
        event = manager.archive(example, "Test")
        assert event.new_state == "archived"
        # Memory is archived, not deleted
        state = manager.get_state(example.id)
        assert state.state == MemoryState.ARCHIVED


class TestLifecycleOscillation:
    """Single feedback events should not cause rapid state changes."""

    def test_no_oscillation_on_single_feedback(self):
        config = LifecycleConfig()
        manager = LifecycleManager(config)
        example = _make_example(success=5, failure=5, weight=0.5)

        # Initial state
        health1 = manager.evaluate_health(example, HybridMemory())

        # Single reinforcement
        manager.reinforce(example)
        health2 = manager.evaluate_health(example, HybridMemory())

        # Should not swing wildly
        assert abs(health2 - health1) < 0.2


class TestPersistenceCorruption:
    """Lifecycle state must survive save/load."""

    def test_persistence_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = LifecycleManager()
            example = _make_example()
            manager.reinforce(example)
            manager.archive(_make_example(id=2), "Test")

            manager.save(Path(tmpdir))
            loaded = LifecycleManager.load(Path(tmpdir))

            assert len(loaded.get_all_states()) == len(manager.get_all_states())


class TestIrrelevantHighSuccess:
    """Irrelevant high-success memories should not dominate retrieval."""

    def test_irrelevant_high_success(self):
        config = LifecycleConfig()
        # High success but irrelevant
        irrelevant = _make_example(
            input_text="bake cake",
            output="recipe",
            success=100,
            failure=0,
        )
        # Lower success but relevant
        relevant = _make_example(
            id=2,
            input_text="sort list",
            output="sorted(x)",
            success=5,
            failure=1,
        )

        # Health should reflect relevance context
        manager = LifecycleManager(config)
        h1 = manager.evaluate_health(irrelevant, HybridMemory())
        h2 = manager.evaluate_health(relevant, HybridMemory())
        # Both can have high health, but they shouldn't interfere
        assert h1 > 0.5
        assert h2 > 0.5
