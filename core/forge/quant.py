"""Deterministic quantitative calculations — the arithmetic authority.

Mission 19B Part 4 rules, enforced here:

- Money uses :class:`decimal.Decimal`. Binary floats never touch a total.
- Currency is explicit. Incompatible currencies are refused unless a documented
  conversion source and reference date are supplied (not supported here).
- Every percentage carries its denominator, unit, scope, and provenance.
- Every material result carries provenance (inputs, formula, intermediates,
  rounding policy, validation outcome).
- A failed calculation yields an explicit error record. This layer FAILS CLOSED:
  it never returns a fabricated value, zero, or infinity to look complete.

Nothing in this module consults a model. These functions are the deterministic
authority for arithmetic; prose may explain their output but must not override a
failed check with "the answer looks reasonable".
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

__all__ = [
    "CalcResult",
    "RoundingPolicy",
    "check_percent_consistency",
    "money_remaining",
    "money_total",
    "over_allocation",
    "percentage",
    "percentage_point_change",
    "relative_change",
    "tax_amount",
    "utilization",
    "verify_budget",
]

_ROUNDING_MODES = {
    "half-up": ROUND_HALF_UP,
    "half-even": ROUND_HALF_EVEN,
    "down": ROUND_DOWN,
    "up": ROUND_UP,
}


class RoundingPolicy(StrEnum):
    """Declared rounding policy for a calculation."""

    NONE = "none"
    HALF_UP = "half-up"
    HALF_EVEN = "half-even"
    DOWN = "down"
    UP = "up"


@dataclass
class CalcResult:
    """One calculation with full provenance.

    ``ok`` is False exactly when ``error`` explains why no value is valid.
    ``value`` is None whenever ``ok`` is False — a failed calc never carries a
    number that could leak into prose as if it were real.
    """

    ok: bool
    value: Decimal | None
    unit: str = ""
    formula: str = ""
    inputs: dict[str, str] = field(default_factory=dict)
    intermediates: dict[str, str] = field(default_factory=dict)
    rounding: str = "none"
    source: str = ""
    scope: str = ""  # population/scope the value describes
    period: str = ""  # measurement period
    observed: str = "calculated"  # calculated|observed|estimated|modelled|forecast|scenario
    error: str = ""
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "value": str(self.value) if self.value is not None else None,
            "unit": self.unit,
            "formula": self.formula,
            "inputs": dict(self.inputs),
            "intermediates": dict(self.intermediates),
            "rounding": self.rounding,
            "source": self.source,
            "scope": self.scope,
            "period": self.period,
            "observed": self.observed,
            "error": self.error,
            "limitations": list(self.limitations),
        }


def _dec(value: Any, name: str) -> tuple[Decimal | None, str]:
    """Coerce a value to Decimal without binary-float artifacts.

    Floats are routed through ``str()`` so ``0.1`` means the decimal 0.1.
    Returns ``(None, error)`` when the value is not a valid number.
    """
    if value is None:
        return None, f"{name} is missing"
    if isinstance(value, Decimal):
        return value, ""
    if isinstance(value, bool):
        return None, f"{name} is a boolean, not a number"
    if isinstance(value, int):
        return Decimal(value), ""
    if isinstance(value, float):
        try:
            return Decimal(str(value)), ""
        except InvalidOperation:
            return None, f"{name} is not a valid number: {value!r}"
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None, f"{name} is missing"
        try:
            return Decimal(text), ""
        except InvalidOperation:
            return None, f"{name} is not a valid number: {value!r}"
    return None, f"{name} has unsupported type {type(value).__name__}"


def _quantize(value: Decimal, rounding: str, places: int = 2) -> Decimal:
    if rounding in ("none", ""):
        return value
    mode = _ROUNDING_MODES.get(rounding)
    if mode is None:
        return value  # unknown policy: return exact rather than guess
    q = Decimal(1).scaleb(-places)
    return value.quantize(q, rounding=mode)


def _fmt(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def _fail(error: str, **kwargs: Any) -> CalcResult:
    return CalcResult(ok=False, value=None, error=error, **kwargs)


def money_total(
    lines: Sequence[tuple[Any, ...]] | Iterable[tuple[Any, ...]],
    *,
    currency: str,
    tax: Sequence[tuple[str, Any]] | None = None,
    fees: Sequence[tuple[str, Any]] | None = None,
    transport: Sequence[tuple[str, Any]] | None = None,
    discounts: Sequence[tuple[str, Any]] | None = None,
    source: str = "",
    rounding: str = RoundingPolicy.HALF_UP.value,
) -> CalcResult:
    """Sum budget lines into a total: lines + tax + fees + transport − discounts.

    Each line is ``(name, amount)`` or ``(name, amount, line_currency)``.
    A line currency that differs from ``currency`` is a hard error — mixing
    currencies without a documented conversion source is refused, not guessed.
    """
    currency = (currency or "").strip()
    if not currency:
        return _fail("currency is required — a money total without a currency is not a total")
    parsed: list[tuple[str, Decimal]] = []
    inputs: dict[str, str] = {}
    for i, raw in enumerate(lines):
        if not isinstance(raw, tuple) or len(raw) < 2:
            return _fail(f"line {i} is not (name, amount[, currency])")
        name, amount = raw[0], raw[1]
        if len(raw) > 2 and str(raw[2]).strip() and str(raw[2]).strip() != currency:
            return _fail(
                f"currency mismatch on line {name!r}: {raw[2]!r} vs {currency!r} "
                "(no documented conversion source and reference date)"
            )
        val, err = _dec(amount, f"line {name!r}")
        if err:
            return _fail(err)
        assert val is not None
        parsed.append((str(name), val))
        inputs[str(name)] = _fmt(val)
    if not parsed:
        return _fail("no budget lines — a total over zero lines is undefined")

    subtotal = sum((v for _, v in parsed), Decimal(0))
    extras: dict[str, Decimal] = {}
    for group, items, sign in (
        ("tax", tax, Decimal(1)),
        ("fees", fees, Decimal(1)),
        ("transport", transport, Decimal(1)),
        ("discounts", discounts, Decimal(-1)),
    ):
        acc = Decimal(0)
        for item in items or ():
            if not isinstance(item, tuple) or len(item) < 2:
                return _fail(f"{group} entry {item!r} is not (name, amount)")
            val, err = _dec(item[1], f"{group} {item[0]!r}")
            if err:
                return _fail(err)
            assert val is not None
            acc += val * sign
            inputs[f"{group}:{item[0]}"] = _fmt(val)
        extras[group] = acc

    total = subtotal + sum(extras.values(), Decimal(0))
    if rounding != RoundingPolicy.NONE.value:
        total = _quantize(total, rounding)
    return CalcResult(
        ok=True,
        value=total,
        unit=currency,
        formula="sum(lines) + tax + fees + transport − discounts",
        inputs=inputs,
        intermediates={"subtotal": _fmt(subtotal), **{k: _fmt(v) for k, v in extras.items()}},
        rounding=rounding,
        source=source,
    )


def verify_budget(
    lines: Sequence[tuple[Any, ...]] | Iterable[tuple[Any, ...]],
    declared_total: Any,
    *,
    currency: str,
    source: str = "",
) -> CalcResult:
    """Independent reconciliation: sum the lines, compare with the declared total.

    The declared total is a CLAIM, not an input. ``ok`` is True only when the
    recomputed sum equals the claim exactly (after declared rounding).
    """
    declared, err = _dec(declared_total, "declared_total")
    if err:
        return _fail(err)
    summed = money_total(lines, currency=currency, source=source)
    if not summed.ok:
        return summed
    assert summed.value is not None and declared is not None
    delta = summed.value - declared
    if delta != 0:
        return CalcResult(
            ok=False,
            value=None,
            unit=summed.unit,
            formula="sum(lines) == declared_total",
            inputs={**summed.inputs, "declared_total": _fmt(declared)},
            intermediates={
                **summed.intermediates,
                "sum": _fmt(summed.value),
                "declared": _fmt(declared),
                "delta": _fmt(delta),
            },
            source=source,
            error=f"declared total {declared} != recomputed sum {summed.value} (delta {delta})",
        )
    return CalcResult(
        ok=True,
        value=summed.value,
        unit=summed.unit,
        formula="sum(lines) == declared_total",
        inputs={**summed.inputs, "declared_total": _fmt(declared)},
        intermediates={
            **summed.intermediates,
            "sum": _fmt(summed.value),
            "declared": _fmt(declared),
            "delta": "0",
        },
        source=source,
    )


def money_remaining(ceiling: Any, total: Any, *, currency: str, source: str = "") -> CalcResult:
    """Remaining funds under a budget ceiling: ceiling − total (may be negative)."""
    cap, err1 = _dec(ceiling, "ceiling")
    spent, err2 = _dec(total, "total")
    if err1 or err2:
        return _fail(err1 or err2 or "invalid input")
    assert cap is not None and spent is not None
    return CalcResult(
        ok=True,
        value=cap - spent,
        unit=currency,
        formula="ceiling − total",
        inputs={"ceiling": _fmt(cap), "total": _fmt(spent)},
        source=source,
    )


def tax_amount(subtotal: Any, rate_percent: Any, *, source: str = "") -> CalcResult:
    """Tax on a subtotal: subtotal × rate/100, half-up to 2 places."""
    sub, err1 = _dec(subtotal, "subtotal")
    rate, err2 = _dec(rate_percent, "rate_percent")
    if err1 or err2:
        return _fail(err1 or err2 or "invalid input")
    assert sub is not None and rate is not None
    amount = _quantize(sub * rate / Decimal(100), RoundingPolicy.HALF_UP.value)
    return CalcResult(
        ok=True,
        value=amount,
        unit="currency",
        formula="subtotal × rate_percent / 100",
        inputs={"subtotal": _fmt(sub), "rate_percent": _fmt(rate)},
        rounding=RoundingPolicy.HALF_UP.value,
        source=source,
    )


def percentage(
    numerator: Any,
    denominator: Any,
    *,
    unit: str = "%",
    scope: str = "",
    period: str = "",
    source: str = "",
    method: str = "numerator / denominator × 100",
    rounding: str = RoundingPolicy.HALF_UP.value,
    observed: str = "calculated",
) -> CalcResult:
    """A percentage that knows what it is a percentage OF.

    A zero or missing denominator makes the percentage UNDEFINED — this returns
    an error record and never a silent 0% or 100%.
    """
    num, err1 = _dec(numerator, "numerator")
    den, err2 = _dec(denominator, "denominator")
    if err1 or err2:
        return _fail(err1 or err2 or "invalid input")
    assert num is not None and den is not None
    if den == 0:
        return _fail(
            "denominator is zero — the percentage is undefined "
            "(never returned as 0 or infinity)"
        )
    raw = num / den * Decimal(100)
    value = _quantize(raw, rounding, places=2)
    limitations: list[str] = []
    if abs(den) < 10:
        limitations.append(
            f"small denominator ({den}) — the value is not statistically reliable "
            "however many decimals it carries"
        )
    return CalcResult(
        ok=True,
        value=value,
        unit=unit,
        formula="numerator / denominator × 100",
        inputs={"numerator": _fmt(num), "denominator": _fmt(den)},
        intermediates={"raw_percent": str(raw)},
        rounding=rounding,
        source=source,
        scope=scope,
        period=period,
        observed=observed,
        limitations=limitations,
    )


def check_percent_consistency(
    claimed_percent: Any,
    numerator: Any,
    denominator: Any,
    *,
    tolerance: Any = "0.01",
    source: str = "",
) -> CalcResult:
    """Verify a claimed percentage against its numerator and denominator."""
    if isinstance(claimed_percent, str):
        claimed_percent = claimed_percent.strip().rstrip("%").strip()
    claimed, err = _dec(claimed_percent, "claimed_percent")
    if err:
        return _fail(err)
    recomputed = percentage(numerator, denominator, source=source)
    if not recomputed.ok:
        return recomputed
    tol, _ = _dec(tolerance, "tolerance")
    assert claimed is not None and recomputed.value is not None and tol is not None
    delta = abs(claimed - recomputed.value)
    if delta > tol:
        return CalcResult(
            ok=False,
            value=None,
            unit="%",
            formula="claimed_percent == numerator / denominator × 100",
            inputs={
                "claimed_percent": _fmt(claimed),
                **recomputed.inputs,
            },
            intermediates={"recomputed": _fmt(recomputed.value), "delta": _fmt(delta)},
            source=source,
            error=f"claimed {claimed}% does not match recomputed {recomputed.value}%",
        )
    return CalcResult(
        ok=True,
        value=recomputed.value,
        unit="%",
        formula="claimed_percent == numerator / denominator × 100",
        inputs={"claimed_percent": _fmt(claimed), **recomputed.inputs},
        intermediates={"recomputed": _fmt(recomputed.value), "delta": _fmt(delta)},
        source=source,
    )


def percentage_point_change(before: Any, after: Any, *, source: str = "") -> CalcResult:
    """Change in percentage POINTS: after − before (40% → 50% is 10 pp)."""
    b, err1 = _dec(before, "before")
    a, err2 = _dec(after, "after")
    if err1 or err2:
        return _fail(err1 or err2 or "invalid input")
    assert b is not None and a is not None
    return CalcResult(
        ok=True,
        value=a - b,
        unit="pp",
        formula="after − before (percentage points)",
        inputs={"before_percent": _fmt(b), "after_percent": _fmt(a)},
        source=source,
    )


def relative_change(before: Any, after: Any, *, source: str = "") -> CalcResult:
    """Relative change in percent: (after − before) / before × 100.

    A zero baseline makes the relative change UNDEFINED — an error record, not
    a fabricated number. (40% → 50% is a +25% relative change.)
    """
    b, err1 = _dec(before, "before")
    a, err2 = _dec(after, "after")
    if err1 or err2:
        return _fail(err1 or err2 or "invalid input")
    assert b is not None and a is not None
    if b == 0:
        return _fail("baseline is zero — relative change is undefined")
    raw = (a - b) / abs(b) * Decimal(100)
    return CalcResult(
        ok=True,
        value=_quantize(raw, RoundingPolicy.HALF_UP.value),
        unit="%",
        formula="(after − before) / |before| × 100",
        inputs={"before_percent": _fmt(b), "after_percent": _fmt(a)},
        intermediates={"raw": str(raw)},
        rounding=RoundingPolicy.HALF_UP.value,
        source=source,
    )


def utilization(used: Any, capacity: Any, *, source: str = "") -> CalcResult:
    """Resource utilization as a percentage of capacity (zero capacity is undefined)."""
    return percentage(
        used,
        capacity,
        unit="%",
        scope="capacity utilization",
        source=source,
        method="used / capacity × 100",
    )


def over_allocation(
    allocations: Sequence[tuple[str, Any]],
    capacity: Any,
    *,
    source: str = "",
) -> CalcResult:
    """Recompute total allocation and check it does not exceed capacity.

    ``ok`` is False when the sum exceeds capacity — over-allocation is a real
    violation, not a rounding nuisance.
    """
    cap, err = _dec(capacity, "capacity")
    if err:
        return _fail(err)
    assert cap is not None
    total = Decimal(0)
    inputs: dict[str, str] = {}
    for name, amount in allocations:
        val, aerr = _dec(amount, f"allocation {name!r}")
        if aerr:
            return _fail(aerr)
        assert val is not None
        total += val
        inputs[name] = _fmt(val)
    if total > cap:
        return CalcResult(
            ok=False,
            value=None,
            unit="units",
            formula="sum(allocations) <= capacity",
            inputs={**inputs, "capacity": _fmt(cap)},
            intermediates={"sum": _fmt(total), "over_by": _fmt(total - cap)},
            source=source,
            error=f"over-allocated: {total} > capacity {cap}",
        )
    return CalcResult(
        ok=True,
        value=total,
        unit="units",
        formula="sum(allocations) <= capacity",
        inputs={**inputs, "capacity": _fmt(cap)},
        intermediates={"sum": _fmt(total), "headroom": _fmt(cap - total)},
        source=source,
    )
