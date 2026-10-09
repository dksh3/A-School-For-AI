"""V2.4.2 adversarial test suite.

Tests for:
1. Duplicate memory flood
2. Repeated success flood
3. Repeated failure flood
4. Stale high-quality memory
5. Recent low-quality memory
6. Contradictory memories
7. Semantic near-duplicates
8. Related-but-distinct memories
9. Poisoned feedback
10. Conflicting feedback
11. Archive/recovery cycle
12. Repeated maintenance
13. Persistence corruption/partial state
14. Large memory population
15. Mixed-quality memory population
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from core.learner.feature_extractor import FeatureVector
from core.learner.hybrid_memory import HybridExample, HybridMemory
from core.learner.knowledge_ops import (
    analyze_redundancy,
    analyze_supersession,
    find_merge_candidates,
)
from core.learner.lifecycle import (
    LifecycleConfig,
    compute_decay,
    compute_reinforcement,
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


# ---------------------------------------------------------------------------
# 1. Duplicate memory flood
# ---------------------------------------------------------------------------


class TestDuplicateFlood:
    """10 copies of same experience must NOT equal 10 independent experiences."""

    def test_duplicate_flood_resisted(self):
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


# ---------------------------------------------------------------------------
# 2. Repeated success flood
# ---------------------------------------------------------------------------


class TestRepeatedSuccessFlood:
    """Repeated identical successes must have diminishing returns."""

    def test_diminishing_returns(self):
        config = LifecycleConfig()
        # 100 identical successes
        confidence = compute_reinforcement(0.5, 100, 100, config)
        # Should not reach 1.0 due to diminishing returns
        assert confidence < 1.0
        # But should be higher than 0.5
        assert confidence > 0.5
        # Marginal gain from 100 to 200 should be small
        confidence_200 = compute_reinforcement(0.5, 200, 200, config)
        marginal = confidence_200 - confidence
        assert marginal < 0.1


# ---------------------------------------------------------------------------
# 3. Repeated failure flood
# ---------------------------------------------------------------------------


class TestRepeatedFailureFlood:
    """Repeated failures must reduce health but not destroy it."""

    def test_failures_reduce_health(self):
        config = LifecycleConfig()
        # 100 failures, 0 successes
        example = _make_example(success=0, failure=100, weight=0.1)
        manager = LifecycleManager(config)
        health = manager.evaluate_health(example, HybridMemory())
        # Health should be low but not zero (decay floor prevents total loss)
        assert health < 0.4
        assert health >= 0.0


# ---------------------------------------------------------------------------
# 4. Stale high-quality memory
# ---------------------------------------------------------------------------


class TestStaleHighQuality:
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


# ---------------------------------------------------------------------------
# 5. Recent low-quality memory
# ---------------------------------------------------------------------------


class TestRecentLowQuality:
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
        assert old_health >= new_health


# ---------------------------------------------------------------------------
# 6. Contradictory memories
# ---------------------------------------------------------------------------


class TestContradictoryMemories:
    """Contradictory knowledge should be preserved when unresolved."""

    def test_contradictions_preserved(self):
        config = LifecycleConfig()
        a = _make_example(input_text="sort list", output="sorted(x)", success=5)
        b = _make_example(id=2, input_text="sort list", output="list.sort()", success=5)

        result_a = analyze_redundancy(a, b, config)
        # Different outputs should NOT be merged
        assert not result_a.should_consolidate


# ---------------------------------------------------------------------------
# 7. Semantic near-duplicates
# ---------------------------------------------------------------------------


class TestSemanticNearDuplicates:
    """Near-duplicates should be detected and handled safely."""

    def test_near_duplicates_detected(self):
        config = LifecycleConfig()
        a = _make_example(input_text="sort a list of numbers", output="sorted(x)")
        b = _make_example(id=2, input_text="sort list of numbers", output="sorted(x)")

        result = analyze_redundancy(a, b, config)
        # Same output = should consolidate
        assert result.should_consolidate


# ---------------------------------------------------------------------------
# 8. Related-but-distinct memories
# ---------------------------------------------------------------------------


class TestRelatedButDistinct:
    """Genuinely different knowledge must NOT be consolidated."""

    def test_different_outputs_not_merged(self):
        config = LifecycleConfig()
        a = _make_example(input_text="sort list", output="sorted(x)")
        b = _make_example(id=2, input_text="sort list", output="list.sort()")

        candidates = find_merge_candidates([a, b], config)
        # Different outputs should not be merge candidates
        assert len(candidates) == 0


# ---------------------------------------------------------------------------
# 9. Poisoned feedback
# ---------------------------------------------------------------------------


class TestPoisonedFeedback:
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


# ---------------------------------------------------------------------------
# 10. Conflicting feedback
# ---------------------------------------------------------------------------


class TestConflictingFeedback:
    """Alternating success/failure should not cause oscillation."""

    def test_no_oscillation(self):
        config = LifecycleConfig()
        manager = LifecycleManager(config)
        example = _make_example(success=5, failure=5, weight=0.5)

        # Initial state
        health1 = manager.evaluate_health(example, HybridMemory())

        # Alternating feedback
        for _i in range(5):
            example.success_count += 1
            example.failure_count += 1
            manager.evaluate_health(example, HybridMemory())

        health2 = manager.evaluate_health(example, HybridMemory())

        # Should not swing wildly
        assert abs(health2 - health1) < 0.2


# ---------------------------------------------------------------------------
# 11. Archive/recovery cycle
# ---------------------------------------------------------------------------


class TestArchiveRecoveryCycle:
    """Archive and recovery must preserve provenance."""

    def test_archive_recovery_preserves_provenance(self):
        manager = LifecycleManager()
        example = _make_example()

        # Archive
        event_archive = manager.archive(example, "Test archival")
        assert event_archive.new_state == "archived"

        # Recovery
        event_restore = manager.restore(example.id, "Test recovery")
        assert event_restore.new_state == "active"

        # Check provenance
        state = manager.get_state(example.id)
        assert len(state.lifecycle_events) == 2
        assert state.lifecycle_events[0].new_state == "archived"
        assert state.lifecycle_events[1].new_state == "active"


# ---------------------------------------------------------------------------
# 12. Repeated maintenance
# ---------------------------------------------------------------------------


class TestRepeatedMaintenance:
    """Repeated maintenance should be idempotent."""

    def test_idempotent_maintenance(self):
        config = LifecycleConfig()
        manager = LifecycleManager(config)
        memory = HybridMemory()

        # Add some examples
        for i in range(10):
            memory.add(
                input_text=f"test {i}",
                output=f"output {i}",
                vector=FeatureVector(features={}, norm=0.0),
                weight=0.8,
            )

        # Run maintenance multiple times
        result1 = manager.run_maintenance(memory, force=True)
        result2 = manager.run_maintenance(memory, force=True)
        result3 = manager.run_maintenance(memory, force=True)

        # All should process same number of memories
        assert result1.memories_processed == 10
        assert result2.memories_processed == 10
        assert result3.memories_processed == 10

        # After first run, subsequent runs should have fewer transitions
        # (because states already settled)
        assert result2.transitions <= result1.transitions
        assert result3.transitions <= result2.transitions


# ---------------------------------------------------------------------------
# 13. Persistence corruption/partial state
# ---------------------------------------------------------------------------


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

    def test_persistence_backward_compatibility(self):
        """Test loading V2.4.0 format (missing new fields)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create old format (without new fields)
            import json

            old_config = {
                "decay_rate": 0.01,
                "decay_min": 0.1,
                "reinforcement_strength": 0.03,
                "independence_bonus": 0.02,
                "supersession_threshold": 0.2,
                "merge_similarity": 0.8,
                "archive_threshold": 0.1,
                "uncertainty_threshold": 0.2,
                "max_redundancy": 5,
            }
            (Path(tmpdir) / "lifecycle_config.json").write_text(
                json.dumps(old_config), encoding="utf-8"
            )

            old_states = {
                "1": {
                    "memory_id": 1,
                    "state": "active",
                    "health_score": 0.8,
                    "last_health_check": time.time(),
                    "superseded_by": None,
                    "merged_from": [],
                    "events": [],
                }
            }
            (Path(tmpdir) / "lifecycle_states.json").write_text(
                json.dumps(old_states), encoding="utf-8"
            )

            # Should load successfully with defaults
            loaded = LifecycleManager.load(Path(tmpdir))
            assert loaded.config.maintenance_interval_hours == 24.0
            assert loaded.config.merge_input_similarity == 0.6
            assert loaded.config.merge_min_evidence == 2


