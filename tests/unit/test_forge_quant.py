"""Deterministic calculation tests (Mission 19B Part 4 + Part 10).

ALL DATA IN THIS FILE IS SYNTHETIC and invented for tests. No real-world
statistics, prices, or human approvals are represented.
"""

from __future__ import annotations

from decimal import Decimal

from core.forge.quant import (
    check_percent_consistency,
    money_remaining,
    money_total,
    over_allocation,
    percentage,
    percentage_point_change,
    relative_change,
    tax_amount,
    utilization,
    verify_budget,
)


def test_money_total_exact_decimal_no_float_drift() -> None:
    # 0.1 + 0.2 style drift: floats would give 0.30000000000000004
    res = money_total([("a", 0.1), ("b", 0.2)], currency="USD")
    assert res.ok
    assert res.value == Decimal("0.3")
    assert res.unit == "USD"
    assert res.formula


def test_money_total_with_tax_fees_transport_discounts() -> None:
    res = money_total(
        [("signs", "80.00"), ("snacks", "24.00")],
        currency="USD",
        tax=[("sales tax", "8.00")],
        fees=[("permit fee", "20.00")],
        transport=[("fuel", "0.00")],
        discounts=[("coupon", "4.00")],
    )
    assert res.ok
    assert res.value == Decimal("128.00")
    assert res.intermediates["subtotal"] == "104.00"
    assert "tax" in res.intermediates


def test_money_total_currency_mismatch_refused() -> None:
    res = money_total([("a", 10, "USD"), ("b", 10, "EUR")], currency="USD")
    assert not res.ok
    assert "currency mismatch" in res.error
    assert res.value is None


def test_money_total_requires_currency() -> None:
    res = money_total([("a", 1)], currency="")
    assert not res.ok
    assert "currency" in res.error


def test_money_total_empty_lines_undefined() -> None:
    res = money_total([], currency="USD")
    assert not res.ok
    assert "zero lines" in res.error


def test_money_total_bad_line_refused_not_fabricated() -> None:
    res = money_total([("a", "about twenty")], currency="USD")
    assert not res.ok
    assert res.value is None


def test_tax_amount_half_up_rounding() -> None:
    res = tax_amount("125.55", "7.5")
    assert res.ok
    assert res.value == Decimal("9.42")  # 9.41625 half-up to 2dp
    assert res.rounding == "half-up"


def test_verify_budget_detects_wrong_declared_total() -> None:
    lines = [("a", "100.00"), ("b", "76.00")]
    bad = verify_budget(lines, "180.00", currency="USD")
    assert not bad.ok
    assert "176.00" in bad.error
    good = verify_budget(lines, "176.00", currency="USD")
    assert good.ok
    assert good.value == Decimal("176.00")


def test_money_remaining_may_go_negative_honestly() -> None:
    res = money_remaining("200", "240", currency="USD")
    assert res.ok
    assert res.value == Decimal("-40")


def test_percentage_carries_denominator_and_provenance() -> None:
    res = percentage(80, 100, scope="books swapped", period="week 6", source="synthetic")
    assert res.ok
    assert res.value == Decimal("80.00")
    assert res.inputs["numerator"] == "80"
    assert res.inputs["denominator"] == "100"
    assert res.scope == "books swapped"
    assert res.period == "week 6"
    assert res.source == "synthetic"
    assert res.formula == "numerator / denominator × 100"


def test_percentage_zero_denominator_undefined() -> None:
    res = percentage(5, 0)
    assert not res.ok
    assert "undefined" in res.error
    assert res.value is None


def test_percentage_missing_denominator_refused() -> None:
    res = percentage(5, None)
    assert not res.ok
    assert res.value is None


def test_percentage_small_denominator_flagged_not_reliable() -> None:
    res = percentage(2, 3)
    assert res.ok
    assert any("small denominator" in lim for lim in res.limitations)


def test_percentage_point_versus_relative_change() -> None:
    pp = percentage_point_change(40, 50)
    assert pp.ok
    assert pp.value == Decimal("10")
    assert pp.unit == "pp"
    rel = relative_change(40, 50)
    assert rel.ok
    assert rel.value == Decimal("25.00")  # +25% relative
    assert rel.unit == "%"


def test_relative_change_zero_baseline_undefined() -> None:
    res = relative_change(0, 5)
    assert not res.ok
    assert "undefined" in res.error


def test_check_percent_consistency_catches_false_claim() -> None:
    good = check_percent_consistency("80", 80, 100)
    assert good.ok
    bad = check_percent_consistency("95", 80, 100)
    assert not bad.ok
    assert "95" in bad.error


def test_check_percent_consistency_accepts_percent_suffix() -> None:
    """Regression: a claim written '27%' used to be rejected as 'not a valid
    number' instead of being compared. A suffixed claim must be checked."""
    suffixed = check_percent_consistency("27%", 80, 300)
    assert not suffixed.ok  # 27% != 26.67% — the comparison must run
    assert "does not match" in suffixed.error
    exact = check_percent_consistency("80%", 80, 100)
    assert exact.ok


def test_utilization_and_over_allocation() -> None:
    util = utilization(5, 8)
    assert util.ok
    assert util.value == Decimal("62.50")
    zero_cap = utilization(5, 0)
    assert not zero_cap.ok
    over = over_allocation([("lane-a", 5), ("lane-b", 6)], 10)
    assert not over.ok
    assert "over-allocated" in over.error
    ok = over_allocation([("lane-a", 5), ("lane-b", 5)], 10)
    assert ok.ok


def test_calcresult_never_carries_value_on_failure() -> None:
    for bad in (
        percentage(1, 0),
        money_total([], currency="USD"),
        relative_change(0, 1),
        verify_budget([("a", 1)], 2, currency="USD"),
    ):
        assert not bad.ok
        assert bad.value is None
        assert bad.error
        d = bad.to_dict()
        assert d["value"] is None and d["error"]
