"""Adaptive questioning controller tests — QuestionBudget + QuestioningSession.

ALL FIXTURES AND ANSWERS IN THIS FILE ARE SYNTHETIC. No human input, no
real-world validation is involved or implied.
"""

from __future__ import annotations

import pytest

from core.forge.questions import (
    DEFAULT_QUESTION_BUDGET,
    MAX_QUESTION_BUDGET,
    QuestionBudget,
    QuestioningSession,
)
from core.forge.requirements import Unknown, UnknownState


def _unknown(
    id: str,
    question: str,
    *,
    affects: tuple[str, ...] = ("correctness",),
    critical: bool = False,
    cost: str = "high",
    depends_on: tuple[str, ...] = (),
    variable: str = "",
) -> Unknown:
    return Unknown(
        id=id,
        question=question,
        variable=variable or id,
        why_it_matters="synthetic fixture",
        affects=affects,
        derivable=False,
        derivation_note="",
        retrievable=False,
        authoritative_source="",
        must_ask_user=True,
        if_unknown="record an explicit unknown",
        wrong_assumption_cost=cost,
        range_safe=False,
        range_note="",
        state="UNKNOWN",
        provenance="synthetic fixture",
        depends_on=depends_on,
        critical=critical,
        asked_keys=(),
    )


def _session(unknowns: list[Unknown], **cfg) -> QuestioningSession:
    return QuestioningSession(config=QuestionBudget(**cfg), unknowns=unknowns)


class TestConfiguration:
    def test_valid_custom_budgets_accepted(self) -> None:
        for n in (1, 5, 42, MAX_QUESTION_BUDGET):
            assert QuestionBudget(question_budget=n).question_budget == n

    def test_zero_and_negative_rejected_actionably(self) -> None:
        for bad in (0, -1):
            with pytest.raises(ValueError, match="at least 1"):
                QuestionBudget(question_budget=bad)

    def test_boolean_masquerading_as_integer_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            QuestionBudget(question_budget=True)

    def test_malformed_and_wrong_types_rejected(self) -> None:
        for bad in ("five", 2.5, None, [5]):
            with pytest.raises(ValueError, match="positive integer"):
                QuestionBudget(question_budget=bad)

    def test_over_limit_rejected_never_clamped(self) -> None:
        with pytest.raises(ValueError, match="safety limit"):
            QuestionBudget(question_budget=MAX_QUESTION_BUDGET + 1)

    def test_defaults_are_adaptive_balanced_followups_early_stop(self) -> None:
        cfg = QuestionBudget()
        assert cfg.question_budget == DEFAULT_QUESTION_BUDGET
        assert cfg.strategy == "adaptive"
        assert cfg.depth == "balanced"
        assert cfg.allow_followups is True
        assert cfg.stop_early is True

    def test_unsupported_strategy_and_depth_rejected(self) -> None:
        with pytest.raises(ValueError, match="adaptive"):
            QuestionBudget(strategy="interrogation")
        with pytest.raises(ValueError, match="balanced"):
            QuestionBudget(depth="exhaustive")
        with pytest.raises(ValueError, match="boolean"):
            QuestionBudget(allow_followups="yes")

    def test_from_dict_strict_and_round_trips(self) -> None:
        cfg = QuestionBudget(question_budget=7)
        again = QuestionBudget.from_dict(cfg.to_dict())
        assert again == cfg
        with pytest.raises(ValueError, match="unknown question budget config key"):
            QuestionBudget.from_dict({"question_budget": 5, "banana": 1})
        with pytest.raises(ValueError, match="JSON object"):
            QuestionBudget.from_dict([1, 2])


