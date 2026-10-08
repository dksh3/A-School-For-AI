"""1A-2Z: deterministic candidate detection and value scoring.

Cheap-first gate: trivial/no-signal experiences must never consume a
model call. Thresholds come from candidate.py (env-configurable).
"""

from __future__ import annotations

import pytest

from core.routing.v26.experience import Experience, ExperienceOutcome
from core.routing.v26.identity import AgentIdentity
from core.skillgen.candidate import (
    MIN_CANDIDATE_SCORE,
    detect,
    detect_trivial,
    extract_signals,
    score_candidate,
)

STRONG_OBS = (
    "The build failed every time with module resolution errors after a config change"
)
STRONG_ACTION = (
    "Diagnosed the root cause and fixed the module configuration so builds pass reliably"
)
WEAK_OBS = "Attempted an alternate approach for unrelated reasons in the environment today"
WEAK_ACTION = "Tried it and it did not apply to this particular setup"


def _exp(
    observation: str,
    action: str,
    outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
    confidence: float = 0.5,
    feedback: str = "",
) -> Experience:
    return Experience.create(
        agent=AgentIdentity(agent_id="a1"),
        observation=observation,
        action=action,
        outcome=outcome,
        confidence=confidence,
        feedback=feedback,
    )


class TestTrivialRejection:
    def test_opened_a_file_is_never_a_candidate(self) -> None:
        exp = _exp("Opened a file", "", outcome=ExperienceOutcome.SUCCESS)
        assert detect(exp) is None

    def test_detect_trivial_patterns(self) -> None:
        assert detect_trivial("Opened a file") is True
        assert detect_trivial("Read the README") is True
        assert detect_trivial("Listed the files") is True
        assert detect_trivial(STRONG_OBS + " " + STRONG_ACTION) is False

    def test_short_text_without_solution_hints_is_trivial(self) -> None:
        assert detect_trivial("clicked around the panel a bit") is True

    def test_neutral_outcome_not_promotable(self) -> None:
        exp = _exp(STRONG_OBS, STRONG_ACTION, outcome=ExperienceOutcome.NEUTRAL)
        assert detect(exp) is None

    def test_low_confidence_not_promotable(self) -> None:
        exp = _exp(STRONG_OBS, STRONG_ACTION, confidence=0.1)
        assert detect(exp) is None

    def test_empty_content_not_promotable(self) -> None:
        exp = _exp("", "", outcome=ExperienceOutcome.SUCCESS)
        assert detect(exp) is None


class TestScoring:
    def test_strong_experience_clears_threshold(self) -> None:
        exp = _exp(
            STRONG_OBS, STRONG_ACTION, feedback="works, exactly what I needed, great"
        )
        candidate = detect(exp)
        assert candidate is not None
        assert candidate.score >= MIN_CANDIDATE_SCORE
        assert 0.0 <= candidate.score <= 1.0
        assert candidate.signals["success"] is True
        assert candidate.signals["solution"] is True
        assert candidate.signals["recurrence"] is True
        assert candidate.signals["positive_feedback"] is True
        assert candidate.reasons

    def test_weak_experience_below_threshold_but_candidate(self) -> None:
        exp = _exp(WEAK_OBS, WEAK_ACTION, outcome=ExperienceOutcome.FAILURE)
        candidate = detect(exp)
        assert candidate is not None
        assert candidate.score < MIN_CANDIDATE_SCORE

    def test_signals_report_shape(self) -> None:
        exp = _exp(STRONG_OBS, STRONG_ACTION)
        signals = extract_signals(exp)
        expected = {
            "success", "non_trivial", "solution", "recurrence",
            "positive_feedback", "efficiency", "error_avoided",
            "previously_unresolved", "reused", "user_positive",
        }
        assert set(signals) == expected

    def test_score_within_bounds_for_randomish_input(self) -> None:
        exp = _exp(STRONG_OBS, STRONG_ACTION, confidence=0.9)
        signals = extract_signals(exp)
        score, factors, _reasons = score_candidate(exp, signals, novelty=1.0)
        assert 0.0 <= score <= 1.0
        assert set(factors) == {
            "usefulness", "repeatability", "novelty", "impact", "reliability"
        }
        assert all(0.0 <= v <= 1.0 for v in factors.values())

    def test_novelty_reflects_existing_similarity(self) -> None:
        exp = _exp(STRONG_OBS, STRONG_ACTION)
        candidate = detect(exp, existing_similarity=0.9,
                           existing_merge_hint="some-skill")
        assert candidate is not None
        assert candidate.novelty == pytest.approx(0.1)
        assert candidate.merge_hint == "some-skill"

    def test_reuse_metadata_raises_repeatability(self) -> None:
        exp = Experience.create(
            agent=AgentIdentity(agent_id="a1"),
            observation=STRONG_OBS,
            action=STRONG_ACTION,
            outcome=ExperienceOutcome.SUCCESS,
            metadata={"reuse_count": 3},
        )
        signals = extract_signals(exp)
        assert signals["reused"] is True
        _score, factors, _reasons = score_candidate(exp, signals)
        assert factors["repeatability"] >= 0.8
