"""Structured constraints and conjunctive acceptance — hard stays hard.

Mission 19B Part 7 rules, enforced here:

- Each constraint is a structured record: requirement, type, validation
  method, actual value, expected bound, evidence source + kind, result.
- Result vocabulary: ``satisfied | violated | unresolved | conditional | n_a``.
- Acceptance is CONJUNCTIVE. A high score never compensates for a violated or
  unresolved hard constraint. Missing evidence never silently becomes a pass.
- Evidence kinds stay distinct: machine-checked, human-verified, simulated,
  inferred, externally-verified, missing. Simulated is never human validation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

__all__ = [
    "AcceptanceVerdict",
    "ConstraintRecord",
    "ConstraintResult",
    "EvidenceKind",
    "check_phase_count",
    "parse_budget_ceiling",
    "validate_constraints",
]


class ConstraintResult(StrEnum):
    """Outcome of validating one constraint."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNRESOLVED = "unresolved"
    CONDITIONAL = "conditional"
    NOT_APPLICABLE = "n_a"


class EvidenceKind(StrEnum):
    """What kind of evidence backs the result (never interchangeable)."""

    MACHINE_CHECKED = "machine_checked"
    HUMAN_VERIFIED = "human_verified"
    SIMULATED = "simulated"
    INFERRED = "inferred"
    EXTERNALLY_VERIFIED = "externally_verified"
    MISSING = "missing"


@dataclass
class ConstraintRecord:
    """One constraint, validated independently."""

    id: str
    requirement: str  # the user's words, e.g. "TOTAL MONEY <= $200"
    kind: str = "hard"  # hard | preference
    validation_method: str = ""
    actual: str = ""
    expected: str = ""
    evidence_source: str = ""
    evidence_kind: EvidenceKind = EvidenceKind.MISSING
    result: ConstraintResult = ConstraintResult.UNRESOLVED
    explanation: str = ""

    def __post_init__(self) -> None:
        """Normalize boundary strings to enums, FAIL CLOSED on unknowns.

        Records arriving from JSON/CLI boundaries carry plain strings. An
        unrecognized result must not fall through the acceptance checks —
        it becomes UNRESOLVED (missing evidence counts as failure).
        """
        if not isinstance(self.evidence_kind, EvidenceKind):
            try:
                self.evidence_kind = EvidenceKind(str(self.evidence_kind))
            except ValueError:
                self.evidence_kind = EvidenceKind.MISSING
        if not isinstance(self.result, ConstraintResult):
            try:
                self.result = ConstraintResult(str(self.result))
            except ValueError:
                self.result = ConstraintResult.UNRESOLVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement": self.requirement,
            "kind": self.kind,
            "validation_method": self.validation_method,
            "actual": self.actual,
            "expected": self.expected,
            "evidence_source": self.evidence_source,
            "evidence_kind": self.evidence_kind.value,
            "result": self.result.value,
            "explanation": self.explanation,
        }


@dataclass
class AcceptanceVerdict:
    """Conjunctive acceptance over constraint records."""

    accepted: bool = False
    reason: str = ""
    blocking: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    score_note: str = (
        "the checklist is a conjunction, not a score — no aggregate can offset a "
        "violated or unresolved hard constraint"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "blocking": list(self.blocking),
            "conditions": list(self.conditions),
            "score_note": self.score_note,
        }