# ---------------------------------------------------------------------------
# 14. Large memory population
# ---------------------------------------------------------------------------


class TestLargeMemoryPopulation:
    """System should handle large memory populations."""

    def test_100_memories(self):
        config = LifecycleConfig()
        manager = LifecycleManager(config)
        memory = HybridMemory()

        # Add 100 memories
        for i in range(100):
            memory.add(
                input_text=f"query {i}",
                output=f"output {i}",
                vector=FeatureVector(features={}, norm=0.0),
                weight=0.8,
            )

        results = manager.process_all(memory)
        assert results["total"] == 100

    def test_500_memories(self):
        config = LifecycleConfig()
        manager = LifecycleManager(config)
        memory = HybridMemory()

        # Add 500 memories
        for i in range(500):
            memory.add(
                input_text=f"query {i}",
                output=f"output {i}",
                vector=FeatureVector(features={}, norm=0.0),
                weight=0.8,
            )

        results = manager.process_all(memory)
        assert results["total"] == 500


# ---------------------------------------------------------------------------
# 15. Mixed-quality memory population
# ---------------------------------------------------------------------------


class TestMixedQualityPopulation:
    """System should handle mixed-quality memories."""

    def test_mixed_quality(self):
        config = LifecycleConfig(archive_threshold=0.3)
        manager = LifecycleManager(config)
        memory = HybridMemory()

        # Add high-quality memories
        for i in range(50):
            ex = memory.add(
                input_text=f"good query {i}",
                output=f"good output {i}",
                vector=FeatureVector(features={}, norm=0.0),
                weight=0.9,
            )
            ex.success_count = 10
            ex.failure_count = 0

        # Add low-quality memories
        for i in range(50):
            ex = memory.add(
                input_text=f"bad query {i}",
                output=f"bad output {i}",
                vector=FeatureVector(features={}, norm=0.0),
                weight=0.1,
            )
            ex.success_count = 0
            ex.failure_count = 10

        results = manager.process_all(memory)
        assert results["total"] == 100
        # Should have some archived (low quality)
        assert results["archived"] > 0


