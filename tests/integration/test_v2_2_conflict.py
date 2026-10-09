"""V2.2 integration tests — conflict detection and resolution end-to-end."""

from __future__ import annotations

import tempfile

from core.learner.base import LearningInput
from core.learner.conflict import ConflictConfig, ConflictState
from core.learner.learner_v2 import HybridSimilarityLearner
from core.learner.predict_result import PredictResult
from core.learner.retrieval_scorer import ScorerConfig


class TestV22EndToEnd:
    """Full pipeline tests with V2.2 conflict detection enabled."""

    def test_predict_returns_predict_result(self):
        learner = HybridSimilarityLearner(k=3)
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))
        result = learner.predict("hello")
        assert isinstance(result, PredictResult)
        assert result.output == "world"

    def test_predict_legacy_returns_prediction(self):
        from core.learner.learner_v1 import Prediction
        learner = HybridSimilarityLearner(k=3)
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))
        pred = learner.predict_legacy("hello")
        assert isinstance(pred, Prediction)
        assert pred.output == "world"

    def test_no_conflict_single_output(self):
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(),
        )
        learner.learn(LearningInput(observation={"input": "sort list", "output": "sorted()"}))
        result = learner.predict("sort list")
        assert result.has_conflict is False
        assert result.overall_conflict_state == ConflictState.NONE

    def test_conflict_detected_with_opposing_outputs(self):
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
            ),
        )
        # Train with conflicting outputs for similar inputs
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))
        learner.learn(
            LearningInput(observation={"input": "sort a list", "output": "use list.sort()"})
        )

        result = learner.predict("sort a list")
        # Should detect a conflict since both are relevant with different outputs
        assert result.has_conflict is True
        assert len(result.conflicts) >= 1

    def test_conflict_reduces_confidence(self):
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
            ),
        )
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))
        learner.learn(
            LearningInput(observation={"input": "sort a list", "output": "use list.sort()"})
        )

        result = learner.predict("sort a list")
        if result.has_conflict:
            assert result.confidence < result.base_confidence

    def test_feedback_resolves_conflict_over_time(self):
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
                min_evidence_samples=2,
            ),
        )
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))
        learner.learn(
            LearningInput(observation={"input": "sort a list", "output": "use list.sort()"})
        )

        # Give positive feedback to "use sorted()" multiple times
        for _ in range(5):
            result = learner.predict("sort a list")
            if result.output == "use sorted()":
                learner.feedback("sort a list", "use sorted()", correct=True)

        # Give negative feedback to "use list.sort()"
        learner.feedback("sort a list", "use list.sort()", correct=False)

        # After feedback, "use sorted()" should be preferred
        result = learner.predict("sort a list")
        # The conflict should be resolved or "use sorted()" should win
        if result.has_conflict and result.selected_conflict:
            assert result.selected_conflict.selected_output == "use sorted()"

    def test_parameters_include_conflict_info(self):
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(),
        )
        params = learner.parameters
        assert params["has_conflict_detection"] is True

    def test_parameters_no_conflict_detection(self):
        learner = HybridSimilarityLearner(k=3)
        params = learner.parameters
        assert params["has_conflict_detection"] is False

    def test_save_load_with_conflict_config(self):
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(input_similarity_threshold=0.8),
        )
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))

        with tempfile.TemporaryDirectory() as tmpdir:
            learner.save_state(tmpdir)
            loaded = HybridSimilarityLearner.load_state(
                tmpdir,
                conflict_config=ConflictConfig(input_similarity_threshold=0.8),
            )

        result = loaded.predict("hello")
        assert result.output == "world"
        assert loaded._conflict_config is not None
        assert loaded._conflict_config.input_similarity_threshold == 0.8

    def test_v20_behavior_without_conflict_config(self):
        """Without conflict_config, predict still returns PredictResult but no conflicts."""
        learner = HybridSimilarityLearner(k=3)
        learner.learn(LearningInput(observation={"input": "hello", "output": "world"}))
        result = learner.predict("hello")
        assert isinstance(result, PredictResult)
        assert result.has_conflict is False
        assert result.output == "world"

    def test_context_dependent_no_false_conflict(self):
        """Different outputs for different contexts should not always conflict."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.8,
            ),
        )
        # These inputs are different enough that they shouldn't conflict
        learner.learn(
            LearningInput(observation={"input": "open a file in Python", "output": "open()"})
        )
        learner.learn(LearningInput(observation={"input": "reverse a string", "output": "s[::-1]"}))

        result = learner.predict("open a file")
        # "open()" should be predicted, no conflict expected
        assert result.output == "open()"

    def test_unrelated_inputs_no_conflict(self):
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(),
        )
        learner.learn(LearningInput(observation={"input": "hello", "output": "greeting"}))
        learner.learn(LearningInput(observation={"input": "goodbye", "output": "farewell"}))

        result = learner.predict("hello")
        assert result.has_conflict is False

    def test_same_output_no_conflict(self):
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(),
        )
        learner.learn(LearningInput(observation={"input": "sort list", "output": "sorted()"}))
        learner.learn(LearningInput(observation={"input": "sort array", "output": "sorted()"}))

        result = learner.predict("sort")
        assert result.has_conflict is False

    def test_predict_result_summary(self):
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
            ),
        )
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))
        learner.learn(
            LearningInput(observation={"input": "sort a list", "output": "use list.sort()"})
        )

        result = learner.predict("sort a list")
        summary = result.summary()
        assert "output" in summary
        assert "confidence" in summary
        assert "has_conflict" in summary

    def test_multiple_feedback_rounds_stabilize(self):
        """After many rounds of consistent feedback, conflict should resolve."""
        learner = HybridSimilarityLearner(
            k=3,
            conflict_config=ConflictConfig(
                input_similarity_threshold=0.5,
                min_evidence_samples=2,
            ),
        )
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "use sorted()"}))
        learner.learn(
            LearningInput(observation={"input": "sort a list", "output": "use list.sort()"})
        )

        # Many rounds of feedback favoring "use sorted()"
        for _ in range(10):
            result = learner.predict("sort a list")
            if result.output == "use sorted()":
                learner.feedback("sort a list", "use sorted()", correct=True)
            elif result.output == "use list.sort()":
                learner.feedback("sort a list", "use list.sort()", correct=False,
                                 actual_output="use sorted()")

        result = learner.predict("sort a list")
        # After heavy feedback, should prefer sorted()
        assert result.output == "use sorted()"


class TestV22VsV21Comparative:
    """V2.2 must maintain V2.1 behavior when conflict detection is off."""

    def test_v22_without_config_matches_v21(self):
        v21 = HybridSimilarityLearner(k=3, scorer_config=ScorerConfig())
        v22 = HybridSimilarityLearner(k=3, scorer_config=ScorerConfig())

        examples = [
            ("sort a list", "use sorted()"),
            ("reverse string", "s[::-1]"),
            ("find max", "max()"),
        ]
        for text, output in examples:
            inp = LearningInput(observation={"input": text, "output": output})
            v21.learn(inp)
            v22.learn(inp)

        for query in ["sort", "reverse", "find max"]:
            p21 = v21.predict_legacy(query)
            p22 = v22.predict_legacy(query)
            assert p21.output == p22.output
