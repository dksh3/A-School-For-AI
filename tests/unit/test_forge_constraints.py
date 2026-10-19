"""Constraint & evidence-acceptance tests (Mission 19B Part 7 + Part 10).

ALL DATA IN THIS FILE IS SYNTHETIC and invented for tests. The "human" and
"persona" evidence in these tests is synthetic — it is never real validation.
"""

from __future__ import annotations

from decimal import Decimal

from core.forge.constraints import (
    ConstraintRecord,
    ConstraintResult,
    EvidenceKind,
    check_phase_count,
    parse_budget_ceiling,
    phase_requirement_count,
    validate_constraints,
)


def _rec(id: str, *, kind: str = "hard", result: ConstraintResult, **kw) -> ConstraintRecord:
    return ConstraintRecord(
        id=id,
        requirement=kw.pop("requirement", f"requirement {id}"),
        kind=kind,
        result=result,
        **kw,
    )


def test_simulated_evidence_not_promoted_to_pass() -> None:
    rec = _rec(
        "c1",
        result=ConstraintResult.SATISFIED,
        evidence_kind=EvidenceKind.SIMULATED,
        explanation="3 synthetic personas said they can follow",
    )
    verdict = validate_constraints([rec])
    assert not verdict.accepted
    assert any("simulated" in b for b in verdict.blocking)


def test_simulated_evidence_accepted_only_with_recorded_user_acceptance() -> None:
    rec = _rec(
        "c1",
        result=ConstraintResult.SATISFIED,
        evidence_kind=EvidenceKind.SIMULATED,
        explanation="user accepted the proxy before the verdict (recorded)",
    )
    verdict = validate_constraints([rec])
    assert verdict.accepted


def test_genuine_human_evidence_passes() -> None:
    rec = _rec(
        "c1",
        result=ConstraintResult.SATISFIED,
        evidence_kind=EvidenceKind.HUMAN_VERIFIED,
        evidence_source="signed review 2026-05-01",
    )
    assert validate_constraints([rec]).accepted


def test_missing_evidence_is_unresolved_not_pass() -> None:
    rec = _rec("c1", result=ConstraintResult.UNRESOLVED, evidence_kind=EvidenceKind.MISSING)
    verdict = validate_constraints([rec])
    assert not verdict.accepted
    assert any("unresolved" in b for b in verdict.blocking)


def test_violated_hard_constraint_blocks_even_if_others_perfect() -> None:
    records = [
        _rec("c1", result=ConstraintResult.SATISFIED, evidence_kind=EvidenceKind.MACHINE_CHECKED),
        _rec("c2", result=ConstraintResult.VIOLATED, evidence_kind=EvidenceKind.MACHINE_CHECKED),
        _rec("c3", result=ConstraintResult.SATISFIED, evidence_kind=EvidenceKind.MACHINE_CHECKED),
    ]
    verdict = validate_constraints(records)
    assert not verdict.accepted
    assert verdict.reason.startswith("NO-GO")
    assert any("c2" in b for b in verdict.blocking)


def test_no_score_offsets_a_hard_violation() -> None:
    # 9 satisfied preferences cannot buy off 1 violated hard constraint.
    records = [
        _rec(f"p{i}", kind="preference", result=ConstraintResult.SATISFIED) for i in range(9)
    ]
    records.append(_rec("h1", result=ConstraintResult.VIOLATED))
    verdict = validate_constraints(records)
    assert not verdict.accepted
    assert "conjunction" in verdict.score_note


def test_conditional_hard_constraint_yields_conditions() -> None:
    rec = _rec(
        "c1",
        result=ConstraintResult.CONDITIONAL,
        explanation="space confirmation due Friday",
    )
    verdict = validate_constraints([rec])
    assert verdict.accepted
    assert verdict.reason.startswith("GO-WITH-CONDITIONS")
    assert any("conditional" in c for c in verdict.conditions)


def test_model_output_contradicting_deterministic_check_fails() -> None:
    # The record is what the deterministic check said; prose claiming otherwise
    # cannot flip it. Simulate: actual 4 phases vs expected 3 → violated.
    rec = check_phase_count("EXACTLY 3 PHASES", 4)
    assert rec.result is ConstraintResult.VIOLATED
    verdict = validate_constraints([rec])
    assert not verdict.accepted