def validate_constraints(records: Sequence[ConstraintRecord]) -> AcceptanceVerdict:
    """Conjunctive acceptance: every hard constraint must be satisfied.

    - hard VIOLATED → not accepted (explicit failure).
    - hard UNRESOLVED → not accepted (unverified counts as failure).
    - hard CONDITIONAL → accepted only with the conditions listed and carried.
    - preferences never block.
    - simulated evidence on a hard constraint stays unresolved UNLESS the user
      accepted the proxy — that acceptance must be recorded in the explanation.
    """
    verdict = AcceptanceVerdict()
    for r in records:
        tag = f"{r.id}: {r.requirement}"
        if r.kind != "hard":
            if r.result == ConstraintResult.VIOLATED:
                verdict.conditions.append(f"preference missed: {tag}")
            continue
        if r.result == ConstraintResult.SATISFIED:
            simulated = r.evidence_kind == EvidenceKind.SIMULATED
            accepted = "user accepted" in r.explanation.lower()
            if simulated and not accepted:
                verdict.blocking.append(
                    f"{tag} — evidence is simulated, not human-verified; "
                    "unresolved unless the user accepted the proxy (recorded)"
                )
            continue
        if r.result == ConstraintResult.VIOLATED:
            verdict.blocking.append(f"{tag} — violated ({r.explanation or r.actual})")
        elif r.result == ConstraintResult.UNRESOLVED:
            verdict.blocking.append(f"{tag} — unresolved (missing evidence counts as failure)")
        elif r.result == ConstraintResult.CONDITIONAL:
            verdict.conditions.append(f"{tag} — conditional: {r.explanation or r.expected}")
    verdict.accepted = not verdict.blocking
    if verdict.accepted and verdict.conditions:
        verdict.reason = "GO-WITH-CONDITIONS — all hard constraints satisfied; carry the conditions"
    elif verdict.accepted:
        verdict.reason = "GO — every hard constraint satisfied on real evidence"
    else:
        verdict.reason = "NO-GO — hard constraints violated or unresolved"
    return verdict


_MONEY_RE = re.compile(
    r"(?:at most|no more than|max(?:imum)?|up to|<=|≤|below|under)\s*"
    r"(?:(?P<pre>[$€£])\s*)?(?P<amt>\d+(?:[.,]\d+)?)\s*(?P<post>[$€£]|[A-Za-z]{3})?",
    re.IGNORECASE,
)


def parse_budget_ceiling(text: str) -> tuple[Decimal | None, str]:
    """Deterministically extract a budget ceiling from constraint text.

    Returns ``(amount, currency)`` or ``(None, "")`` when no ceiling is stated.
    Never invents a ceiling that the text does not contain.
    """
    if not isinstance(text, str):
        return None, ""
    m = _MONEY_RE.search(text)
    if not m:
        return None, ""
    amount = Decimal(m.group("amt").replace(",", ""))
    cur = (m.group("pre") or m.group("post") or "").strip()
    if cur in ("$", "USD"):
        cur = "USD"
    elif cur in ("€", "EUR"):
        cur = "EUR"
    elif cur in ("£", "GBP"):
        cur = "GBP"
    return amount, cur


_WORD_NUMBERS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_PHASE_COUNT_RE = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"\s+phases?\b",
    re.IGNORECASE,
)


def phase_requirement_count(text: str) -> int | None:
    """Explicit phase count declared in requirement text — digits or words (one..twelve).

    Returns None when no explicit count is present. Never guesses: a requirement
    without a stated count is not a phase-count requirement.
    """
    m = _PHASE_COUNT_RE.search(str(text or ""))
    if not m:
        return None
    token = m.group(1).lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def check_phase_count(requirement: str, actual_count: int) -> ConstraintRecord:
    """Validate an explicit phase-count constraint like 'EXACTLY 3 PHASES'
    (digits or words: 'exactly three phases')."""
    expected = phase_requirement_count(requirement)
    if expected is None:
        return ConstraintRecord(
            id="phase-count",
            requirement=requirement,
            validation_method="none — no numeric phase count in the requirement",
            actual=str(actual_count),
            result=ConstraintResult.NOT_APPLICABLE,
            explanation="no explicit phase count to enforce",
        )
    ok = actual_count == expected
    return ConstraintRecord(
        id="phase-count",
        requirement=requirement,
        validation_method="recount command phases and compare with the declared count",
        actual=str(actual_count),
        expected=str(expected),
        evidence_kind=EvidenceKind.MACHINE_CHECKED,
        result=ConstraintResult.SATISFIED if ok else ConstraintResult.VIOLATED,
        explanation="" if ok else f"plan has {actual_count} phases, requirement says {expected}",
    )


def constraint_rows(records: Iterable[ConstraintRecord]) -> list[dict[str, Any]]:
    """Render records as gate-style table rows: requirement | type | actual | expected | result."""
    return [r.to_dict() for r in records]
