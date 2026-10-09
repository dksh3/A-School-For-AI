"""Unit tests for V2.3 confidence estimation."""

from __future__ import annotations

from core.learner.calibration.estimator import estimate_confidence_v232
from core.learner.confidence import (
    ConfidenceConfig,
    ConfidenceLevel,
    bayesian_evidence_strength,
    classify_uncertainty_state,
    compute_agreement,
    compute_conflict_penalty,
    detect_conflict_count,
    estimate_confidence,
)

# ---------------------------------------------------------------------------
# Bayesian evidence strength
# ---------------------------------------------------------------------------


class TestBayesianEvidenceStrength:
    def test_no_evidence_returns_prior(self):
        result = bayesian_evidence_strength(0.8, 0, 0, prior_strength=4.0)
        assert result == 0.8

    def test_all_success_converges_to_one(self):
        result = bayesian_evidence_strength(0.5, 100, 0, prior_strength=4.0)
        assert result > 0.95

    def test_all_failure_converges_to_zero(self):
        result = bayesian_evidence_strength(0.5, 0, 100, prior_strength=4.0)
        assert result < 0.05

    def test_mixed_evidence_blends(self):
        result = bayesian_evidence_strength(0.8, 5, 5, prior_strength=4.0)
        # 50% success rate, blended with prior 0.8
        assert 0.4 < result < 0.8

    def test_high_prior_with_little_evidence(self):
        result = bayesian_evidence_strength(0.9, 1, 0, prior_strength=4.0)
        # 1 success, prior 0.9, should be close to prior
        assert result > 0.85

    def test_low_prior_with_strong_evidence(self):
        result = bayesian_evidence_strength(0.2, 50, 0, prior_strength=4.0)
        # 50 successes, should converge toward 1.0 despite low prior
        assert result > 0.8

    def test_prior_strength_affects_convergence(self):
        # With a non-0.5 prior, higher prior_strength keeps result closer to prior
        low_prior = bayesian_evidence_strength(0.8, 2, 2, prior_strength=2.0)
        high_prior = bayesian_evidence_strength(0.8, 2, 2, prior_strength=10.0)
        # Higher prior strength = more weight on prior (0.8)
        assert high_prior > low_prior

    def test_result_bounded(self):
        for s in range(0, 11):
            for f in range(0, 11):
                result = bayesian_evidence_strength(0.5, s, f)
                assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------


class TestAgreement:
    def test_full_agreement(self):
        result = compute_agreement(10.0, 10.0, 5, 5)
        assert result == 1.0

    def test_no_agreement(self):
        result = compute_agreement(0.0, 10.0, 0, 5)
        assert result == 0.0

    def test_half_agreement_weight(self):
        result = compute_agreement(5.0, 10.0, 5, 5)
        assert abs(result - 0.75) < 0.01  # 0.5 * 0.5 + 0.5 * 1.0

    def test_half_agreement_count(self):
        result = compute_agreement(10.0, 10.0, 2, 4)
        assert abs(result - 0.75) < 0.01  # 0.5 * 1.0 + 0.5 * 0.5

    def test_zero_total_weight(self):
        result = compute_agreement(0.0, 0.0, 0, 0)
        assert result == 0.0

    def test_zero_total_count(self):
        result = compute_agreement(5.0, 10.0, 3, 0)
        assert result == 0.0


# ---------------------------------------------------------------------------
# Conflict penalty
# ---------------------------------------------------------------------------


class TestConflictPenalty:
    def test_no_runner_up(self):
        result = compute_conflict_penalty(10.0, 0.0)
        assert result == 0.0

    def test_strong_runner_up(self):
        result = compute_conflict_penalty(10.0, 9.0, max_penalty=0.3)
        assert abs(result - 0.27) < 0.01

    def test_equal_weights(self):
        result = compute_conflict_penalty(10.0, 10.0, max_penalty=0.3)
        assert result == 0.3

    def test_max_penalty_cap(self):
        result = compute_conflict_penalty(1.0, 100.0, max_penalty=0.3)
        assert result == 0.3

    def test_zero_winner(self):
        result = compute_conflict_penalty(0.0, 5.0, max_penalty=0.3)
        assert result == 0.3