def test_phase_count_pass_and_na() -> None:
    ok = check_phase_count("EXACTLY 3 PHASES", 3)
    assert ok.result is ConstraintResult.SATISFIED
    assert ok.evidence_kind is EvidenceKind.MACHINE_CHECKED
    na = check_phase_count("ship it when ready", 2)
    assert na.result is ConstraintResult.NOT_APPLICABLE


def test_phase_count_accepts_word_numbers() -> None:
    """Regression (Mission 20 case e): 'EXACTLY three phases' used to return
    n_a — a hard phase-count constraint written in words was never enforced,
    so a 4-phase plan against 'exactly three phases' evaded the verdict."""
    ok = check_phase_count("EXACTLY three phases in the plan", 3)
    assert ok.result is ConstraintResult.SATISFIED
    assert ok.evidence_kind is EvidenceKind.MACHINE_CHECKED
    bad = check_phase_count("EXACTLY three phases in the plan", 4)
    assert bad.result is ConstraintResult.VIOLATED
    assert "4 phases" in bad.explanation and "says 3" in bad.explanation
    two = check_phase_count("exactly two phases", 2)
    assert two.result is ConstraintResult.SATISFIED
    mixed_case = check_phase_count("Exactly Four Phases", 4)
    assert mixed_case.result is ConstraintResult.SATISFIED
    digits_still_work = check_phase_count("EXACTLY 3 phases in the plan", 4)
    assert digits_still_work.result is ConstraintResult.VIOLATED


def test_phase_requirement_count_never_guesses() -> None:
    assert phase_requirement_count("three phases") == 3
    assert phase_requirement_count("EXACTLY 3 PHASES") == 3
    assert phase_requirement_count("eleven phases, no more") == 11
    assert phase_requirement_count("ship it when ready") is None
    assert phase_requirement_count("no phase words here") is None


def test_budget_ceiling_parsed_not_invented() -> None:
    amount, cur = parse_budget_ceiling("TOTAL MONEY <= $200")
    assert amount == Decimal("200")
    assert cur == "USD"
    amount2, cur2 = parse_budget_ceiling("at most 176.50 EUR")
    assert amount2 == Decimal("176.50")
    assert cur2 == "EUR"
    none_amount, none_cur = parse_budget_ceiling("keep it cheap")
    assert none_amount is None and none_cur == ""


def test_unresolved_mandatory_criterion_blocks_go() -> None:
    records = [
        _rec("c1", result=ConstraintResult.SATISFIED, evidence_kind=EvidenceKind.MACHINE_CHECKED),
        _rec("c2", result=ConstraintResult.UNRESOLVED, evidence_kind=EvidenceKind.INFERRED),
    ]
    verdict = validate_constraints(records)
    assert not verdict.accepted
    assert verdict.reason.startswith("NO-GO")


def test_preference_missed_never_blocks() -> None:
    records = [_rec("p1", kind="preference", result=ConstraintResult.VIOLATED)]
    verdict = validate_constraints(records)
    assert verdict.accepted
    assert any("preference missed" in c for c in verdict.conditions)


def test_verdict_dict_shape() -> None:
    d = validate_constraints([_rec("c1", result=ConstraintResult.SATISFIED)]).to_dict()
    assert set(d) == {"accepted", "reason", "blocking", "conditions", "score_note"}


def test_string_typed_records_fail_closed_at_the_boundary() -> None:
    """JSON boundaries deliver plain strings — they must not silently pass.

    Regression: pre-fix, `result="satisfied"` as a plain str skipped every
    branch of validate_constraints (identity checks against the enum) and the
    verdict came back GO. Unrecognized values must land on UNRESOLVED.
    """
    stringly = ConstraintRecord(
        id="C2",
        requirement="TOTAL MONEY <= $200",
        kind="hard",
        result="satisfied",  # plain str, as a JSON boundary produces
        evidence_kind="simulated",  # plain str
        explanation="proxy check",
    )
    assert stringly.result == ConstraintResult.SATISFIED
    assert stringly.evidence_kind == EvidenceKind.SIMULATED
    verdict = validate_constraints([stringly])
    assert not verdict.accepted
    assert any("simulated" in b for b in verdict.blocking)

    unknown = ConstraintRecord(
        id="C3",
        requirement="something",
        kind="hard",
        result="banana",
        evidence_kind="telepathy",
    )
    assert unknown.result == ConstraintResult.UNRESOLVED
    assert unknown.evidence_kind == EvidenceKind.MISSING
    verdict2 = validate_constraints([unknown])
    assert not verdict2.accepted
    assert any("unresolved" in b for b in verdict2.blocking)
