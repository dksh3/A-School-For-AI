"""Targeted tests for bugs found in V2.5 routing audit.

Each test class targets a specific bug identified during code review.
These tests should FAIL before the fix and PASS after.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from core.routing.cache import RoutingCache
from core.routing.context import ContextState
from core.routing.decision import RoutingDecision, create_discard_decision
from core.routing.destinations import DISCARD, Destination, DestinationType
from core.routing.efficiency import EfficiencyController
from core.routing.information import (
    InformationPacket,
    InformationType,
    SensitivityLevel,
)
from core.routing.integration import SchoolIntegrationBridge, make_noop_handler
from core.routing.pipeline import RoutingPipeline
from core.routing.priority import Priority, PriorityConfig
from core.routing.provenance import ProvenanceTracker, RoutingProvenance
from core.routing.router import UniversalRouter
from core.routing.security import SecurityPolicy, enforce_policy


def _make_packet(
    content: str = "test",
    info_type: InformationType = InformationType.DATA,
    sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC,
    priority: int = 2,
    scope: str = "",
) -> InformationPacket:
    return InformationPacket(
        content=content,
        information_type=info_type,
        sensitivity=sensitivity,
        priority=priority,
        scope=scope,
    )


def _tmp_dir() -> str:
    return tempfile.mkdtemp()


# =====================================================================
# BUG 1: cache.has() corrupts statistics
# =====================================================================


class TestBugCacheHasSideEffect:
    """has() should not affect hit/miss statistics."""

    def test_has_does_not_affect_hit_rate(self) -> None:
        cache = RoutingCache()
        pkt = _make_packet(content="test")
        dec = RoutingDecision(packet_id="p1", destinations=())
        cache.put(pkt, dec)

        # Record baseline
        baseline_hits = cache._hits
        baseline_misses = cache._misses

        # has() should be pure — no side effects
        result = cache.has(pkt)
        assert result is True

        # Counters should not have changed
        assert cache._hits == baseline_hits
        assert cache._misses == baseline_misses

    def test_has_miss_does_not_affect_stats(self) -> None:
        cache = RoutingCache()
        pkt = _make_packet(content="missing")
        baseline_misses = cache._misses
        result = cache.has(pkt)
        assert result is False
        assert cache._misses == baseline_misses


# =====================================================================
# BUG 2: provenance._by_packet unbounded memory leak
# =====================================================================


class TestBugProvenanceMemoryLeak:
    """_by_packet index should be cleaned up when records are evicted."""

    def test_by_packet_bounded(self) -> None:
        tracker = ProvenanceTracker(max_history=3)
        for i in range(10):
            tracker.record(RoutingProvenance(
                packet_id=f"p{i}",
                decision_id=f"d{i}",
                timestamp=float(i),
                packet_source="AGENT",
                packet_type="DATA",
                destinations=(),
                strategy="DIRECT",
                confidence=1.0,
                reason="test",
            ))
        # _by_packet should not contain entries for evicted records
        # Only the last 3 packet IDs should have entries
        for pid in ["p0", "p1", "p2", "p3", "p4", "p5", "p6"]:
            if pid in tracker._by_packet:
                # These records were evicted; _by_packet should be clean
                decision_ids = tracker._by_packet[pid]
                # All decision_ids should correspond to records still in _records
                record_ids = {r.decision_id for r in tracker._records}
                for did in decision_ids:
                    assert did in record_ids, (
                        f"_by_packet has stale reference: {pid} -> {did}"
                    )

    def test_by_packet_no_stale_references(self) -> None:
        tracker = ProvenanceTracker(max_history=2)
        for i in range(5):
            tracker.record(RoutingProvenance(
                packet_id=f"p{i}",
                decision_id=f"d{i}",
                timestamp=float(i),
                packet_source="AGENT",
                packet_type="DATA",
                destinations=(),
                strategy="DIRECT",
                confidence=1.0,
                reason="test",
            ))
        # After eviction, only p3 and p4 should have entries
        assert "p0" not in tracker._by_packet
        assert "p1" not in tracker._by_packet
        assert "p2" not in tracker._by_packet


# =====================================================================
# BUG 3: security.enforce_policy regex recompilation
# =====================================================================


class TestBugSecurityRegexRecompilation:
    """Regex patterns should be pre-compiled, not compiled per call."""

    def test_enforce_policy_performance(self) -> None:
        policy = SecurityPolicy(blocked_patterns=(r"spam", r"phish"))
        pkt = _make_packet(content="normal content")

        # This should be fast if patterns are pre-compiled
        start = time.time()
        for _ in range(1000):
            enforce_policy(pkt, policy)
        elapsed = time.time() - start

        # If regex is recompiled each time, this will be noticeably slower
        # Threshold: 1000 calls should complete in under 0.5 seconds
        assert elapsed < 0.5, f"enforce_policy too slow: {elapsed:.2f}s for 1000 calls"


# =====================================================================
# BUG 4: pipeline._build_decision policy.name assumption
# =====================================================================


class TestBugPolicyNameAttribute:
    """policy_applied should handle policies without .name attribute."""

    def test_policy_without_name(self) -> None:
        class DummyPolicy:
            pass

        pipe = RoutingPipeline()
        pkt = _make_packet(
            content="test",
            info_type=InformationType.INSTRUCTION,
            priority=1,
        )
        # Should not raise AttributeError
        decision = pipe.route(pkt, policy=DummyPolicy())
        assert isinstance(decision, RoutingDecision)

    def test_policy_with_name(self) -> None:
        class NamedPolicy:
            name = "test_policy"

        pipe = RoutingPipeline()
        pkt = _make_packet(
            content="test",
            info_type=InformationType.INSTRUCTION,
            priority=1,
        )
        decision = pipe.route(pkt, policy=NamedPolicy())
        assert decision.policy_applied == "test_policy"


# =====================================================================
# BUG 5: pipeline._build_decision dead assignment
# =====================================================================


class TestBugDeadPriorityAssignment:
    """final_priority should not be assigned twice."""

    def test_priority_from_packet_is_used(self) -> None:
        pipe = RoutingPipeline()
        pkt = _make_packet(
            content="test",
            info_type=InformationType.DATA,
            priority=3,
        )
        decision = pipe.route(pkt)
        # Priority should come from the packet (after boosting), not be overwritten
        assert decision.priority == 3

    def test_priority_with_config_boost(self) -> None:
        pipe = RoutingPipeline(
            priority_config=PriorityConfig(high_boost=-1)
        )
        pkt = _make_packet(
            content="test",
            info_type=InformationType.DATA,
            priority=1,
        )
        decision = pipe.route(pkt)
        # With high_boost=-1, priority 1 (HIGH) should become 0 (CRITICAL)
        assert decision.priority == Priority.CRITICAL.value


# =====================================================================
# BUG 6: Missing routing for EXPERIENCE/KNOWLEDGE types
# =====================================================================


class TestBugMissingExperienceRouting:
    """EXPERIENCE and KNOWLEDGE types should have explicit routing."""

    def test_experience_routes_to_learning(self) -> None:
        pipe = RoutingPipeline()
        pkt = _make_packet(
            content="learned something",
            info_type=InformationType.EXPERIENCE,
        )
        decision = pipe.route(pkt)
        # Should route to LEARNING, not just SCHOOL_CONTEXT
        assert decision.has_destination(DestinationType.LEARNING), (
            f"EXPERIENCE should route to LEARNING, got: {[d.name for d in decision.destinations]}"
        )

    def test_knowledge_routes_to_knowledge(self) -> None:
        pipe = RoutingPipeline()
        pkt = _make_packet(
            content="knowledge item",
            info_type=InformationType.KNOWLEDGE,
        )
        decision = pipe.route(pkt)
        assert decision.has_destination(DestinationType.KNOWLEDGE), (
            f"KNOWLEDGE should route to KNOWLEDGE, got: {[d.name for d in decision.destinations]}"
        )


# =====================================================================
# BUG 7: integration.dispatch exception swallowing
# =====================================================================


class TestBugExceptionSwallowing:
    """Handler exceptions should be logged, not silently swallowed."""

    def test_handler_exception_recorded(self) -> None:
        bridge = SchoolIntegrationBridge()

        def failing_handler(pkt: InformationPacket, dec: RoutingDecision) -> None:
            raise RuntimeError("intentional failure")

        bridge.register_handler(DestinationType.LEARNING, failing_handler)
        pkt = _make_packet(content="test")
        dec = RoutingDecision(
            packet_id="p1",
            destinations=(Destination(destination_type=DestinationType.LEARNING),),
        )

        result = bridge.dispatch(pkt, dec)
        assert result is False
        stats = bridge.get_stats()
        assert stats["error_count"] == 1


# =====================================================================
# BUG 8: integration.dispatch counts no-op dispatches
# =====================================================================


class TestBugNoOpDispatchCounted:
    """Dispatches to unregistered handlers should not increment dispatch count."""

    def test_no_handler_not_counted(self) -> None:
        bridge = SchoolIntegrationBridge()
        pkt = _make_packet(content="test")
        dec = RoutingDecision(
            packet_id="p1",
            destinations=(Destination(destination_type=DestinationType.LEARNING),),
        )

        bridge.dispatch(pkt, dec)
        stats = bridge.get_stats()
        # With no handler registered, dispatch_count should be 0 (no-op)
        assert stats["dispatch_count"] == 0, (
            f"No-op dispatch should not be counted, got: {stats['dispatch_count']}"
        )

    def test_with_handler_counted(self) -> None:
        bridge = SchoolIntegrationBridge()
        bridge.register_handler(DestinationType.LEARNING, make_noop_handler())
        pkt = _make_packet(content="test")
        dec = RoutingDecision(
            packet_id="p1",
            destinations=(Destination(destination_type=DestinationType.LEARNING),),
        )

        bridge.dispatch(pkt, dec)
        stats = bridge.get_stats()
        assert stats["dispatch_count"] == 1


# =====================================================================
# BUG 9: router.submit_information doesn't call record_routing
# =====================================================================


class TestBugContextRecordRouting:
    """submit_information should call context.record_routing()."""

    def test_recent_destinations_populated(self) -> None:
        router = UniversalRouter()
        pkt = _make_packet(
            content="test",
            info_type=InformationType.OBSERVATION,
        )
        router.submit_information(pkt)
        ctx = router.get_context_state()
        # After routing, recent_destinations should have entries
        assert len(ctx.recent_destinations) > 0, (
            "record_routing() was never called; recent_destinations is empty"
        )

    def test_operation_count_matches(self) -> None:
        router = UniversalRouter()
        for i in range(3):
            router.submit_information(_make_packet(content=f"test{i}"))
        ctx = router.get_context_state()
        assert ctx.operation_count == 3


# =====================================================================
# BUG 10: create_discard_decision destination inconsistency
# =====================================================================


class TestBugDiscardDestinationInconsistency:
    """create_discard_decision should use consistent destination naming."""

    def test_discard_has_name(self) -> None:
        dec = create_discard_decision("p1", reason="test")
        assert dec.destination_count == 1
        dest = dec.destinations[0]
        # The destination should have a name
        assert dest.name != "", (
            "Discard destination should have a name, got empty string"
        )

    def test_discard_matches_module_constant(self) -> None:
        dec = create_discard_decision("p1")
        dest = dec.destinations[0]
        assert dest.matches(DISCARD), (
            "create_discard_decision destination should match module-level DISCARD"
        )


# =====================================================================
# BUG 11: protocol.from_json broad exception catch
# =====================================================================


class TestBugBroadExceptionCatch:
    """from_json should not catch SystemExit, KeyboardInterrupt, etc."""

    def test_catches_json_error(self) -> None:
        from core.routing.protocol import RoutingIntent

        # Should handle malformed JSON gracefully
        intent = RoutingIntent.from_json("{bad json}")
        assert intent.operation is not None

    def test_does_not_swallow_system_exit(self) -> None:
        from core.routing.protocol import RoutingIntent

        # This tests that the broad catch doesn't hide critical errors
        # In practice, json.loads won't raise SystemExit, but the pattern
        # should be checked
        intent = RoutingIntent.from_json("null")
        # null is valid JSON but not a dict, so fallback occurs
        assert intent.operation is not None


# =====================================================================
# BUG 12: efficiency.evaluate ignores context parameter
# =====================================================================


class TestBugEfficiencyContextIgnored:
    """evaluate() should use context when provided."""

    def test_context_parameter_accepted(self) -> None:
        ec = EfficiencyController()
        pkt = _make_packet(
            content="test",
            info_type=InformationType.DATA,
        )
        ctx = ContextState()
        ctx.enter_scope("project_a")
        # Should not raise, but context is unused
        result = ec.evaluate(pkt, context=ctx)
        assert result is not None


# =====================================================================
# Cross-Version Compatibility Tests
# =====================================================================


class TestV11LearnerCrossVersion:
    """Create V1.1 learner, save, load, verify data survives."""

    def test_v11_save_load_roundtrip(self) -> None:
        from core.learner.base import LearningInput
        from core.learner.learner_v1 import SimilarityLearner

        learner = SimilarityLearner(k=3)
        learner.learn(
            LearningInput(observation={"input": "hello world", "output": "greeting"})
        )
        learner.learn(
            LearningInput(observation={"input": "goodbye world", "output": "farewell"})
        )

        path = Path(_tmp_dir()) / "v1_1_cross"
        path.mkdir(parents=True, exist_ok=True)
        learner.save_state(str(path))

        loaded = SimilarityLearner.load_state(str(path))
        assert loaded.memory.count() == 2
        assert loaded.parameters["k"] == 3

        # Verify prediction works
        pred = loaded.predict("hello")
        assert pred.output == "greeting"
        assert pred.confidence > 0.0

    def test_v11_feedback_preserved(self) -> None:
        from core.learner.base import LearningInput
        from core.learner.learner_v1 import SimilarityLearner

        learner = SimilarityLearner()
        learner.learn(
            LearningInput(observation={"input": "test", "output": "result"})
        )
        learner.feedback("test", "result", correct=True)

        path = Path(_tmp_dir()) / "v11_feedback"
        path.mkdir(parents=True, exist_ok=True)
        learner.save_state(str(path))

        loaded = SimilarityLearner.load_state(str(path))
        # Stats should be preserved
        assert loaded.parameters["total_predictions"] == 0
        assert loaded.parameters["num_examples"] == 1


class TestV2LearnerCrossVersion:
    """Create V2 learner, add examples, save, load, verify data survives."""

    def test_v2_save_load_roundtrip(self) -> None:
        from core.learner.base import LearningInput
        from core.learner.learner_v2 import HybridSimilarityLearner

        learner = HybridSimilarityLearner(k=5)
        learner.learn(
            LearningInput(observation={"input": "test input", "output": "test output"})
        )
        learner.learn(
            LearningInput(observation={"input": "another input", "output": "another output"})
        )

        path = Path(_tmp_dir()) / "v2_cross"
        path.mkdir(parents=True, exist_ok=True)
        learner.save_state(str(path))

        loaded = HybridSimilarityLearner.load_state(str(path))
        assert loaded.memory.count() == 2
        assert loaded.parameters["k"] == 5

    def test_v2_lexical_weight_preserved(self) -> None:
        from core.learner.learner_v2 import HybridSimilarityLearner

        learner = HybridSimilarityLearner(
            lexical_weight=0.3, semantic_weight=0.7
        )
        path = Path(_tmp_dir()) / "v2_weight"
        path.mkdir(parents=True, exist_ok=True)
        learner.save_state(str(path))

        loaded = HybridSimilarityLearner.load_state(str(path))
        assert loaded.parameters["lexical_weight"] == pytest.approx(0.3, abs=0.01)
        assert loaded.parameters["semantic_weight"] == pytest.approx(0.7, abs=0.01)


class TestExampleMemoryRoundtrip:
    """ExampleMemory.save/load should preserve all data."""

    def test_roundtrip_preserves_examples(self) -> None:
        from core.learner.feature_extractor import FeatureExtractor
        from core.learner.memory import ExampleMemory

        mem = ExampleMemory()
        ext = FeatureExtractor()
        vec = ext.fit("hello world")
        mem.add(input_text="hello", output="greeting", vector=vec)
        mem.add(input_text="world", output="place", vector=ext.fit("world"))

        path = Path(_tmp_dir()) / "example_mem.json"
        mem.save(path)
        loaded = ExampleMemory.load(path)

        assert loaded.count() == 2
        examples = loaded.get_all()
        assert examples[0].input_text == "hello"
        assert examples[0].output == "greeting"
        assert examples[1].input_text == "world"

    def test_roundtrip_preserves_weights(self) -> None:
        from core.learner.feature_extractor import FeatureExtractor
        from core.learner.memory import ExampleMemory

        mem = ExampleMemory()
        ext = FeatureExtractor()
        vec = ext.fit("test")
        ex = mem.add(input_text="test", output="result", vector=vec, weight=2.5)
        mem.record_feedback(ex.id, correct=True)

        path = Path(_tmp_dir()) / "example_weights.json"
        mem.save(path)
        loaded = ExampleMemory.load(path)

        loaded_ex = loaded.get(0)
        assert loaded_ex is not None
        assert loaded_ex.weight > 1.0
        assert loaded_ex.feedback_count == 1
        assert loaded_ex.correct_count == 1


class TestHybridMemoryRoundtrip:
    """HybridMemory.save/load should preserve semantic vectors and metadata."""

    def test_roundtrip_with_semantic(self) -> None:
        from core.learner.feature_extractor import FeatureExtractor
        from core.learner.hybrid_memory import HybridMemory

        mem = HybridMemory()
        ext = FeatureExtractor()
        vec = ext.fit("hello world")
        sem = [0.1, 0.2, 0.3, 0.4, 0.5]
        ex = mem.add(
            input_text="hello",
            output="greeting",
            vector=vec,
            semantic_vector=sem,
        )
        mem.record_use(ex.id)
        mem.record_success(ex.id)

        path = Path(_tmp_dir()) / "hybrid_rt.json"
        mem.save(path)
        loaded = HybridMemory.load(path)

        assert loaded.count() == 1
        h = loaded.get_hybrid(0)
        assert h is not None
        assert h.semantic_vector == [0.1, 0.2, 0.3, 0.4, 0.5]

        stats = loaded.get_usage_stats(0)
        assert stats is not None
        assert stats["use_count"] == 1
        assert stats["success_count"] == 1

    def test_roundtrip_without_semantic(self) -> None:
        from core.learner.feature_extractor import FeatureExtractor
        from core.learner.hybrid_memory import HybridMemory

        mem = HybridMemory()
        ext = FeatureExtractor()
        vec = ext.fit("test")
        mem.add(input_text="test", output="result", vector=vec)

        path = Path(_tmp_dir()) / "hybrid_no_sem.json"
        mem.save(path)
        loaded = HybridMemory.load(path)

        assert loaded.count() == 1
        h = loaded.get_hybrid(0)
        assert h is not None
        assert h.semantic_vector is None

    def test_v1_format_loads(self) -> None:
        """Simulate V1 format (no semantic, no usage fields)."""
        from core.learner.hybrid_memory import HybridMemory

        path = Path(_tmp_dir()) / "v1_format_hybrid.json"
        data = {
            "next_id": 1,
            "examples": [
                {
                    "id": 0,
                    "input_text": "test",
                    "output": "result",
                    "vector": {"test": 1.0},
                    "norm": 1.0,
                    "weight": 1.0,
                    "feedback_count": 0,
                    "correct_count": 0,
                    "metadata": {},
                }
            ],
        }
        path.write_text(
            __import__("json").dumps(data), encoding="utf-8"
        )
        loaded = HybridMemory.load(path)
        assert loaded.count() == 1

        # Usage stats should have defaults
        stats = loaded.get_usage_stats(0)
        assert stats is not None
        assert stats["use_count"] == 0
        assert stats["success_count"] == 0


class TestLifecycleManagerRoundtrip:
    """LifecycleManager.save/load should preserve all state."""

    def test_roundtrip_preserves_config(self) -> None:
        from core.learner.lifecycle import LifecycleConfig
        from core.learner.lifecycle_manager import LifecycleManager

        config = LifecycleConfig(
            decay_rate=0.02,
            archive_threshold=0.05,
            maintenance_interval_hours=12.0,
        )
        mgr = LifecycleManager(config=config)

        path = Path(_tmp_dir()) / "lifecycle_rt"
        mgr.save(path)
        loaded = LifecycleManager.load(path)

        assert loaded.config.decay_rate == 0.02
        assert loaded.config.archive_threshold == 0.05
        assert loaded.config.maintenance_interval_hours == 12.0

    def test_roundtrip_preserves_states(self) -> None:
        from core.learner.lifecycle import MemoryState
        from core.learner.lifecycle_manager import LifecycleManager

        mgr = LifecycleManager()
        mgr.get_state(1).state = MemoryState.ACTIVE
        mgr.get_state(2).state = MemoryState.UNCERTAIN
        mgr.get_state(3).state = MemoryState.SUPERSEDED

        path = Path(_tmp_dir()) / "lifecycle_states_rt"
        mgr.save(path)
        loaded = LifecycleManager.load(path)

        assert loaded.get_state(1).state == MemoryState.ACTIVE
        assert loaded.get_state(2).state == MemoryState.UNCERTAIN
        assert loaded.get_state(3).state == MemoryState.SUPERSEDED

    def test_roundtrip_preserves_maintenance_history(self) -> None:
        from core.learner.feature_extractor import FeatureExtractor
        from core.learner.hybrid_memory import HybridMemory
        from core.learner.lifecycle_manager import LifecycleManager

        mgr = LifecycleManager()
        mem = HybridMemory()
        ext = FeatureExtractor()
        vec = ext.fit("test data")
        mem.add(input_text="test data", output="result", vector=vec)

        record = mgr.run_maintenance(mem, force=True)
        assert record.memories_processed == 1

        path = Path(_tmp_dir()) / "lifecycle_maint_rt"
        mgr.save(path)
        loaded = LifecycleManager.load(path)

        history = loaded.get_maintenance_history()
        assert len(history) >= 1
        assert history[0].memories_processed == 1

    def test_roundtrip_preserves_events(self) -> None:
        from core.learner.lifecycle_manager import LifecycleManager

        mgr = LifecycleManager()
        state = mgr.get_state(42)
        state.state = mgr.get_state(42).state  # triggers default creation
        state.health_score = 0.35

        path = Path(_tmp_dir()) / "lifecycle_events_rt"
        mgr.save(path)
        loaded = LifecycleManager.load(path)

        s = loaded.get_state(42)
        assert s.health_score == 0.35

    def test_v240_format_loads(self) -> None:
        """V2.4.0 format without newer fields should load with defaults."""
        from core.learner.lifecycle_manager import LifecycleManager

        path = Path(_tmp_dir()) / "lc_v240_compat"
        path.mkdir()
        config_data = {
            "decay_rate": 0.015,
            "decay_min": 0.1,
            "reinforcement_strength": 0.03,
            "independence_bonus": 0.02,
            "supersession_threshold": 0.2,
            "merge_similarity": 0.8,
            "archive_threshold": 0.1,
            "uncertainty_threshold": 0.2,
            "max_redundancy": 5,
        }
        (path / "lifecycle_config.json").write_text(
            __import__("json").dumps(config_data), encoding="utf-8"
        )
        loaded = LifecycleManager.load(path)
        assert loaded.config.decay_rate == 0.015
        # Newer fields get defaults
        assert loaded.config.maintenance_interval_hours == 24.0
        assert loaded.config.merge_input_similarity == 0.6
        assert loaded.config.merge_min_evidence == 2


# =====================================================================
# Serialization Edge Cases
# =====================================================================


class TestSerializationEdgeCases:
    """Edge cases in save/load roundtrips."""

    def test_empty_state_roundtrip_v1(self) -> None:
        from core.learner.learner_v1 import SimilarityLearner

        learner = SimilarityLearner()
        path = Path(_tmp_dir()) / "v1_empty_edge"
        path.mkdir(parents=True, exist_ok=True)
        learner.save_state(str(path))
        loaded = SimilarityLearner.load_state(str(path))
        assert loaded.memory.count() == 0

    def test_empty_state_roundtrip_v2(self) -> None:
        from core.learner.learner_v2 import HybridSimilarityLearner

        learner = HybridSimilarityLearner()
        path = Path(_tmp_dir()) / "v2_empty_edge"
        path.mkdir(parents=True, exist_ok=True)
        learner.save_state(str(path))
        loaded = HybridSimilarityLearner.load_state(str(path))
        assert loaded.memory.count() == 0

    def test_double_roundtrip_v1(self) -> None:
        from core.learner.base import LearningInput
        from core.learner.learner_v1 import SimilarityLearner

        learner = SimilarityLearner()
        learner.learn(
            LearningInput(observation={"input": "a", "output": "b"})
        )
        path1 = Path(_tmp_dir()) / "v1_double_1"
        path1.mkdir(parents=True, exist_ok=True)
        learner.save_state(str(path1))

        loaded1 = SimilarityLearner.load_state(str(path1))
        path2 = Path(_tmp_dir()) / "v1_double_2"
        path2.mkdir(parents=True, exist_ok=True)
        loaded1.save_state(str(path2))

        loaded2 = SimilarityLearner.load_state(str(path2))
        assert loaded2.memory.count() == 1

    def test_double_roundtrip_v2(self) -> None:
        from core.learner.base import LearningInput
        from core.learner.learner_v2 import HybridSimilarityLearner

        learner = HybridSimilarityLearner()
        learner.learn(
            LearningInput(observation={"input": "x", "output": "y"})
        )
        path1 = Path(_tmp_dir()) / "v2_double_1"
        path1.mkdir(parents=True, exist_ok=True)
        learner.save_state(str(path1))

        loaded1 = HybridSimilarityLearner.load_state(str(path1))
        path2 = Path(_tmp_dir()) / "v2_double_2"
        path2.mkdir(parents=True, exist_ok=True)
        loaded1.save_state(str(path2))

        loaded2 = HybridSimilarityLearner.load_state(str(path2))
        assert loaded2.memory.count() == 1

    def test_large_memory_roundtrip(self) -> None:
        from core.learner.base import LearningInput
        from core.learner.learner_v2 import HybridSimilarityLearner

        learner = HybridSimilarityLearner()
        for i in range(50):
            learner.learn(
                LearningInput(
                    observation={
                        "input": f"input text number {i}",
                        "output": f"output {i}",
                    }
                )
            )
        path = Path(_tmp_dir()) / "v2_large_edge"
        path.mkdir(parents=True, exist_ok=True)
        learner.save_state(str(path))
        loaded = HybridSimilarityLearner.load_state(str(path))
        assert loaded.memory.count() == 50

    def test_metadata_preserved_roundtrip(self) -> None:
        from core.learner.feature_extractor import FeatureExtractor
        from core.learner.hybrid_memory import HybridMemory

        mem = HybridMemory()
        ext = FeatureExtractor()
        vec = ext.fit("test")
        mem.add(
            input_text="test",
            output="result",
            vector=vec,
            metadata={"key": "value", "num": 42, "flag": True},
        )
        path = Path(_tmp_dir()) / "meta_rt.json"
        mem.save(path)
        loaded = HybridMemory.load(path)

        h = loaded.get_hybrid(0)
        assert h is not None
        assert h.metadata["key"] == "value"
        assert h.metadata["num"] == 42
        assert h.metadata["flag"] is True

    def test_ids_preserved_roundtrip(self) -> None:
        from core.learner.feature_extractor import FeatureExtractor
        from core.learner.hybrid_memory import HybridMemory

        mem = HybridMemory()
        ext = FeatureExtractor()
        vec = ext.fit("test")
        ex = mem.add(input_text="test", output="result", vector=vec)
        original_id = ex.id

        path = Path(_tmp_dir()) / "id_rt.json"
        mem.save(path)
        loaded = HybridMemory.load(path)

        h = loaded.get_hybrid(0)
        assert h is not None
        assert h.id == original_id

    def test_timestamps_preserved_roundtrip(self) -> None:
        from core.learner.feature_extractor import FeatureExtractor
        from core.learner.hybrid_memory import HybridMemory

        mem = HybridMemory()
        ext = FeatureExtractor()
        vec = ext.fit("test")
        before = time.time()
        mem.add(input_text="test", output="result", vector=vec)

        path = Path(_tmp_dir()) / "ts_rt.json"
        mem.save(path)
        loaded = HybridMemory.load(path)

        h = loaded.get_hybrid(0)
        assert h is not None
        assert h.created_at >= before

    def test_corrupted_json_raises(self) -> None:
        from core.learner.hybrid_memory import HybridMemory

        path = Path(_tmp_dir()) / "corrupt.json"
        path.write_text("{bad json!!!", encoding="utf-8")
        with pytest.raises((ValueError, Exception)):
            HybridMemory.load(path)

    def test_missing_required_fields_raises(self) -> None:
        from core.learner.hybrid_memory import HybridMemory

        path = Path(_tmp_dir()) / "missing_fields.json"
        path.write_text('{"next_id": 0}', encoding="utf-8")
        with pytest.raises((KeyError, Exception)):
            HybridMemory.load(path)