# ---------------------------------------------------------------------------
# Conflict count
# ---------------------------------------------------------------------------


class TestConflictCount:
    def test_single_output(self):
        assert detect_conflict_count(["A", "A", "A"]) == 1

    def test_two_outputs(self):
        assert detect_conflict_count(["A", "B"]) == 2

    def test_identical_outputs(self):
        assert detect_conflict_count(["sorted()", "sorted()"]) == 1

    def test_empty(self):
        assert detect_conflict_count([]) == 0

    def test_three_outputs(self):
        assert detect_conflict_count(["A", "B", "C"]) == 3

    def test_with_similarities_filters_irrelevant(self):
        # Only "A" has meaningful similarity, "B" is irrelevant
        assert detect_conflict_count(
            ["A", "B"], similarities=[0.8, 0.05]
        ) == 1

    def test_with_similarities_counts_relevant_conflicts(self):
        # Both have meaningful similarity but different outputs
        assert detect_conflict_count(
            ["A", "B"], similarities=[0.8, 0.7]
        ) == 2


# ---------------------------------------------------------------------------
# Uncertainty state
# ---------------------------------------------------------------------------


class TestUncertaintyState:
    def test_confident(self):
        state = classify_uncertainty_state(
            confidence=0.8,
            evidence_strength=0.7,
            conflict_count=1,
            supporting_count=5,
            similarity=0.8,
            total_uses=10,
        )
        assert state == ConfidenceLevel.CONFIDENT

    def test_insufficient_evidence_low_confidence(self):
        state = classify_uncertainty_state(
            confidence=0.2,
            evidence_strength=0.2,
            conflict_count=1,
            supporting_count=1,
            similarity=0.3,
            total_uses=1,
        )
        assert state == ConfidenceLevel.INSUFFICIENT_EVIDENCE

    def test_conflicted(self):
        state = classify_uncertainty_state(
            confidence=0.5,
            evidence_strength=0.5,
            conflict_count=2,
            supporting_count=3,
            similarity=0.7,
            total_uses=10,
        )
        assert state == ConfidenceLevel.CONFLICTED

    def test_uncertain(self):
        state = classify_uncertainty_state(
            confidence=0.5,
            evidence_strength=0.5,
            conflict_count=1,
            supporting_count=2,
            similarity=0.5,
            total_uses=5,
        )
        assert state == ConfidenceLevel.UNCERTAIN


# ---------------------------------------------------------------------------
# Full confidence estimation
# ---------------------------------------------------------------------------