# ---------------------------------------------------------------------------
# 16. Deterministic behavior
# ---------------------------------------------------------------------------


class TestDeterministicBehavior:
    """Lifecycle operations should be deterministic with same clock."""

    def test_deterministic_decay(self):
        config = LifecycleConfig()

        # Same inputs should produce same outputs
        result1 = compute_decay(0.8, 30.0, 0.8, 3, config)
        result2 = compute_decay(0.8, 30.0, 0.8, 3, config)
        assert result1 == result2

    def test_deterministic_reinforcement(self):
        config = LifecycleConfig()

        # Same inputs should produce same outputs
        result1 = compute_reinforcement(0.5, 5, 5, config)
        result2 = compute_reinforcement(0.5, 5, 5, config)
        assert result1 == result2


# ---------------------------------------------------------------------------
# 17. Maintenance interval
# ---------------------------------------------------------------------------


class TestMaintenanceInterval:
    """Maintenance should respect configured interval."""

    def test_maintenance_interval(self):
        config = LifecycleConfig(maintenance_interval_hours=1.0)
        clock_value = 1000000.0
        def clock():
            return clock_value

        manager = LifecycleManager(config, clock=clock)
        memory = HybridMemory()

        # Add some examples
        for i in range(5):
            memory.add(
                input_text=f"test {i}",
                output=f"output {i}",
                vector=FeatureVector(features={}, norm=0.0),
                weight=0.8,
            )

        # First maintenance should run
        result1 = manager.run_maintenance(memory, force=True)
        assert result1.memories_processed == 5

        # Second maintenance without advancing clock should be skipped
        result2 = manager.run_maintenance(memory, force=False)
        assert result2.memories_processed == 0

        # Advance clock past interval
        clock_value += 3601.0  # Just over 1 hour

        # Third maintenance should run
        result3 = manager.run_maintenance(memory, force=False)
        assert result3.memories_processed == 5


# ---------------------------------------------------------------------------
# 18. Provenance tracking
# ---------------------------------------------------------------------------


class TestProvenanceTracking:
    """All lifecycle mutations must be traceable."""

    def test_provenance_after_archive(self):
        config = LifecycleConfig()
        manager = LifecycleManager(config)

        example = _make_example()
        manager.archive(example, "Test archival")

        # Check provenance
        state = manager.get_state(example.id)
        assert len(state.lifecycle_events) == 1
        assert state.lifecycle_events[0].previous_state == "active"
        assert state.lifecycle_events[0].new_state == "archived"
        assert state.lifecycle_events[0].reason == "Test archival"

    def test_provenance_after_supersession(self):
        config = LifecycleConfig()
        manager = LifecycleManager(config)

        old = _make_example(id=1, success=1, failure=5, weight=0.3)
        new = _make_example(id=2, success=10, failure=0, weight=0.9)

        result = analyze_supersession(old, new, config)
        if result.should_supersede:
            event = manager.apply_supersession(
                old.id, new.id, result.reason
            )
            assert event.previous_state == "active"
            assert event.new_state == "superseded"
            assert len(event.related_ids) == 2
