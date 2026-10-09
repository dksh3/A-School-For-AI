"""Tests for V2.4 knowledge lifecycle system."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from core.learner.hybrid_memory import HybridMemory
from core.learner.knowledge_ops import (
    RedundancyType,
    analyze_redundancy,
    analyze_supersession,
    archive_memory,
    find_merge_candidates,
    is_eligible_for_archive,
)
from core.learner.lifecycle import (
    HealthSignals,
    LifecycleConfig,
    MemoryState,
    compute_decay,
    compute_health_score,
    compute_reinforcement,
)
from core.learner.lifecycle_manager import LifecycleManager

# ---------------------------------------------------------------------------
# Lifecycle states
# ---------------------------------------------------------------------------


class TestMemoryState:
    def test_states_exist(self):
        assert MemoryState.ACTIVE.value == "active"
        assert MemoryState.UNCERTAIN.value == "uncertain"
        assert MemoryState.SUPERSEDED.value == "superseded"
        assert MemoryState.ARCHIVED.value == "archived"


# ---------------------------------------------------------------------------
# Health computation
# ---------------------------------------------------------------------------


class TestHealthComputation:
    def test_healthy_memory(self):
        signals = HealthSignals(
            success_rate=0.9,
            independent_evidence=5,
            confidence=0.8,
            recency=0.9,
            usage_frequency=0.7,
            redundancy=0.0,
            contradiction_count=0,
        )
        score = compute_health_score(signals)
        assert score > 0.7

    def test_weak_memory(self):
        signals = HealthSignals(
            success_rate=0.2,
            independent_evidence=0,
            confidence=0.1,
            recency=0.1,
            usage_frequency=0.0,
            redundancy=0.0,
            contradiction_count=0,
        )
        score = compute_health_score(signals)
        assert score < 0.4

    def test_bounded(self):
        signals = HealthSignals(
            success_rate=1.0,
            independent_evidence=100,
            confidence=1.0,
            recency=1.0,
            usage_frequency=1.0,
            redundancy=0.0,
            contradiction_count=0,
        )
        score = compute_health_score(signals)
        assert 0.0 <= score <= 1.0

    def test_redundancy_reduces_health(self):
        base = HealthSignals(
            success_rate=0.8,
            independent_evidence=3,
            confidence=0.7,
            recency=0.8,
            usage_frequency=0.5,
            redundancy=0.0,
            contradiction_count=0,
        )
        redundant = HealthSignals(
            success_rate=0.8,
            independent_evidence=3,
            confidence=0.7,
            recency=0.8,
            usage_frequency=0.5,
            redundancy=1.0,
            contradiction_count=0,
        )
        assert compute_health_score(redundant) < compute_health_score(base)


# ---------------------------------------------------------------------------
# Decay
# ---------------------------------------------------------------------------


class TestDecay:
    def test_no_time_no_decay(self):
        config = LifecycleConfig()
        result = compute_decay(0.8, 0.0, 0.8, 3, config)
        assert result == 0.8

    def test_strong_evidence_slows_decay(self):
        config = LifecycleConfig()
        strong = compute_decay(0.8, 30.0, 0.9, 5, config)
        weak = compute_decay(0.8, 30.0, 0.2, 0, config)
        assert strong > weak

    def test_decay_floor(self):
        config = LifecycleConfig(decay_min=0.1)
        result = compute_decay(0.5, 365.0, 0.1, 0, config)
        assert result >= 0.1

    def test_decay_bounded(self):
        config = LifecycleConfig()
        result = compute_decay(0.8, 30.0, 0.5, 2, config)
        assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Reinforcement
# ---------------------------------------------------------------------------


class TestReinforcement:
    def test_no_success_no_change(self):
        config = LifecycleConfig()
        result = compute_reinforcement(0.5, 0, 0, config)
        assert result == 0.5

    def test_single_success(self):
        config = LifecycleConfig()
        result = compute_reinforcement(0.5, 1, 1, config)
        assert result > 0.5

    def test_diminishing_returns(self):
        config = LifecycleConfig()
        r1 = compute_reinforcement(0.5, 1, 1, config)
        r2 = compute_reinforcement(0.5, 2, 2, config)
        r3 = compute_reinforcement(0.5, 5, 5, config)
        # Each additional success adds less
        assert (r2 - 0.5) < (r1 - 0.5) * 2
        assert (r3 - 0.5) < (r2 - 0.5) * 3

    def test_bounded(self):
        config = LifecycleConfig()
        result = compute_reinforcement(0.9, 100, 100, config)
        assert result <= 1.0


# ---------------------------------------------------------------------------
# Supersession
# ---------------------------------------------------------------------------


class TestSupersession:
    def _make_example(self, output: str, success: int, failure: int, weight: float = 1.0):
        from core.learner.feature_extractor import FeatureVector
        from core.learner.hybrid_memory import HybridExample

        return HybridExample(
            id=1,
            input_text="test query",
            output=output,
            lexical_vector=FeatureVector(features={}, norm=0.0),
            weight=weight,
            success_count=success,
            failure_count=failure,
            created_at=time.time() - 86400,
            last_used_at=time.time() - 3600,
            use_count=10,
        )

    def test_same_output_no_supersession(self):
        old = self._make_example("sorted(x)", 5, 1)
        new = self._make_example("sorted(x)", 10, 0)
        config = LifecycleConfig()
        result = analyze_supersession(old, new, config)
        assert not result.should_supersede

    def test_different_output_needs_evidence(self):
        old = self._make_example("sorted(x)", 10, 0, weight=0.8)
        new = self._make_example("list.sort()", 2, 0, weight=0.5)
        config = LifecycleConfig()
        result = analyze_supersession(old, new, config)
        # Old has more evidence, should not be superseded
        assert not result.should_supersede

    def test_stronger_new_supersedes(self):
        old = self._make_example("sorted(x)", 1, 5, weight=0.3)
        new = self._make_example("list.sort()", 10, 0, weight=0.9)
        config = LifecycleConfig(supersession_threshold=0.1)
        result = analyze_supersession(old, new, config)
        # New has much stronger evidence
        assert result.should_supersede


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


class TestMerging:
    def _make_example(self, input_text: str, output: str, success: int = 5, failure: int = 0):
        from core.learner.feature_extractor import FeatureVector
        from core.learner.hybrid_memory import HybridExample

        return HybridExample(
            id=1,
            input_text=input_text,
            output=output,
            lexical_vector=FeatureVector(features={}, norm=0.0),
            weight=1.0,
            success_count=success,
            failure_count=failure,
        )

    def test_similar_outputs_are_candidates(self):
        a = self._make_example("sort a list of numbers", "sorted(x)")
        b = self._make_example("sort list of numbers", "sorted(x)")
        config = LifecycleConfig()
        candidates = find_merge_candidates([a, b], config)
        assert len(candidates) == 1

    def test_different_outputs_not_candidates(self):
        a = self._make_example("sort a list", "sorted(x)")
        b = self._make_example("sort a list", "list.sort()")
        config = LifecycleConfig()
        candidates = find_merge_candidates([a, b], config)
        # Outputs are different
        assert len(candidates) == 0


# ---------------------------------------------------------------------------
# Redundancy
# ---------------------------------------------------------------------------


class TestRedundancy:
    def _make_example(self, input_text: str, output: str, success: int = 5, failure: int = 0):
        from core.learner.feature_extractor import FeatureVector
        from core.learner.hybrid_memory import HybridExample

        return HybridExample(
            id=1,
            input_text=input_text,
            output=output,
            lexical_vector=FeatureVector(features={}, norm=0.0),
            weight=1.0,
            success_count=success,
            failure_count=failure,
        )

    def test_exact_duplicate(self):
        a = self._make_example("sort a list", "sorted(x)")
        b = self._make_example("sort a list", "sorted(x)")
        config = LifecycleConfig()
        result = analyze_redundancy(a, b, config)
        assert result.type == RedundancyType.EXACT_DUPLICATE
        assert result.should_consolidate

    def test_same_output_different_input(self):
        a = self._make_example("sort a list", "sorted(x)")
        b = self._make_example("order items", "sorted(x)")
        config = LifecycleConfig()
        result = analyze_redundancy(a, b, config)
        # Same output = either NORMALIZED_DUPLICATE or SEMANTIC_DUPLICATE
        assert result.type in (
            RedundancyType.NORMALIZED_DUPLICATE,
            RedundancyType.SEMANTIC_DUPLICATE,
        )
        assert result.should_consolidate

    def test_different_output(self):
        a = self._make_example("sort a list", "sorted(x)")
        b = self._make_example("sort a list", "list.sort()")
        config = LifecycleConfig()
        result = analyze_redundancy(a, b, config)
        assert result.type in (
            RedundancyType.RELATED_BUT_INDEPENDENT,
            RedundancyType.GENUINELY_DISTINCT,
        )

    def test_preserves_evidence(self):
        a = self._make_example("sort a list", "sorted(x)", success=10)
        b = self._make_example("sort a list", "sorted(x)", success=5)
        config = LifecycleConfig()
        result = analyze_redundancy(a, b, config)
        assert result.combined_evidence == 15


# ---------------------------------------------------------------------------
# Archiving
# ---------------------------------------------------------------------------


class TestArchiving:
    def _make_example(self, success: int = 5, failure: int = 0):
        from core.learner.feature_extractor import FeatureVector
        from core.learner.hybrid_memory import HybridExample

        return HybridExample(
            id=1,
            input_text="test",
            output="test",
            lexical_vector=FeatureVector(features={}, norm=0.0),
            weight=1.0,
            success_count=success,
            failure_count=failure,
            use_count=10,
        )

    def test_low_health_eligible(self):
        example = self._make_example(0, 3)
        config = LifecycleConfig(archive_threshold=0.1)
        eligible, reason = is_eligible_for_archive(example, 0.05, config)
        assert eligible

    def test_high_health_not_eligible(self):
        example = self._make_example(10, 0)
        config = LifecycleConfig()
        eligible, reason = is_eligible_for_archive(example, 0.8, config)
        assert not eligible

    def test_archive_creates_event(self):
        example = self._make_example(0, 5)
        LifecycleConfig()
        state, event = archive_memory(example, "Low health", MemoryState.ACTIVE)
        assert state == MemoryState.ARCHIVED
        assert event.previous_state == "active"
        assert event.new_state == "archived"


# ---------------------------------------------------------------------------
# Lifecycle manager
# ---------------------------------------------------------------------------


class TestLifecycleManager:
    def _make_example(self, id: int = 1, output: str = "test", success: int = 5, failure: int = 0):
        from core.learner.feature_extractor import FeatureVector
        from core.learner.hybrid_memory import HybridExample

        return HybridExample(
            id=id,
            input_text="test query",
            output=output,
            lexical_vector=FeatureVector(features={}, norm=0.0),
            weight=1.0,
            success_count=success,
            failure_count=failure,
            use_count=10,
            created_at=time.time() - 86400,
            last_used_at=time.time() - 3600,
        )

    def test_initial_state(self):
        manager = LifecycleManager()
        state = manager.get_state(1)
        assert state.state == MemoryState.ACTIVE

    def test_reinforce(self):
        manager = LifecycleManager()
        example = self._make_example()
        old_weight = example.weight
        new_weight = manager.reinforce(example)
        assert new_weight >= old_weight

    def test_archive(self):
        manager = LifecycleManager()
        example = self._make_example()
        event = manager.archive(example, "Test archival")
        assert event.new_state == "archived"
        state = manager.get_state(example.id)
        assert state.state == MemoryState.ARCHIVED

    def test_restore(self):
        manager = LifecycleManager()
        example = self._make_example()
        manager.archive(example, "Test")
        event = manager.restore(example.id, "Test restoration")
        assert event.new_state == "active"
        state = manager.get_state(example.id)
        assert state.state == MemoryState.ACTIVE

    def test_supersession(self):
        manager = LifecycleManager()
        old = self._make_example(1, "sorted(x)", 1, 5)
        new = self._make_example(2, "list.sort()", 10, 0)
        result = manager.analyze_supersession(old, new)
        # New has stronger evidence
        assert result.should_supersede

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = LifecycleManager()
            example = self._make_example()
            manager.reinforce(example)

            # Save
            manager.save(Path(tmpdir))

            # Load
            loaded = LifecycleManager.load(Path(tmpdir))
            assert loaded.config.decay_rate == manager.config.decay_rate

    def test_process_all(self):
        manager = LifecycleManager()
        memory = HybridMemory()
        from core.learner.feature_extractor import FeatureVector

        # Add some examples
        for i in range(5):
            memory.add(
                input_text=f"test {i}",
                output=f"output {i}",
                vector=FeatureVector(features={}, norm=0.0),
                weight=0.8,
            )

        results = manager.process_all(memory)
        assert results["total"] == 5
        assert results["active"] + results["uncertain"] + results["archived"] == 5