class TestEstimateConfidence:
    def test_high_similarity_strong_evidence(self):
        result = estimate_confidence(
            similarity=0.9,
            success_count=50,
            failure_count=0,
            supporting_weight=10.0,
            total_weight=10.0,
            supporting_count=5,
            total_count=5,
            outputs=["A"],
        )
        assert result.confidence > 0.7
        assert result.uncertainty_state == ConfidenceLevel.CONFIDENT

    def test_low_similarity_weak_evidence(self):
        result = estimate_confidence(
            similarity=0.2,
            success_count=0,
            failure_count=0,
            supporting_weight=2.0,
            total_weight=5.0,
            supporting_count=1,
            total_count=3,
            outputs=["A", "B"],
        )
        assert result.confidence < 0.4

    def test_conflict_reduces_confidence(self):
        no_conflict = estimate_confidence(
            similarity=0.8,
            success_count=10,
            failure_count=0,
            supporting_weight=10.0,
            total_weight=10.0,
            supporting_count=3,
            total_count=3,
            outputs=["A", "A", "A"],
        )
        with_conflict = estimate_confidence(
            similarity=0.8,
            success_count=10,
            failure_count=0,
            supporting_weight=5.0,
            total_weight=10.0,
            supporting_count=2,
            total_count=4,
            outputs=["A", "A", "B", "B"],
        )
        assert with_conflict.confidence < no_conflict.confidence

    def test_novelty_penalty(self):
        result = estimate_confidence(
            similarity=0.1,
            success_count=10,
            failure_count=0,
            supporting_weight=10.0,
            total_weight=10.0,
            supporting_count=5,
            total_count=5,
            outputs=["A"],
        )
        assert result.novelty_penalty > 0

    def test_agreement_bonus(self):
        high_agreement = estimate_confidence(
            similarity=0.7,
            success_count=5,
            failure_count=0,
            supporting_weight=10.0,
            total_weight=10.0,
            supporting_count=5,
            total_count=5,
            outputs=["A"],
        )
        low_agreement = estimate_confidence(
            similarity=0.7,
            success_count=5,
            failure_count=0,
            supporting_weight=5.0,
            total_weight=10.0,
            supporting_count=2,
            total_count=5,
            outputs=["A", "B"],
        )
        assert high_agreement.confidence > low_agreement.confidence

    def test_result_bounded(self):
        result = estimate_confidence(
            similarity=0.95,
            success_count=100,
            failure_count=0,
            supporting_weight=20.0,
            total_weight=20.0,
            supporting_count=5,
            total_count=5,
            outputs=["A"],
        )
        assert 0.0 <= result.confidence <= 1.0

    def test_components_present(self):
        result = estimate_confidence(
            similarity=0.8,
            success_count=10,
            failure_count=2,
            supporting_weight=8.0,
            total_weight=10.0,
            supporting_count=4,
            total_count=5,
            outputs=["A", "B"],
        )
        assert "similarity" in result.components
        assert "evidence_strength" in result.components
        assert "agreement" in result.components
        assert "conflict_penalty" in result.components
        assert "success_count" in result.components

    def test_zero_similarity_gives_zero_confidence(self):
        result = estimate_confidence_v232(
            similarity=0.0,
            success_count=100,
            failure_count=0,
            supporting_weight=10.0,
            total_weight=10.0,
            supporting_count=5,
            total_count=5,
            outputs=["A"],
            output_similarities=[0.0] * 5,
        )
        assert result.confidence == 0.0

    def test_custom_config(self):
        config = ConfidenceConfig(prior_strength=10.0, agreement_weight=0.3)
        result = estimate_confidence(
            similarity=0.7,
            success_count=5,
            failure_count=5,
            supporting_weight=8.0,
            total_weight=10.0,
            supporting_count=4,
            total_count=5,
            outputs=["A"],
            config=config,
        )
        assert 0.0 <= result.confidence <= 1.0
        assert result.components["similarity"] == 0.7

    def test_evidence_factor_blends_similarity_and_evidence(self):
        result = estimate_confidence(
            similarity=0.8,
            success_count=20,
            failure_count=0,
            supporting_weight=10.0,
            total_weight=10.0,
            supporting_count=5,
            total_count=5,
            outputs=["A"],
        )
        # evidence_factor should be between similarity and evidence_strength
        assert result.evidence_factor >= result.similarity * 0.3


# ---------------------------------------------------------------------------
# Confidence config
# ---------------------------------------------------------------------------


class TestConfidenceConfig:
    def test_default_values(self):
        config = ConfidenceConfig()
        assert config.prior_strength == 2.0
        assert config.agreement_weight == 0.20
        assert config.max_conflict_penalty == 0.5
        assert config.min_evidence_samples == 3
        assert config.novelty_penalty_threshold == 0.3
        assert config.novelty_penalty_strength == 0.15
        assert config.use_v232 is True
        assert config.failure_dominance_penalty == 0.30

    def test_custom_values(self):
        config = ConfidenceConfig(
            prior_strength=8.0,
            agreement_weight=0.2,
            max_conflict_penalty=0.5,
        )
        assert config.prior_strength == 8.0
        assert config.agreement_weight == 0.2
        assert config.max_conflict_penalty == 0.5


