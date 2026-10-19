"""Adaptive requirements-elicitation tests (Mission 19B Part 2 + Part 10).

ALL DATA IN THIS FILE IS SYNTHETIC and invented for tests.
"""

from __future__ import annotations

from core.forge.models import Interview, Question, RequirementAnswer
from core.forge.requirements import (
    Requirement,
    RequirementKind,
    Unknown,
    UnknownState,
    elicitation_status,
    from_interview,
    mark_asked,
    next_batch,
    prioritize,
    requirements_summary,
)


def _u(
    id: str,
    *,
    state: UnknownState = UnknownState.UNKNOWN,
    affects: tuple[str, ...] = ("correctness",),
    critical: bool = False,
    must_ask: bool = True,
    cost: str = "high",
    derivable: bool = False,
    depends_on: tuple[str, ...] = (),
    question: str = "",
) -> Unknown:
    return Unknown(
        id=id,
        question=question or f"Question for {id}?",
        affects=affects,
        critical=critical,
        must_ask_user=must_ask,
        wrong_assumption_cost=cost,
        derivable=derivable,
        depends_on=depends_on,
        state=state,
        if_unknown="plan incomplete",
    )


def test_missing_critical_input_blocks_completion() -> None:
    unknowns = [_u("u1", critical=True)]
    status = elicitation_status(unknowns, verification_defined=True)
    assert not status.complete
    assert any("u1" in b for b in status.blocking)


def test_irrelevant_missing_input_never_asked() -> None:
    unknowns = [
        _u("u-color", state=UnknownState.NOT_APPLICABLE, must_ask=False),
        _u("u-budget", critical=True),
    ]
    batch = next_batch(unknowns)
    ids = [u.id for u in batch]
    assert "u-color" not in ids
    assert "u-budget" in ids


def test_contradictory_requirements_conflicted_blocks() -> None:
    unknowns = [_u("u-date", state=UnknownState.CONFLICTED)]
    status = elicitation_status(unknowns, verification_defined=True)
    assert not status.complete
    assert any("u-date" in c for c in status.unresolved_conflicts)


def test_already_answered_question_never_reasked() -> None:
    unknowns = [_u("u1", state=UnknownState.KNOWN_FROM_USER)]
    assert next_batch(unknowns) == []


def test_derived_value_does_not_trigger_question() -> None:
    unknowns = [_u("u-derived", derivable=True, must_ask=False, cost="low")]
    assert next_batch(unknowns) == []


def test_authorized_assumption_recorded_not_fact() -> None:
    unknowns = [_u("u-a", state=UnknownState.ASSUMED, must_ask=False, cost="low")]
    status = elicitation_status(unknowns, verification_defined=True)
    assert status.complete
    assert any("assumed, not fact" in a for a in status.authorized_assumptions)


def test_unresolved_critical_unknown_blocks_and_summary_says_so() -> None:
    unknowns = [_u("u-crit", critical=True), _u("u-ok", state=UnknownState.KNOWN_FROM_USER)]
    status = elicitation_status(unknowns, verification_defined=True)
    assert not status.complete
    summary = requirements_summary([], unknowns)
    assert "u-crit" in summary


def test_conditional_plan_completes_with_low_cost_unknown() -> None:
    # A remaining unknown that is neither critical, must-ask, nor high-cost
    # does not prevent a defensible (possibly conditional) result.
    unknowns = [_u("u-nice", must_ask=False, cost="low", affects=("feasibility",))]
    status = elicitation_status(unknowns, verification_defined=True)
    assert status.complete


def test_verification_criteria_required_for_completion() -> None:
    unknowns: list[Unknown] = []
    assert not elicitation_status(unknowns, verification_defined=False).complete
    assert elicitation_status(unknowns, verification_defined=True).complete


