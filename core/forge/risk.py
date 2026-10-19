"""Quantitative risk analysis — honest probability, expected loss, and no false precision.

Mission 19B Part 5 rules, enforced here:

- Every probability is CLASSIFIED (observed frequency / statistical / external /
  expert judgment / model / scenario assumption / unknown) with method, source,
  and limitations. A number without a class is not defensible evidence.
- ``E[L] = P(event) × E[loss | event]`` only when both terms have defensible
  meanings and compatible units. Unknown class or missing terms → explicit
  error, never a fabricated loss.
- Scenario expected value ``E[X] = Σ P_i X_i`` validates its own scenario space
  (probabilities in [0,1], summing to 1).
- A probability-severity MATRIX is a prioritization device, NOT a quantitative
  calculation. Ordinal 1–5 labels are never multiplied into a "risk percentage".
- Mitigations do not auto-reduce risk. Before/after estimates produce absolute
  and relative reduction; unknown effect stays unknown.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from core.forge.quant import CalcResult, _dec, _fmt, _quantize

__all__ = [
    "ProbabilityClass",
    "RiskEntry",
    "expected_loss",
    "mitigation_effect",
    "ordinal_priority",
    "scenario_expected_value",
]


class ProbabilityClass(StrEnum):
    """How a probability estimate was obtained (Part 5.2)."""

    OBSERVED_FREQUENCY = "observed_frequency"
    STATISTICALLY_ESTIMATED = "statistically_estimated"
    EXTERNALLY_SOURCED = "externally_sourced"
    EXPERT_JUDGMENT = "expert_judgment"
    MODEL_GENERATED = "model_generated"
    SCENARIO_ASSUMPTION = "scenario_assumption"
    UNKNOWN = "unknown"


_NON_CALIBRATED = (
    ProbabilityClass.EXPERT_JUDGMENT,
    ProbabilityClass.MODEL_GENERATED,
    ProbabilityClass.SCENARIO_ASSUMPTION,
)


@dataclass
class RiskEntry:
    """One material risk (Part 5.1 fields). Inherent vs residual kept distinct."""

    risk_id: str
    description: str = ""
    cause: str = ""
    consequence: str = ""
    affected_objectives: tuple[str, ...] = ()
    probability: Decimal | None = None
    probability_range: tuple[Decimal, Decimal] | None = None
    probability_class: ProbabilityClass = ProbabilityClass.UNKNOWN
    probability_method: str = ""
    probability_source: str = ""
    sample_size: int | None = None
    severity: Decimal | None = None
    severity_unit: str = ""
    exposure_horizon: str = ""
    controls: str = ""
    mitigation: str = ""
    contingency: str = ""
    owner: str = ""
    evidence: str = ""
    residual_probability: Decimal | None = None
    residual_severity: Decimal | None = None
    uncertainty: str = ""
    review_trigger: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "description": self.description,
            "cause": self.cause,
            "consequence": self.consequence,
            "affected_objectives": list(self.affected_objectives),
            "probability": str(self.probability) if self.probability is not None else None,
            "probability_range": (
                [str(self.probability_range[0]), str(self.probability_range[1])]
                if self.probability_range
                else None
            ),
            "probability_class": self.probability_class.value,
            "probability_method": self.probability_method,
            "probability_source": self.probability_source,
            "sample_size": self.sample_size,
            "severity": str(self.severity) if self.severity is not None else None,
            "severity_unit": self.severity_unit,
            "exposure_horizon": self.exposure_horizon,
            "controls": self.controls,
            "mitigation": self.mitigation,
            "contingency": self.contingency,
            "owner": self.owner,
            "evidence": self.evidence,
            "residual_probability": (
                str(self.residual_probability) if self.residual_probability is not None else None
            ),
            "residual_severity": (
                str(self.residual_severity) if self.residual_severity is not None else None
            ),
            "uncertainty": self.uncertainty,
            "review_trigger": self.review_trigger,
        }


def expected_loss(
    probability: Any,
    conditional_loss: Any,
    *,
    probability_class: ProbabilityClass | str = ProbabilityClass.UNKNOWN,
    loss_unit: str = "",
    probability_method: str = "",
    probability_source: str = "",
    source: str = "",
) -> CalcResult:
    """E[L] = P(event) × E[loss | event] — only when both terms are defensible.

    Refuses: missing terms, probability outside [0,1], UNKNOWN probability
    class, empty loss unit. Non-statistical classes compute but carry a
    limitation — never described as statistically calibrated.
    """
    try:
        pclass = (
            probability_class
            if isinstance(probability_class, ProbabilityClass)
            else ProbabilityClass(str(probability_class))
        )
    except ValueError:
        return CalcResult(
            ok=False,
            value=None,
            error=f"unrecognized probability class: {probability_class!r}",
        )
    p, err1 = _dec(probability, "probability")
    loss, err2 = _dec(conditional_loss, "conditional_loss")
    if err1 or err2:
        return CalcResult(ok=False, value=None, error=err1 or err2 or "invalid input")
    assert p is not None and loss is not None
    if p < 0 or p > 1:
        return CalcResult(
            ok=False, value=None, error=f"probability {p} outside [0, 1] — not a probability"
        )
    if pclass is ProbabilityClass.UNKNOWN:
        return CalcResult(
            ok=False,
            value=None,
            error=(
                "probability class is UNKNOWN — expected loss is not defensible; "
                "classify the estimate first"
            ),
        )
    if not loss_unit:
        return CalcResult(
            ok=False,
            value=None,
            error="conditional loss needs an explicit unit (money, days, points) for meaning",
        )
    value = _quantize(p * loss, "none")
    limitations: list[str] = []
    if pclass in _NON_CALIBRATED:
        limitations.append(
            f"probability is {pclass.value} — not a statistically calibrated probability"
        )
    if not probability_source:
        limitations.append("probability has no recorded source")
    return CalcResult(
        ok=True,
        value=value,
        unit=f"probability × {loss_unit}",
        formula="E[L] = P(event) × E[loss | event]",
        inputs={
            "probability": _fmt(p),
            "conditional_loss": _fmt(loss),
            "probability_class": pclass.value,
            "probability_method": probability_method,
            "probability_source": probability_source,
        },
        source=source,
        observed=pclass.value,
        limitations=limitations,
    )


def scenario_expected_value(
    outcomes: Sequence[tuple[Any, Any]],
    *,
    source: str = "",
    unit: str = "",
) -> CalcResult:
    """E[X] = Σ P_i X_i over a validated scenario space.

    Validates: at least one outcome, probabilities in [0,1], probabilities sum
    to 1 (tolerance 1e-9). A non-consistent space is a hard error — do not
    normalize silently.
    """
    if not outcomes:
        return CalcResult(
            ok=False, value=None, error="no outcomes — E[X] over an empty space is undefined"
        )
    probs: list[Decimal] = []
    vals: list[Decimal] = []
    inputs: dict[str, str] = {}
    for i, item in enumerate(outcomes):
        if not isinstance(item, tuple) or len(item) != 2:
            return CalcResult(
                ok=False, value=None, error=f"outcome {i} is not (probability, value)"
            )
        p, err1 = _dec(item[0], f"outcome {i} probability")
        x, err2 = _dec(item[1], f"outcome {i} value")
        if err1 or err2:
            return CalcResult(ok=False, value=None, error=err1 or err2 or "invalid input")
        assert p is not None and x is not None
        if p < 0 or p > 1:
            return CalcResult(
                ok=False, value=None, error=f"outcome {i} probability {p} outside [0, 1]"
            )
        probs.append(p)
        vals.append(x)
        inputs[f"p{i}"] = _fmt(p)
        inputs[f"x{i}"] = _fmt(x)
    total_p = sum(probs, Decimal(0))
    if abs(total_p - Decimal(1)) > Decimal("1e-9"):
        return CalcResult(
            ok=False,
            value=None,
            formula="E[X] = Σ P_i X_i",
            inputs=inputs,
            intermediates={"sum_p": _fmt(total_p)},
            error=f"probabilities sum to {total_p}, not 1 — scenario space is inconsistent",
        )
    total = sum((p * x for p, x in zip(probs, vals, strict=True)), Decimal(0))
    return CalcResult(
        ok=True,
        value=total,
        unit=unit,
        formula="E[X] = Σ P_i X_i",
        inputs=inputs,
        intermediates={"sum_p": _fmt(total_p)},
        source=source,
        observed="calculated",
    )


def ordinal_priority(probability_label: str, severity_label: str) -> dict[str, Any]:
    """Ordinal matrix → PRIORITY ONLY. Never a quantitative risk number.

    Multiplying 1–5 ordinal labels and calling the product a "risk percentage"
    is exactly the false precision this mission forbids. The output is a
    qualitative priority label with its limitation spelled out.
    """
    order = {"low": 0, "medium": 1, "high": 2}
    p = order.get(str(probability_label).strip().lower())
    s = order.get(str(severity_label).strip().lower())
    if p is None or s is None:
        return {
            "priority": "unknown",
            "method": "ordinal matrix",
            "limitation": (
                "labels must be qualitative (low/medium/high); "
                "this is prioritization, not a quantitative risk calculation"
            ),
            "error": (
                f"unrecognized labels: probability={probability_label!r}, "
                f"severity={severity_label!r}"
            ),
        }
    rank = p + s
    label = "high" if rank >= 3 else ("medium" if rank == 2 else "low")
    return {
        "priority": label,
        "method": "ordinal matrix (additive banding)",
        "limitation": (
            "ordinal labels are not numbers — the result ranks priorities and is "
            "NOT a probability, an expected loss, or a precise risk percentage"
        ),
    }


def mitigation_effect(
    probability_before: Any,
    probability_after: Any,
    conditional_loss: Any,
    implementation_cost: Any = None,
    *,
    loss_unit: str = "",
    source: str = "",
) -> dict[str, Any]:
    """Before/after mitigation analysis (Part 5.5). Unknown effect stays unknown.

    Returns absolute risk reduction, relative risk reduction, change in
    expected loss, implementation cost, and residual risk — or an explicit
    ``effect: "unknown"`` with the evidence needed to estimate it.
    """
    base: dict[str, Any] = {
        "effect": "unknown",
        "absolute_reduction": None,
        "relative_reduction_percent": None,
        "delta_expected_loss": None,
        "implementation_cost": str(implementation_cost)
        if implementation_cost is not None
        else None,
        "residual_expected_loss": None,
        "assumptions": [],
        "evidence_needed": "",
        "error": "",
    }
    pb, err1 = _dec(probability_before, "probability_before")
    pa, err2 = _dec(probability_after, "probability_after")
    loss, err3 = _dec(conditional_loss, "conditional_loss")
    if err1 or err2 or err3:
        base["error"] = err1 or err2 or err3 or "invalid input"
        base["evidence_needed"] = "defensible before/after probabilities and a conditional loss"
        return base
    assert pb is not None and pa is not None and loss is not None
    for name, p in (("probability_before", pb), ("probability_after", pa)):
        if p < 0 or p > 1:
            base["error"] = f"{name}={p} outside [0, 1]"
            base["evidence_needed"] = "probabilities in [0, 1]"
            return base
    arr = pb - pa  # absolute risk reduction
    out = dict(base)
    out["effect"] = "estimated"
    out["absolute_reduction"] = str(arr)
    if pb == 0:
        out["relative_reduction_percent"] = None
        out["error"] = "relative reduction undefined (before-probability is zero)"
    else:
        out["relative_reduction_percent"] = str(
            _quantize(arr / pb * Decimal(100), "half-up")
        )
    out["delta_expected_loss"] = str(arr * loss)
    out["residual_expected_loss"] = str(pa * loss)
    out["assumptions"] = [
        "before/after probabilities are comparable estimates of the same event",
        f"conditional loss unchanged by the mitigation ({_fmt(loss)} {loss_unit})",
    ]
    out["source"] = source
    return out