# ---------------------------------------------------------------------------
# Probabilistic semantics
# ---------------------------------------------------------------------------


class TestConfidenceBand:
    def test_high_band(self):
        from core.learner.confidence import ConfidenceBand
        assert ConfidenceBand.from_confidence(0.9) == ConfidenceBand.HIGH
        assert ConfidenceBand.from_confidence(0.8) == ConfidenceBand.HIGH

    def test_moderate_band(self):
        from core.learner.confidence import ConfidenceBand
        assert ConfidenceBand.from_confidence(0.7) == ConfidenceBand.MODERATE
        assert ConfidenceBand.from_confidence(0.6) == ConfidenceBand.MODERATE

    def test_low_band(self):
        from core.learner.confidence import ConfidenceBand
        assert ConfidenceBand.from_confidence(0.5) == ConfidenceBand.LOW
        assert ConfidenceBand.from_confidence(0.4) == ConfidenceBand.LOW

    def test_weak_band(self):
        from core.learner.confidence import ConfidenceBand
        assert ConfidenceBand.from_confidence(0.3) == ConfidenceBand.WEAK
        assert ConfidenceBand.from_confidence(0.2) == ConfidenceBand.WEAK

    def test_minimal_band(self):
        from core.learner.confidence import ConfidenceBand
        assert ConfidenceBand.from_confidence(0.1) == ConfidenceBand.MINIMAL
        assert ConfidenceBand.from_confidence(0.0) == ConfidenceBand.MINIMAL

    def test_boundary_values(self):
        from core.learner.confidence import ConfidenceBand
        assert ConfidenceBand.from_confidence(1.0) == ConfidenceBand.HIGH
        assert ConfidenceBand.from_confidence(0.0) == ConfidenceBand.MINIMAL

    def test_band_range(self):
        from core.learner.confidence import ConfidenceBand
        lo, hi = ConfidenceBand.band_range(ConfidenceBand.MODERATE)
        assert lo == 0.6
        assert hi == 0.8


class TestConfidenceToProbability:
    def test_identity_mapping(self):
        from core.learner.confidence import confidence_to_probability
        assert confidence_to_probability(0.5) == 0.5
        assert confidence_to_probability(0.0) == 0.0
        assert confidence_to_probability(1.0) == 1.0

    def test_clamping(self):
        from core.learner.confidence import confidence_to_probability
        assert confidence_to_probability(-0.1) == 0.0
        assert confidence_to_probability(1.1) == 1.0


class TestProbabilisticResult:
    def test_result_has_probability_and_band(self):
        result = estimate_confidence(
            similarity=0.8,
            success_count=5,
            failure_count=1,
            supporting_weight=0.7,
            total_weight=1.0,
            supporting_count=4,
            total_count=5,
            outputs=["a", "a", "a", "a", "b"],
        )
        assert hasattr(result, "probability")
        assert hasattr(result, "band")
        assert 0.0 <= result.probability <= 1.0
        assert result.band in ("high", "moderate", "low", "weak", "minimal")
        assert result.probability == result.confidence

    def test_v232_result_has_probability_and_band(self):
        result = estimate_confidence_v232(
            similarity=0.8,
            success_count=5,
            failure_count=1,
            supporting_weight=0.7,
            total_weight=1.0,
            supporting_count=4,
            total_count=5,
            outputs=["a", "a", "a", "a", "b"],
        )
        assert hasattr(result, "probability")
        assert hasattr(result, "band")
        assert 0.0 <= result.probability <= 1.0
        assert result.band in ("high", "moderate", "low", "weak", "minimal")
