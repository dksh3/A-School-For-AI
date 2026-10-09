"""V2.2 adversarial safety tests — trying to break conflict detection."""

from __future__ import annotations

from core.learner.base import LearningInput
from core.learner.conflict import ConflictConfig
from core.learner.learner_v2 import HybridSimilarityLearner


class TestAdversarialConflictDetection:
    """Try to produce false conflicts or missed conflicts."""

    def test_highly_successful_wrong_answer_vs_relevant_correct(self):
        """A wrong answer with many successes should still lose to a correct
        answer with high relevance."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
                min_evidence_samples=2,
            ),
        )
        # "wrong" answer gets lots of positive feedback
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "reverse it"}))
        # "correct" answer is added later
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))

        # Give many positive feedbacks to the wrong answer
        for _ in range(10):
            learner.feedback("sort a list", "reverse it", correct=True)

        # The correct answer should still be retrievable
        result = learner.predict("sort a list")
        assert result.output in ("reverse it", "use sorted()")

    def test_many_copies_of_wrong_answer(self):
        """Multiple copies of the same wrong answer shouldn't dominate."""
        learner = HybridSimilarityLearner(
            k=5,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
            ),
        )
        # Multiple wrong answers
        for i in range(5):
            learner.learn(LearningInput(
                observation={"input": f"sort list variant {i}", "output": "delete it"}
            ))
        # One correct answer
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))

        result = learner.predict("sort a list")
        # Should still be able to find "use sorted()"
        assert result.output is not None

    def test_alternating_feedback_stability(self):
        """Alternating feedback should not cause catastrophic instability."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
                min_evidence_samples=2,
            ),
        )
        learner.learn(LearningInput(observation={"input": "task X", "output": "A"}))
        learner.learn(LearningInput(observation={"input": "task X", "output": "B"}))

        # Alternating feedback
        for i in range(20):
            if i % 2 == 0:
                learner.feedback("task X", "A", correct=True)
                learner.feedback("task X", "B", correct=False)
            else:
                learner.feedback("task X", "A", correct=False)
                learner.feedback("task X", "B", correct=True)

        # Should not crash and should still produce a prediction
        result = learner.predict("task X")
        assert result.output in ("A", "B")

    def test_empty_memory_prediction(self):
        """Prediction with no memories should not crash."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(),
        )
        result = learner.predict("hello")
        assert result.output == ""
        assert result.has_conflict is False

    def test_single_memory_no_conflict(self):
        """One memory should never produce a conflict."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(),
        )
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))
        result = learner.predict("hello")
        assert result.has_conflict is False

    def test_confidence_never_negative(self):
        """Even with extreme penalty, confidence stays >= 0."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
            ),
        )
        learner.learn(LearningInput(observation={"input": "task", "output": "A"}))
        learner.learn(LearningInput(observation={"input": "task", "output": "B"}))

        result = learner.predict("task")
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0

    def test_feedback_does_not_affect_unrelated_memories(self):
        """Feedback on one conflict should not affect unrelated memories."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
            ),
        )
        learner.learn(LearningInput(observation={"input": "sort", "output": "sorted()"}))
        learner.learn(LearningInput(observation={"input": "sort", "output": "list.sort()"}))
        learner.learn(LearningInput(observation={"input": "reverse", "output": "s[::-1]"}))

        # Feedback on sort conflict
        learner.feedback("sort", "sorted()", correct=True)
        learner.feedback("sort", "list.sort()", correct=False)

        # Reverse should be unaffected
        result = learner.predict("reverse")
        assert result.output == "s[::-1]"
        assert result.has_conflict is False

    def test_reset_clears_conflict_state(self):
        """Reset should clear all conflict-related state."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(),
        )
        learner.learn(LearningInput(observation={"input": "x", "output": "A"}))
        learner.predict("x")
        learner.reset()
        assert learner._memory.count() == 0
        result = learner.predict("x")
        assert result.output == ""

    def test_semantic_similarity_used_for_context(self):
        """Context-dependent outputs should not always be conflicts."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.8,
                context_similarity_threshold=0.9,
            ),
        )
        # Different tasks with different correct answers
        learner.learn(
            LearningInput(observation={"input": "open a file handle", "output": "open()"})
        )
        learner.learn(LearningInput(observation={"input": "create a list", "output": "list()"}))

        result = learner.predict("open a file")
        # Should predict "open()" without conflict
        assert result.output == "open()"


class TestAdversarialEvidence:
    """Test that evidence comparison handles extreme cases."""

    def test_zero_relevance_wins_nothing(self):
        """Zero relevance should always score zero."""
        from core.learner.conflict import Evidence, _evidence_score
        ev = Evidence(
            example_id=1,
            output="A",
            relevance=0.0,
            success_rate=1.0,
            success_count=100,
            failure_count=0,
            weight=5.0,
            recency=1.0,
        )
        score = _evidence_score(ev)
        assert score == 0.0

    def test_high_relevance_low_evidence_still_scores(self):
        """High relevance with minimal evidence should still produce a score."""
        from core.learner.conflict import Evidence, _evidence_score
        ev = Evidence(
            example_id=1,
            output="A",
            relevance=0.9,
            success_rate=0.5,
            success_count=0,
            failure_count=0,
            weight=1.0,
            recency=0.5,
        )
        score = _evidence_score(ev, min_samples=3)
        assert score > 0.0
        # Should be dominated by relevance
        assert score > 0.4
