"""Quantitative risk tests (Mission 19B Part 5 + Part 10).

ALL DATA IN THIS FILE IS SYNTHETIC and invented for tests. No real-world
probabilities or statistics are represented.
"""

from __future__ import annotations

from decimal import Decimal

from core.forge.risk import (
    ProbabilityClass,
    RiskEntry,
    expected_loss,
    mitigation_effect,
    ordinal_priority,
    scenario_expected_value,
)


def test_valid_expected_loss() -> None:
    res = expected_loss(
        "0.25",
        "200",
        probability_class=ProbabilityClass.OBSERVED_FREQUENCY,
        loss_unit="USD",
        probability_method="1 of 4 past events",
        probability_source="synthetic log",
    )
    assert res.ok
    assert res.value == Decimal("50")  # 0.25 × 200; Decimal equality ignores trailing zeros
    assert "P(event)" in res.formula
    assert res.inputs["probability"] == "0.25"


def test_missing_probability_refused() -> None:
    res = expected_loss(
        None, "200", probability_class=ProbabilityClass.EXPERT_JUDGMENT, loss_unit="USD"
    )
    assert not res.ok
    assert res.value is None


def test_missing_impact_refused() -> None:
    res = expected_loss(
        "0.5", None, probability_class=ProbabilityClass.EXPERT_JUDGMENT, loss_unit="USD"
    )
    assert not res.ok


def test_unknown_class_refused_not_guessed() -> None:
    res = expected_loss("0.5", "100", probability_class=ProbabilityClass.UNKNOWN, loss_unit="USD")
    assert not res.ok
    assert "classify" in res.error


def test_probability_out_of_range_refused() -> None:
    res = expected_loss(
        "1.5", "100", probability_class=ProbabilityClass.EXPERT_JUDGMENT, loss_unit="USD"
    )
    assert not res.ok
    assert "[0, 1]" in res.error


def test_non_statistical_class_carries_limitation() -> None:
    res = expected_loss(
        "0.5",
        "100",
        probability_class=ProbabilityClass.SCENARIO_ASSUMPTION,
        loss_unit="days",
    )
    assert res.ok
    assert any("not a statistically calibrated" in lim for lim in res.limitations)
    assert res.observed == "scenario_assumption"


def test_loss_unit_required_for_meaning() -> None:
    res = expected_loss(
        "0.5", "100", probability_class=ProbabilityClass.EXPERT_JUDGMENT, loss_unit=""
    )
    assert not res.ok
    assert "unit" in res.error


def test_scenario_expected_value_valid() -> None:
    res = scenario_expected_value([("0.2", "100"), ("0.5", "50"), ("0.3", "0")], unit="USD")
    assert res.ok
    assert res.value == Decimal("45")


def test_inconsistent_probabilities_refused() -> None:
    res = scenario_expected_value([("0.2", "100"), ("0.2", "50")])
    assert not res.ok
    assert "sum to" in res.error
    assert res.value is None


def test_empty_scenario_space_undefined() -> None:
    res = scenario_expected_value([])
    assert not res.ok


def test_ordinal_priority_is_not_quantitative() -> None:
    out = ordinal_priority("high", "medium")
    assert out["priority"] in ("low", "medium", "high")
    assert "NOT a probability" in out["limitation"]
    assert "risk percentage" in out["limitation"]
    bad = ordinal_priority("5", "4")  # numeric ordinal labels are refused
    assert bad["priority"] == "unknown"
    assert "error" in bad


def test_dependent_risks_not_summed() -> None:
    # The API offers no "sum of expected losses" for dependent risks — the only
    # aggregate available is a validated scenario space. This test documents the
    # refusal: calling expected_loss twice and adding is NOT provided anywhere.
    from core.forge import risk as risk_mod

    assert not hasattr(risk_mod, "sum_expected_losses")


def test_unknown_mitigation_effect_stays_unknown() -> None:
    out = mitigation_effect(None, None, "100", "20", loss_unit="USD")
    assert out["effect"] == "unknown"
    assert out["evidence_needed"]
    assert out["absolute_reduction"] is None


def test_mitigation_effect_before_after() -> None:
    out = mitigation_effect("0.4", "0.1", "1000", "50", loss_unit="USD")
    assert out["effect"] == "estimated"
    assert Decimal(out["absolute_reduction"]) == Decimal("0.3")
    assert Decimal(out["relative_reduction_percent"]) == Decimal("75.00")
    assert Decimal(out["delta_expected_loss"]) == Decimal("300")
    assert Decimal(out["residual_expected_loss"]) == Decimal("100")
    assert any("comparable estimates" in a for a in out["assumptions"])


def test_mitigation_relative_reduction_zero_baseline() -> None:
    out = mitigation_effect("0", "0", "100", loss_unit="USD")
    assert out["relative_reduction_percent"] is None
    assert "undefined" in out["error"]


def test_risk_entry_round_trip_keeps_class_and_residual() -> None:
    e = RiskEntry(
        risk_id="R1",
        description="rain on event day",
        probability=Decimal("0.3"),
        probability_class=ProbabilityClass.EXPERT_JUDGMENT,
        probability_method="coordinator judgment",
        severity=Decimal("400"),
        severity_unit="USD",
        residual_probability=Decimal("0.1"),
        review_trigger="forecast at week 6",
    )
    d = e.to_dict()
    assert d["probability_class"] == "expert_judgment"
    assert d["probability"] == "0.3"
    assert d["residual_probability"] == "0.1"
    assert d["review_trigger"]


def test_range_preferred_over_point_when_data_supports() -> None:
    e = RiskEntry(
        risk_id="R2",
        probability_range=(Decimal("0.1"), Decimal("0.3")),
        probability_class=ProbabilityClass.STATISTICALLY_ESTIMATED,
        sample_size=12,
    )
    d = e.to_dict()
    assert d["probability_range"] == ["0.1", "0.3"]
    assert d["probability"] is None  # range retained; no invented point estimate