class TestAdaptiveBehavior:
    def test_new_answer_changes_the_next_question(self) -> None:
        s = _session([_unknown("u-a", "What is A?"), _unknown("u-b", "What is B?")])
        first = s.ask_next()
        assert first is not None
        s.record_answer(first.id, "settled")
        second = s.ask_next()
        assert second is not None
        assert second.id != first.id

    def test_uncertain_answer_raises_followup_from_same_budget(self) -> None:
        s = _session([_unknown("u-a", "What is A?")], question_budget=3)
        p = s.ask_next()
        assert p is not None
        assert s.remaining == 2
        res = s.record_answer(p.id, "not sure")
        assert res["followup"] is not None
        follow = s.ask_next()
        assert follow is not None
        assert follow.kind == "follow-up"
        assert follow.id.startswith("u-a:fu:")
        assert s.remaining == 1  # follow-up consumed from the same budget
        assert s.followups_asked == 1

    def test_contradiction_marks_conflicted_and_raises_followup(self) -> None:
        s = _session(
            [
                _unknown("u-a", "What is A?", variable="x"),
                _unknown("u-b", "What is B?", variable="x"),
            ],
            question_budget=5,
        )
        s.record_answer("u-a", "left")
        res = s.record_answer("u-b", "right")
        states = {u.id: u.state for u in s.unknowns}
        assert states["u-b"] == UnknownState.CONFLICTED
        assert states["u-a"] == UnknownState.CONFLICTED
        assert res["followup"] is not None

    def test_weak_confidence_marks_conflicted(self) -> None:
        s = _session([_unknown("u-a", "What is A?")], question_budget=3)
        res = s.record_answer("u-a", "maybe 42", confidence=0.2)
        assert res["state"] == str(UnknownState.CONFLICTED)
        assert res["followup"] is not None

    def test_answered_questions_never_reprsented_again(self) -> None:
        s = _session(
            [_unknown("u-a", "What is A?"), _unknown("u-b", "What is B?")],
            question_budget=10,
        )
        seen = []
        for _ in range(6):
            p = s.ask_next()
            if p is None:
                break
            seen.append(p.question)
            s.record_answer(p.id, "settled")
        assert len(seen) == len(set(seen)) == 2

    def test_tie_breaking_is_deterministic(self) -> None:
        def build() -> list[Unknown]:
            return [
                _unknown("u-b", "What is B?", affects=("cost",), cost="low"),
                _unknown("u-a", "What is A?", affects=("cost",), cost="low"),
                _unknown("u-c", "What is C?", affects=("cost",), cost="low"),
            ]

        order_a = [p.id for p in _drain(_session(build()))]
        order_b = [p.id for p in _drain(_session(build()))]
        assert order_a == order_b == ["u-a", "u-b", "u-c"]


def _drain(s: QuestioningSession) -> list:
    out = []
    while True:
        p = s.ask_next()
        if p is None:
            return out
        out.append(p)
        s.record_answer(p.id, "settled")


class TestBudgetEnforcement:
    def test_never_presents_more_than_the_maximum(self) -> None:
        s = _session(
            [_unknown(f"u-{i}", f"Question {i}?") for i in range(6)], question_budget=3
        )
        presented = [p for p in _drain(s) if True]
        assert len(presented) == 3
        assert s.stop_reason == "budget-exhausted"

    def test_the_final_allowed_question_can_be_asked(self) -> None:
        s = _session([_unknown("u-a", "A?"), _unknown("u-b", "B?")], question_budget=2)
        assert s.ask_next().remaining_after == 1
        assert s.ask_next().remaining_after == 0
        assert s.presented == 2
        assert s.ask_next() is None

    def test_exhaustion_is_not_success_and_keeps_unresolved(self) -> None:
        s = _session(
            [_unknown(f"u-{i}", f"Question {i}?", critical=True) for i in range(4)],
            question_budget=2,
        )
        _drain(s)
        assert s.stop_reason == "budget-exhausted"
        assert s.outcome() == "budget exhausted (not success)"
        report = s.status_report()
        assert report["unresolved_questions"]
        assert report["complete"] is False


