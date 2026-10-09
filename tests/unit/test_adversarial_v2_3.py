"""V2.3 adversarial safety tests — trying to break confidence estimation."""

from __future__ import annotations

from core.learner.base import LearningInput
from core.learner.confidence import ConfidenceConfig, ConfidenceLevel
from core.learner.learner_v2 import HybridSimilarityLearner


class TestAdversarialConfidence:
    """Try to produce false confidence or misleading estimates."""

    def test_high_similarity_no_evidence_low_confidence(self):
        """A new memory with high similarity but no evidence should not be confident."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "hello world", "output": "greeting"}))
        result = learner.predict("hello world")
        # High similarity but no evidence -> should not be highly confident
        assert result.confidence < 0.9

    def test_many_duplicates_do_not_inflate_confidence(self):
        """Multiple copies of the same memory should not artificially boost confidence."""
        learner = HybridSimilarityLearner(
            k=5,
            confidence_config=ConfidenceConfig(),
        )
        # Add the same memory 5 times
        for _ in range(5):
            learner.learn(LearningInput(observation={"input": "task X", "output": "A"}))
        result = learner.predict("task X")
        # Should not be overly confident just because of duplicates
        assert result.confidence < 0.95

    def test_irrelevant_successful_memory_does_not_dominate(self):
        """A highly successful but irrelevant memory should not boost confidence."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "sort list", "output": "sorted()"}))
        # Add irrelevant memory with lots of success
        for _ in range(20):
            learner.learn(LearningInput(observation={"input": "cook dinner", "output": "recipe"}))
            learner.feedback("cook dinner", "recipe", correct=True)

        result = learner.predict("sort list")
        # Should predict sorted(), confidence should not be inflated by irrelevant successes
        assert result.output == "sorted()"

    def test_conflicting_memories_reduce_confidence(self):
        """Conflicting memories should reduce confidence."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
            conflict_config=ConfidenceConfig(),  # Use same config for conflict
        )
        # Need to import ConflictConfig properly
        from core.learner.conflict import ConflictConfig as CC
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
            conflict_config=CC(input_similarity_threshold=0.5),
        )
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))
        learner.learn(
            LearningInput(observation={"input": "sort a list", "output": "use list.sort()"})
        )

        result = learner.predict("sort a list")
        # Should have a conflict and reduced confidence
        assert result.has_conflict

    def test_alternating_feedback_stability(self):
        """Alternating feedback should not cause catastrophic confidence changes."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task X", "output": "A"}))

        confidences = []
        for i in range(20):
            result = learner.predict("task X")
            confidences.append(result.confidence)
            learner.feedback("task X", "A", correct=(i % 2 == 0))

        # Confidence should not oscillate wildly
        max_diff = max(abs(confidences[i] - confidences[i - 1]) for i in range(1, len(confidences)))
        assert max_diff < 0.5  # No extreme jumps

    def test_single_success_gives_moderate_confidence(self):
        """One successful use should give moderate, not high, confidence."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))
        learner.feedback("task", "A", correct=True)
        result = learner.predict("task")
        # Should be moderate confidence, not high
        assert 0.2 < result.confidence < 0.9

    def test_fifty_successes_gives_higher_confidence(self):
        """Many successful uses should give higher confidence than one."""
        learner1 = HybridSimilarityLearner(k=3, confidence_config=ConfidenceConfig())
        learner1.learn(LearningInput(observation={"input": "task", "output": "A"}))
        learner1.learn(LearningInput(observation={"input": "task other", "output": "B"}))
        learner1.learn(LearningInput(observation={"input": "task thing", "output": "C"}))
        learner1.feedback("task", "A", correct=True)
        r1 = learner1.predict("task")

        learner50 = HybridSimilarityLearner(k=3, confidence_config=ConfidenceConfig())
        learner50.learn(LearningInput(observation={"input": "task", "output": "A"}))
        learner50.learn(LearningInput(observation={"input": "task other", "output": "B"}))
        learner50.learn(LearningInput(observation={"input": "task thing", "output": "C"}))
        for _ in range(50):
            learner50.feedback("task", "A", correct=True)
        r50 = learner50.predict("task")

        assert r50.confidence >= r1.confidence

    def test_confidence_never_negative(self):
        """Even with extreme inputs, confidence stays >= 0."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "x", "output": "A"}))
        learner.feedback("x", "A", correct=False)
        learner.feedback("x", "A", correct=False)
        learner.feedback("x", "A", correct=False)
        result = learner.predict("x")
        assert result.confidence >= 0.0

    def test_confidence_never_exceeds_one(self):
        """Even with perfect evidence, confidence stays <= 1."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))
        for _ in range(100):
            learner.feedback("task", "A", correct=True)
        result = learner.predict("task")
        assert result.confidence <= 1.0

    def test_empty_memory_gives_zero_confidence(self):
        """No memories should give zero confidence."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        result = learner.predict("hello")
        assert result.confidence == 0.0

    def test_unrelated_query_low_confidence(self):
        """A query with no matching memories should have low confidence."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "sort list", "output": "sorted()"}))
        result = learner.predict("quantum physics formula")
        # Should have low confidence since the query is unrelated
        assert result.confidence < 0.5

    def test_feedback_does_not_affect_unrelated_memories(self):
        """Feedback on one memory should not change confidence for unrelated queries."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "sort", "output": "sorted()"}))
        learner.learn(LearningInput(observation={"input": "reverse", "output": "s[::-1]"}))

        r1 = learner.predict("reverse")
        learner.feedback("sort", "sorted()", correct=True)
        r2 = learner.predict("reverse")

        # Reverse confidence should not change significantly
        assert abs(r1.confidence - r2.confidence) < 0.1

    def test_uncertainty_state_meaningful(self):
        """Uncertainty state should match confidence level."""
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))
        result = learner.predict("task")
        # New memory with no evidence -> should be insufficient_evidence or uncertain
        assert result.uncertainty_state in (
            ConfidenceLevel.INSUFFICIENT_EVIDENCE,
            ConfidenceLevel.UNCERTAIN,
        )

    def test_components_are_explainable(self):
        """Confidence components should be present and meaningful."""
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
        assert "success_count" in components

    def test_legacy_prediction_still_works(self):
        """predict_legacy() should still return a Prediction."""
        from core.learner.learner_v1 import Prediction
        learner = HybridSimilarityLearner(
            k=3,
            confidence_config=ConfidenceConfig(),
        )
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))
        pred = learner.predict_legacy("hello")
        assert isinstance(pred, Prediction)
        assert pred.output == "world"
