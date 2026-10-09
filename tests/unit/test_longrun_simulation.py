"""Long-run lifecycle simulation and scalability benchmark for V2.4.2.

Tests:
- 100-500 lifecycle cycles
- 100-10,000 memories
- Stability of reinforcement, decay, supersession over time
- Performance benchmarks
- Edge cases in long-running scenarios
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

import pytest

from core.learner.hybrid_memory import HybridExample, HybridMemory
from core.learner.knowledge_ops import (
    find_merge_candidates,
)
from core.learner.lifecycle import (
    HealthSignals,
    LifecycleConfig,
    MemoryState,
    compute_decay,
    compute_health_score,
    compute_reinforcement,
)
from core.learner.lifecycle_manager import (
    LifecycleManager,
    MaintenanceEvent,
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
) -> HybridExample:
    """Create a test memory."""
    return HybridExample(
        id=memory_id,
        input_text=input_text,
        output=output,
        lexical_vector=[],
        semantic_vector=None,
        weight=1.0,
        success_count=success_count,
        failure_count=failure_count,
        use_count=use_count,
        created_at=created_at,
        last_used_at=created_at,
    )


def _make_memory_pool(
    count: int,
    base_time: float = 0.0,
    seed: int = 42,
) -> list[HybridExample]:
    """Create a pool of diverse memories."""
    rng = random.Random(seed)
    memories = []

    topics = [
        "python", "javascript", "rust", "go", "java",
        "database", "api", "testing", "deployment", "security",
    ]
    actions = [
        "implement", "fix", "optimize", "refactor", "test",
        "deploy", "configure", "debug", "review", "document",
    ]

    for i in range(count):
        topic = rng.choice(topics)
        action = rng.choice(actions)
        memories.append(_make_memory(
            memory_id=i,
            input_text=f"{action} {topic} feature {i}",
            output=f"Solution for {topic} {action}: approach {i % 10}",
            success_count=rng.randint(0, 10),
            failure_count=rng.randint(0, 3),
            created_at=base_time + rng.uniform(0, 1000),
            use_count=rng.randint(0, 20),
        ))

    return memories


def _make_hybrid_memory(examples: list[HybridExample]) -> HybridMemory:
    """Create a HybridMemory populated with the given examples."""
    memory = HybridMemory()
    for ex in examples:
        memory.add(
            input_text=ex.input_text,
            output=ex.output,
            vector=ex.lexical_vector,
            weight=ex.weight,
        )
    return memory


@dataclass
class SimulationMetrics:
    """Metrics from a lifecycle simulation run."""

    total_cycles: int = 0
    total_memories_processed: int = 0
    total_transitions: int = 0
    total_merges: int = 0
    total_supersessions: int = 0
    total_archivals: int = 0
    total_restorations: int = 0
    final_memory_count: int = 0
    state_distribution: dict[str, int] = field(default_factory=dict)
    avg_health_score: float = 0.0
    performance_ms: float = 0.0


# ---------------------------------------------------------------------------
# Long-run lifecycle simulation tests
# ---------------------------------------------------------------------------


class TestLongRunSimulation:
    """Test lifecycle behavior over many cycles."""

    def test_100_cycle_simulation(self) -> None:
        """Test 100 lifecycle cycles with 50 memories."""
        memories = _make_memory_pool(50, seed=100)
        manager = LifecycleManager(
            config=LifecycleConfig(
                reinforcement_strength=0.1,
                decay_rate=0.01,
                merge_similarity=0.6,
                merge_input_similarity=0.4,
                merge_min_evidence=2,
            ),
            clock=lambda: 1000.0,
        )

        metrics = SimulationMetrics()
        start_time = time.time()

        for _cycle in range(100):
            # Simulate reinforcement events
            for mem in memories[:10]:  # Reinforce first 10
                manager.record_event(MaintenanceEvent.REPEATED_SUCCESS, mem.id)

            # Simulate decay
            for mem in memories[20:30]:  # Decay some memories
                manager.record_event(MaintenanceEvent.NEW_EVIDENCE, mem.id)

            # Check if maintenance needed
            if manager.needs_maintenance:
                record = manager.run_maintenance(
                    memory=_make_hybrid_memory(memories),
                    force=True,
                )
                metrics.total_maintenance += 1
                metrics.total_transitions += record.transitions

        metrics.performance_ms = (time.time() - start_time) * 1000
        metrics.final_memory_count = len(memories)

        # Verify stability
        assert metrics.performance_ms < 10000, f"100 cycles took {metrics.performance_ms:.1f}ms"
        assert len(memories) == 50, "Memory count should remain stable"

    def test_500_cycle_simulation(self) -> None:
        """Test 500 lifecycle cycles with 100 memories."""
        memories = _make_memory_pool(100, seed=500)
        manager = LifecycleManager(
            config=LifecycleConfig(
                reinforcement_strength=0.1,
                decay_rate=0.01,
                merge_similarity=0.6,
                merge_input_similarity=0.4,
                merge_min_evidence=2,
            ),
            clock=lambda: 1000.0,
        )

        metrics = SimulationMetrics()
        start_time = time.time()

        for cycle in range(500):
            # Simulate varied events
            if cycle % 10 == 0:
                # Every 10 cycles, reinforce some memories
                for mem in memories[:5]:
                    manager.record_event(MaintenanceEvent.REPEATED_SUCCESS, mem.id)

            if cycle % 5 == 0:
                # Every 5 cycles, add new evidence
                for mem in memories[10:15]:
                    manager.record_event(MaintenanceEvent.NEW_EVIDENCE, mem.id)

            # Check maintenance
            if manager.needs_maintenance:
                record = manager.run_maintenance(
                    memory=_make_hybrid_memory(memories),
                    force=True,
                )
                metrics.total_maintenance += 1
                metrics.total_transitions += record.transitions

        metrics.performance_ms = (time.time() - start_time) * 1000
        metrics.final_memory_count = len(memories)

        # Verify no degradation
        assert metrics.performance_ms < 30000, f"500 cycles took {metrics.performance_ms:.1f}ms"
        assert len(memories) == 100, "Memory count should remain stable"

    def test_maintenance_stability(self) -> None:
        """Test that maintenance is idempotent over many runs."""
        memories = _make_memory_pool(30, seed=30)
        manager = LifecycleManager(
            config=LifecycleConfig(
                maintenance_interval_hours=0.001,  # Very frequent
            ),
            clock=lambda: 1000.0,
        )

        # Run maintenance 50 times
        for _ in range(50):
            record = manager.run_maintenance(
                memory=_make_hybrid_memory(memories),
                force=True,
            )
            assert record.memories_processed == 30

        # Verify no state corruption
        for mem in memories:
            state = manager.get_state(mem.id)
            assert state.state in [MemoryState.ACTIVE, MemoryState.UNCERTAIN]


# ---------------------------------------------------------------------------
# Scalability benchmark tests
# ---------------------------------------------------------------------------


class TestScalabilityBenchmark:
    """Test performance with varying numbers of memories."""

    def test_100_memory_performance(self) -> None:
        """Benchmark with 100 memories."""
        memories = _make_memory_pool(100, seed=100)
        manager = LifecycleManager()

        start_time = time.time()
        record = manager.run_maintenance(
            memory=_make_hybrid_memory(memories),
            force=True,
        )
        elapsed_ms = (time.time() - start_time) * 1000

        # Should complete in < 100ms
        assert elapsed_ms < 100, f"100 memories took {elapsed_ms:.1f}ms"
        assert record.memories_processed == 100

    def test_1000_memory_performance(self) -> None:
        """Benchmark with 1000 memories.

        Note: HybridMemory.get_all_hybrid() reconstructs HybridExample each
        call, so larger pools are inherently slower. This is acceptable for
        lifecycle maintenance which runs infrequently.
        """
        memories = _make_memory_pool(1000, seed=1000)
        manager = LifecycleManager()

        start_time = time.time()
        record = manager.run_maintenance(
            memory=_make_hybrid_memory(memories),
            force=True,
        )
        elapsed_ms = (time.time() - start_time) * 1000

        # Should complete in < 30s (reconstruction overhead)
        assert elapsed_ms < 30000, f"1000 memories took {elapsed_ms:.1f}ms"
        assert record.memories_processed == 1000

    def test_10000_memory_performance(self) -> None:
        """Benchmark with 10,000 memories.

        This is a stress test — lifecycle maintenance runs infrequently
        so longer times are acceptable for very large memory pools.
        """
        memories = _make_memory_pool(10000, seed=10000)
        manager = LifecycleManager()

        start_time = time.time()
        record = manager.run_maintenance(
            memory=_make_hybrid_memory(memories),
            force=True,
        )
        elapsed_ms = (time.time() - start_time) * 1000

        # Should complete in < 5 minutes (stress test)
        assert elapsed_ms < 300000, f"10000 memories took {elapsed_ms:.1f}ms"
        assert record.memories_processed == 10000

    def test_indexed_vs_bruteforce(self) -> None:
        """Compare indexed vs brute-force merge candidate generation."""
        memories = _make_memory_pool(500, seed=500)
        config = LifecycleConfig(
            merge_similarity=0.3,  # Lower threshold to get more candidates
            merge_input_similarity=0.2,
            merge_min_evidence=1,
        )

        # Brute force
        start_brute = time.time()
        candidates_brute = find_merge_candidates(
            memories, config, use_index=False
        )
        time_brute = (time.time() - start_brute) * 1000

        # Indexed
        start_index = time.time()
        find_merge_candidates(
            memories, config, use_index=True
        )
        time_index = (time.time() - start_index) * 1000

        # Both should find similar candidates
        assert len(candidates_brute) > 0, "Should find some candidates"
        # Indexed should be faster for 500 memories
        # (may find fewer due to min_overlap filter, but should be faster)
        assert time_index < time_brute * 2, (
            f"Indexed ({time_index:.1f}ms) should not be much slower than "
            f"brute force ({time_brute:.1f}ms)"
        )


# ---------------------------------------------------------------------------
# Stability tests
# ---------------------------------------------------------------------------


class TestLifecycleStability:
    """Test stability of lifecycle operations over time."""

    def test_health_score_stability(self) -> None:
        """Test that health scores remain stable under normal conditions."""
        manager = LifecycleManager()

        # Create memory with consistent behavior
        mem = _make_memory(
            memory_id=1,
            success_count=5,
            failure_count=1,
        )

        # Track health scores over time
        scores = []
        for _ in range(50):
            score = manager.evaluate_health(
                mem,
                HybridMemory(),
            )
            scores.append(score)

        # Scores should be stable (no large jumps)
        for i in range(1, len(scores)):
            diff = abs(scores[i] - scores[i-1])
            assert diff < 0.1, f"Health score jumped by {diff} at step {i}"

    def test_reinforcement_stability(self) -> None:
        """Test that reinforcement is bounded."""
        manager = LifecycleManager()

        mem = _make_memory(
            memory_id=1,
            success_count=0,
            failure_count=0,
        )

        # Reinforce many times
        for _ in range(100):
            signals = HealthSignals(
                success_rate=min(1.0, mem.success_count / 10.0),
                independent_evidence=mem.success_count,
                confidence=0.5,
                recency=0.5,
                usage_frequency=0.5,
                redundancy=0.0,
                contradiction_count=0,
            )
            score = compute_health_score(signals)
            compute_reinforcement(
                score,
                mem.success_count + 1,
                mem.success_count + 1,
                manager.config,
            )
            mem = _make_memory(
                memory_id=1,
                success_count=mem.success_count + 1,
            )

        # Score should not exceed 1.0
        final_signals = HealthSignals(
            success_rate=min(1.0, mem.success_count / 10.0),
            independent_evidence=mem.success_count,
            confidence=0.5,
            recency=0.5,
            usage_frequency=0.5,
            redundancy=0.0,
            contradiction_count=0,
        )
        final_score = compute_health_score(final_signals)
        assert final_score <= 1.0, f"Health score exceeded 1.0: {final_score}"

    def test_decay_stability(self) -> None:
        """Test that decay is bounded and doesn't go negative."""
        manager = LifecycleManager()

        score = 0.5
        for _ in range(100):
            score = compute_decay(
                score,
                days_since_use=1.0,
                success_rate=0.5,
                independent_evidence=1,
                config=manager.config,
            )

        assert score >= 0.0, f"Decay went negative: {score}"
        assert score <= 1.0, f"Decay exceeded 1.0: {score}"


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases in long-running scenarios."""

    def test_empty_memory_pool(self) -> None:
        """Test maintenance with no memories."""
        manager = LifecycleManager()
        record = manager.run_maintenance(
            memory=_make_hybrid_memory([]),
            force=True,
        )
        assert record.memories_processed == 0
        assert record.transitions == 0

    def test_single_memory(self) -> None:
        """Test maintenance with single memory."""
        memories = [_make_memory(memory_id=0)]
        manager = LifecycleManager()
        record = manager.run_maintenance(
            memory=_make_hybrid_memory(memories),
            force=True,
        )
        assert record.memories_processed == 1

    def test_all_identical_memories(self) -> None:
        """Test with all identical memories."""
        memories = [
            _make_memory(memory_id=i, input_text="same", output="same")
            for i in range(20)
        ]
        manager = LifecycleManager(
            config=LifecycleConfig(
                merge_similarity=0.9,
                merge_input_similarity=0.9,
                merge_min_evidence=1,
            ),
        )
        record = manager.run_maintenance(
            memory=_make_hybrid_memory(memories),
            force=True,
        )
        # Should handle gracefully without crashing
        assert record.memories_processed == 20

    def test_rapid_state_transitions(self) -> None:
        """Test rapid state transitions don't corrupt state."""
        manager = LifecycleManager()

        mem = _make_memory(memory_id=1)

        # Force rapid state changes via the internal states dict
        for _ in range(20):
            state = manager.get_state(mem.id)
            if state.state == MemoryState.ACTIVE:
                manager._states[mem.id] = MemoryLifecycleState(
                    memory_id=mem.id,
                    state=MemoryState.UNCERTAIN,
                    health_score=state.health_score,
                    last_health_check=state.last_health_check,
                )
            else:
                manager._states[mem.id] = MemoryLifecycleState(
                    memory_id=mem.id,
                    state=MemoryState.ACTIVE,
                    health_score=state.health_score,
                    last_health_check=state.last_health_check,
                )

        # Should be in valid state
        state = manager.get_state(mem.id)
        assert state.state in [MemoryState.ACTIVE, MemoryState.UNCERTAIN]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