class TestEarlyStopping:
    def test_stops_early_only_when_completion_criteria_hold(self) -> None:
        s = _session([_unknown("u-a", "A?")], question_budget=5)
        s.verification_defined = True
        p = s.ask_next()
        s.record_answer(p.id, "settled")
        assert s.ask_next() is None
        assert s.stop_reason == "early-stopped"
        assert s.outcome() == "succeeded"
        assert s.presented < 5

    def test_empty_queue_with_blocking_unknowns_is_not_success(self) -> None:
        s = _session(
            [
                _unknown("u-permit", "Permit?"),
                _unknown("u-ins", "Insurance?", depends_on=("u-permit",)),
            ],
            question_budget=5,
            allow_followups=False,
        )
        p = s.ask_next()  # u-permit (u-ins is dependency-blocked)
        s.record_answer(p.id, "not sure", confidence=0.1)  # leaves u-permit open
        assert s.ask_next() is None  # u-ins blocked, u-permit already asked
        assert s.stop_reason == "blocked"
        assert s.outcome() == "incomplete (not success)"
        report = s.status_report()
        assert report["complete"] is False
        assert any(b.startswith("u-permit") for b in report["blocking"])

    def test_verification_undefined_never_claims_success(self) -> None:
        s = _session([_unknown("u-a", "A?")], question_budget=5)
        p = s.ask_next()
        s.record_answer(p.id, "settled")
        assert s.ask_next() is None
        assert s.stop_reason == "no-questions-remaining"
        assert s.outcome() == "incomplete (not success)"
        assert "not a success claim" in s.stop_detail

    def test_disabled_early_stopping_still_respects_safety(self) -> None:
        s = _session([_unknown("u-a", "A?")], question_budget=5, stop_early=False)
        s.verification_defined = True
        p = s.ask_next()
        s.record_answer(p.id, "settled")
        # complete criteria hold, but stop_early is off and nothing remains to
        # ask: it must stop honestly, not fabricate questions.
        assert s.ask_next() is None
        assert s.stop_reason in ("complete", "no-questions-remaining")


class TestPersistence:
    def test_round_trip_preserves_budget_state(self) -> None:
        s = _session(
            [_unknown("u-a", "A?"), _unknown("u-b", "B?")], question_budget=3
        )
        p = s.ask_next()
        s.record_answer(p.id, "not sure")
        again = QuestioningSession.from_dict(s.to_dict())
        assert again.config == s.config
        assert again.presented == s.presented == 1
        assert again.asked_keys == s.asked_keys
        assert again.answers == s.answers
        assert again.remaining == 2
        assert {u.id for u in again.unknowns} == {u.id for u in s.unknowns}

    def test_resume_never_resets_the_budget(self) -> None:
        s = _session([_unknown(f"u-{i}", f"Q{i}?") for i in range(4)], question_budget=2)
        s.ask_next()
        again = QuestioningSession.from_dict(s.to_dict())
        assert again.remaining == 1
        again.ask_next()
        assert again.exhausted
        assert again.ask_next() is None
        assert again.stop_reason == "budget-exhausted"

    def test_malformed_state_fails_closed(self) -> None:
        base = _session([_unknown("u-a", "A?")], question_budget=3).to_dict()
        for mutate in (
            lambda d: d.update(version=99),
            lambda d: d.update(presented="three"),
            lambda d: d.update(presented=5),
            lambda d: d.update(presented=-1),
            lambda d: d.update(asked_keys="u-a"),
            lambda d: d.update(answers=[1]),
            lambda d: d.update(unknowns="u-a"),
            lambda d: d.update(config={"question_budget": 0}),
        ):
            data = dict(base)
            mutate(data)
            pattern = "refusing|session|must be|unsupported|question_budget"
            with pytest.raises(ValueError, match=pattern):
                QuestioningSession.from_dict(data)

    def test_from_dict_rejects_non_object(self) -> None:
        with pytest.raises(ValueError, match="JSON object"):
            QuestioningSession.from_dict([1])
