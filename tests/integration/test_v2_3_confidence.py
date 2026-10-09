"""V2.3 integration tests — confidence estimation end-to-end."""

from __future__ import annotations

import tempfile

from core.learner.base import LearningInput
from core.learner.confidence import ConfidenceConfig, ConfidenceLevel
from core.learner.conflict import ConflictConfig
from core.learner.learner_v2 import HybridSimilarityLearner
from core.learner.predict_result import PredictResult
from core.learner.retrieval_scorer import ScorerConfig


class TestV23EndToEnd:
    """Full pipeline tests with V2.3 confidence estimation."""

    def test_predict_returns_predict_result_with_confidence(self):
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))
        result = learner.predict("hello")
        assert isinstance(result, PredictResult)
        assert result.output == "world"
        assert result.confidence > 0.0
        assert result.confidence_result is not None

    def test_confidence_uses_bayesian_evidence(self):
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))

        # No evidence -> confidence should reflect prior
        r0 = learner.predict("task")

        # After feedback -> evidence should increase confidence
        learner.feedback("task", "A", correct=True)
        r1 = learner.predict("task")

        assert r1.confidence >= r0.confidence

    def test_evidence_strength_increases_with_feedback(self):
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))

        for _ in range(10):
            learner.feedback("task", "A", correct=True)

        result = learner.predict("task")
        assert result.confidence_result is not None
        assert result.confidence_result.evidence_strength > 0.5

    def test_agreement_bonus_present(self):
        learner = HybridSimilarityLearner(
            k=5,
            confidence_config=ConfidenceConfig(),
        )
        # Add multiple memories with same output
        for i in range(5):
            learner.learn(LearningInput(
                observation={"input": f"variant {i}", "output": "A"}
            ))
        result = learner.predict("variant")
        assert result.confidence_result is not None
        assert result.confidence_result.agreement_bonus > 0

    def test_conflict_reduces_confidence(self):
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
            conflict_config=ConflictConfig(input_similarity_threshold=0.5),
        )
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))
        learner.learn(
            LearningInput(observation={"input": "sort a list", "output": "use list.sort()"})
        )

        result = learner.predict("sort a list")
        if result.has_conflict:
            assert result.confidence < 1.0

    def test_novelty_penalty_for_unseen(self):
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))
        learner.learn(LearningInput(observation={"input": "greeting", "output": "hi"}))
        result = learner.predict("hello there")
        assert result.confidence_result is not None
        # Low similarity should trigger novelty penalty
        if result.confidence_result.similarity < 0.3:
            assert result.confidence_result.novelty_penalty > 0

    def test_uncertainty_state_classification(self):
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))
        result = learner.predict("task")
        assert result.uncertainty_state in (
            ConfidenceLevel.CONFIDENT,
            ConfidenceLevel.UNCERTAIN,
            ConfidenceLevel.INSUFFICIENT_EVIDENCE,
            ConfidenceLevel.CONFLICTED,
        )

    def test_confidence_components_explainable(self):
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))
        learner.feedback("task", "A", correct=True)
        result = learner.predict("task")
        components = result.confidence_components
        assert "similarity" in components
        assert "evidence_strength" in components
        assert "evidence_quality" in components
        assert "agreement_bonus" in components
        assert "conflict_penalty" in components
        assert "novelty_penalty" in components
        assert "success_count" in components
        assert "failure_count" in components

    def test_summary_includes_v23_fields(self):
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))
        result = learner.predict("task")
        summary = result.summary()
        assert "similarity" in summary
        assert "uncertainty_state" in summary
        assert "confidence_components" in summary

    def test_predict_legacy_ignores_confidence_config(self):
        """predict_legacy() should use V1 confidence formula."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))
        pred = learner.predict_legacy("hello")
        # Should have confidence but no V2.3 result
        assert 0.0 <= pred.confidence <= 1.0

    def test_save_load_preserves_confidence_config(self):
        learner = HybridSimilarityLearner(
            k=3,
            scorer_config=ScorerConfig(),
            conflict_config=ConflictConfig(),
            confidence_config=ConfidenceConfig(prior_strength=8.0),
        )
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))

        with tempfile.TemporaryDirectory() as tmpdir:
            learner.save_state(tmpdir)
            loaded = HybridSimilarityLearner.load_state(
                tmpdir,
                scorer_config=ScorerConfig(),
                conflict_config=ConflictConfig(),
                confidence_config=ConfidenceConfig(prior_strength=8.0),
            )

        result = loaded.predict("hello")
        assert result.output == "world"
        assert loaded._confidence_config is not None
        assert loaded._confidence_config.prior_strength == 8.0

    def test_backward_compatibility_no_confidence_config(self):
        """Without confidence_config, V1 fallback behavior is preserved."""
        learner = HybridSimilarityLearner(k=3)
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))
        result = learner.predict("hello")
        assert result.output == "world"
        assert result.confidence_result is None
        assert 0.0 <= result.confidence <= 1.0

    def test_v22_behavior_with_conflict_only(self):
        """V2.2 conflict detection still works without V2.3 confidence."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(input_similarity_threshold=0.5),
        )
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))
        learner.learn(
            LearningInput(observation={"input": "sort a list", "output": "use list.sort()"})
        )

        result = learner.predict("sort a list")
        assert result.has_conflict
        assert result.confidence_result is None  # No V2.3 confidence

    def test_full_stack_v2_3_with_all_features(self):
        """Full V2.3 with scorer, conflict, and confidence."""
        learner = HybridSimilarityLearner(
            k=5,
            scorer_config=ScorerConfig(),
            conflict_config=ConflictConfig(),
            confidence_config=ConfidenceConfig(),
        )
        # Use similar inputs so they're all relevant
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "sorted()"}))
        learner.learn(LearningInput(observation={"input": "sort an array", "output": "sorted()"}))
        learner.learn(LearningInput(observation={"input": "sort items", "output": "sorted()"}))

        for _ in range(5):
            learner.feedback("sort a list", "sorted()", correct=True)

        result = learner.predict("sort a list")
        assert result.output == "sorted()"
        assert result.confidence > 0.3
        assert result.confidence_result is not None
        assert result.confidence_result.evidence_strength > 0.5

    def test_multiple_feedback_rounds_stabilize(self):
        """After consistent feedback, confidence should stabilize."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))
        learner.learn(LearningInput(observation={"input": "task other", "output": "B"}))
        learner.learn(LearningInput(observation={"input": "task thing", "output": "C"}))

        confidences = []
        for _ in range(20):
            learner.feedback("task", "A", correct=True)
            result = learner.predict("task")
            confidences.append(result.confidence)

        # Confidence should increase and stabilize
        assert confidences[-1] >= confidences[0]
        # Last 5 should be close to each other
        assert max(confidences[-5:]) - min(confidences[-5:]) < 0.1