def test_no_repeated_questions() -> None:
    u = _u("u1", question="What is the budget ceiling?")
    batch = next_batch([u])
    assert len(batch) == 1
    stats = mark_asked([u], ["What is the budget ceiling?"])
    assert stats["marked"] == 1
    assert next_batch([u]) == []  # never asked again
    stats2 = mark_asked([u], ["What is the budget ceiling?", "What is the budget ceiling?"])
    assert stats2["repeats"] == 1


def test_dependency_aware_questioning() -> None:
    early = _u("u-scope", critical=True, affects=("correctness", "cost"))
    late = _u("u-tax-rate", depends_on=("u-scope",), affects=("cost",))
    batch1 = next_batch([early, late])
    assert [u.id for u in batch1] == ["u-scope"]
    early.state = UnknownState.KNOWN_FROM_USER
    batch2 = next_batch([early, late])
    assert [u.id for u in batch2] == ["u-tax-rate"]


def test_prioritize_orders_by_materiality() -> None:
    high = _u("u-high", critical=True, cost="high", affects=("safety",))
    low = _u("u-low", must_ask=False, cost="low", affects=("style",))
    mid = _u("u-mid", affects=("cost", "schedule"))
    ordered = [u.id for u in prioritize([low, mid, high])]
    assert ordered[0] == "u-high"
    assert ordered[-1] == "u-low"


def test_from_interview_maps_unanswered_required_and_open_questions() -> None:
    q_req = Question(id="q1", dimension="constraints", prompt="Hard constraint?", required=True)
    q_opt = Question(id="q2", dimension="style", prompt="Style?", required=False)
    q_ans = Question(id="q3", dimension="scope", prompt="Scope?", required=True)
    weak = RequirementAnswer(question_id="q3", value="maybe", is_custom=False, confidence=0.2)
    iv = Interview(
        title="Synthetic goal",
        questions=[q_req, q_opt, q_ans],
        answers=[weak],
        open_questions=["Who signs off?"],
    )
    unknowns = from_interview(iv)
    ids = {u.id for u in unknowns}
    assert "u:q1" in ids  # unanswered required → must-ask
    assert "u:q2" not in ids  # optional unanswered → no material unknown
    assert "u:q3:weak" in ids  # confidence 0.2 → conflicted
    assert any(u.state is UnknownState.CONFLICTED for u in unknowns)
    assert any("Who signs off?" in u.question for u in unknowns)


def test_requirement_preserves_user_words_and_kind() -> None:
    r = Requirement(
        id="r1",
        kind=RequirementKind.HARD_CONSTRAINT,
        text="TOTAL MONEY <= $200",
        source="user:kickoff",
    )
    d = r.to_dict()
    assert d["text"] == "TOTAL MONEY <= $200"
    assert d["kind"] == "hard_constraint"
    assert d["source"] == "user:kickoff"


def test_string_typed_boundary_fields_normalize_fail_closed() -> None:
    """JSON/CLI boundaries deliver plain strings; .value must never explode.

    Regression: building Unknown(state='UNKNOWN') from a JSON dict made
    elicitation_status crash with ``'str' object has no attribute 'value'``.
    Unknown enum values must land on UNKNOWN (fail closed), not crash and not
    get promoted to a resolved state.
    """
    u = Unknown(id="u1", question="Tax rate?", state="UNKNOWN")
    assert u.state == UnknownState.UNKNOWN
    u2 = Unknown(id="u2", question="Space?", state="banana")
    assert u2.state == UnknownState.UNKNOWN  # unrecognized -> fail closed
    r = Requirement(id="r1", kind="hard_constraint", text="EXACTLY 3 PHASES")
    assert r.kind == RequirementKind.HARD_CONSTRAINT
    r2 = Requirement(id="r2", kind="banana", text="x")
    assert r2.kind == RequirementKind.OBJECTIVE
    # to_dict and status must work on boundary-built records
    status = elicitation_status([u, u2])
    assert not status.complete
    assert r.to_dict()["kind"] == "hard_constraint"
