"""Compass builder — acceptance criteria: Given/When/Then, checklist, metrics.

``build_compass(interview, blueprint=None, commands=None) -> AcceptanceCriteria``
turns the interview's ``success`` and ``edge_cases`` answers into verifiable
acceptance:

* **scenarios** — proper Given/When/Then dicts (happy path from ``success``,
  defensive path from ``edge_cases``)
* **checklist** — verifiable yes/no items from ``constraints``/``success``
  (plus one completeness gate per execution phase when commands are known)
* **metrics**   — measurable targets parsed from ``success`` answers

Universal: acceptance phrasing works for a research study, a course, a move
or a novel just as well as for software.

FAIL-OPEN: every public boundary catches ``Exception`` and returns a safe
(possibly empty) ``AcceptanceCriteria``. This module never raises.
"""

from __future__ import annotations

import re
from typing import Any

from core.forge.blueprint import (
    answer_texts,
    by_dimension,
    clean_item,
    collect_answers,
    domain_label,
    match_any,
)
from core.forge.models import (
    AcceptanceCriteria,
    Blueprint,
    Command,
    Domain,
    Interview,
    _safe_float,
    _safe_list,
    _safe_str,
)

__all__ = ["build_compass"]

_TARGET_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([%a-zA-Z/]{0,12})")

_DECREASE_WORDS = (
    "reduce", "lower", "under", "below", "less", "fewer", "cut", "minim",
    "at most", "no more", "drop", "decrease", "shorter", "faster than",
)
_INCREASE_WORDS = (
    "increase", "grow", "more", "above", "at least", "reach", "exceed",
    "boost", "raise", "double", "triple", "maximize", "at most",
)
_NEGATIVE_WORDS = (
    "fail", "crash", "error", "invalid", "missing", "empty", "timeout",
    "offline", "unavailable", "corrupt", "reject", "denied", "overflow",
    "edge", "unusual", "unexpected", "wrong", "bad", "hostile",
)


def build_compass(
    interview: Interview,
    blueprint: Blueprint | None = None,
    commands: list[Command] | None = None,
) -> AcceptanceCriteria:
    """Build ``AcceptanceCriteria`` (Given/When/Then + checklist + metrics).

    FAIL-OPEN: never raises; returns a safe (possibly empty) criteria set.
    """
    try:
        return _build_compass_impl(interview, blueprint, commands)
    except Exception:  # noqa: BLE001
        return AcceptanceCriteria()


def _short(text: str, limit: int = 70) -> str:
    s = _safe_str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 3].rsplit(" ", 1)[0] + "..."


def _capitalize(text: str) -> str:
    s = _safe_str(text)
    return s[:1].upper() + s[1:] if s else s


def _scenario(
    kind: str,
    title: str,
    given: str,
    when: str,
    then: str,
    source: str,
    index: int,
) -> dict[str, str]:
    return {
        "id": f"{kind}-{index:02d}",
        "title": _short(title, 70),
        "given": _short(given, 220),
        "when": _short(when, 220),
        "then": _short(then, 220),
        "source": _safe_str(source),
    }


def _metric(text: str, source: str) -> dict[str, Any]:
    """One measurable target parsed from a success answer. Never raises."""
    s = _safe_str(text)
    target: float | None = None
    unit = ""
    try:
        m = _TARGET_RE.search(s)
        if m:
            target = _safe_float(m.group(1).replace(",", "."), 0.0)
            unit = _safe_str(m.group(2)).strip().lower()
    except Exception:  # noqa: BLE001
        target, unit = None, ""
    if match_any(s, _DECREASE_WORDS):
        direction = "decrease"
    elif match_any(s, _INCREASE_WORDS):
        direction = "increase"
    else:
        direction = "maintain"
    return {
        "name": _short(s, 48),
        "target": target,
        "unit": unit,
        "direction": direction,
        "measure": s,
        "source": _safe_str(source),
    }


def _build_compass_impl(
    interview: Any,
    blueprint: Any,
    commands: Any,
) -> AcceptanceCriteria:
    acc = AcceptanceCriteria()
    try:
        dom = Domain.coerce(getattr(interview, "domain", Domain.GENERAL))
    except Exception:  # noqa: BLE001
        dom = Domain.GENERAL
    label = domain_label(dom).lower()
    title = _safe_str(getattr(interview, "title", "")) \
        or _safe_str(getattr(blueprint, "title", "")) or f"the {label} effort"

    answers = collect_answers(interview)
    bydim = by_dimension(answers)
    success = bydim.get("success", [])
    edge = bydim.get("edge_cases", [])
    audience = answer_texts(bydim, "audience")
    who = _short(audience[0], 60) if audience else "a stakeholder"

    # -- scenarios: Given / When / Then ---------------------------------
    for i, a in enumerate(success[:12], start=1):
        try:
            text = _safe_str(a.text)
            acc.scenarios.append(_scenario(
                "happy",
                text,
                f"The {label} work in '{_short(title, 48)}' has been delivered "
                f"to {who}.",
                f"The outcome is verified against: \u201c{text}\u201d",
                f"{_capitalize(text)}",
                a.question_id,
                i,
            ))
        except Exception:  # noqa: BLE001
            continue

    for i, a in enumerate(edge[:12], start=1):
        try:
            text = _safe_str(a.text)
            acc.scenarios.append(_scenario(
                "edge",
                text,
                f"This edge case occurs during the work: \u201c{text}\u201d",
                "the situation is encountered in execution or delivery",
                "it is handled explicitly: the work degrades safely, the "
                "constraints are not violated, and the outcome is recorded",
                a.question_id,
                i,
            ))
        except Exception:  # noqa: BLE001
            continue

    # -- checklist: verifiable yes/no items ------------------------------
    seen: set[str] = set()

    def check(text: str) -> None:
        try:
            t = clean_item(text)
            if t and t.lower() not in seen:
                seen.add(t.lower())
                acc.checklist.append(t)
        except Exception:  # noqa: BLE001
            return

    for a in bydim.get("constraints", [])[:15]:
        check(f"Constraint holds \u2014 {_safe_str(a.text)}")
    for a in success[:15]:
        check(f"Success demonstrated \u2014 {_safe_str(a.text)}")
    for text in _safe_list(getattr(blueprint, "constraints", []))[:10]:
        check(f"Constraint holds \u2014 {clean_item(text)}")
    for text in _safe_list(getattr(blueprint, "success_metrics", []))[:10]:
        check(f"Success demonstrated \u2014 {clean_item(text)}")

    # one completeness gate per execution phase (when commands are known)
    phase_counts: dict[str, int] = {}
    for cmd in _safe_list(commands)[:200]:
        try:
            phase = _safe_str(getattr(cmd, "phase", "")) or "General"
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
        except Exception:  # noqa: BLE001
            continue
    for phase, count in phase_counts.items():
        check(f"All {count} command(s) in phase '{_short(phase, 40)}' are complete")
    if phase_counts:
        check("No open questions remain unresolved")

    # -- metrics: measurable targets from success answers ----------------
    seen_metrics: set[str] = set()

    def metric(text: str, source: str) -> None:
        try:
            m = _metric(text, source)
            key = _safe_str(m.get("measure")).lower()
            if key and key not in seen_metrics:
                seen_metrics.add(key)
                acc.metrics.append(m)
        except Exception:  # noqa: BLE001
            return

    for a in success[:15]:
        metric(_safe_str(a.text), a.question_id)
    for text in _safe_list(getattr(blueprint, "success_metrics", []))[:10]:
        metric(clean_item(text), "(blueprint)")

    return acc
