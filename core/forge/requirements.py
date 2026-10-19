"""Adaptive requirements elicitation — find material unknowns, ask the right questions.

Mission 19B Part 2 rules, enforced here:

- Identify every materially relevant unknown — and only those. No endless
  questionnaires, no silent guesses.
- Every unknown carries its state (Stage D vocabulary), provenance, what it
  affects, and what happens if it stays unknown.
- Questions are prioritized by effect on correctness, safety, feasibility,
  cost, schedule, and acceptance. Dependency-aware: an answer can retire later
  questions. Never ask for what can be derived or retrieved. Never repeat.
- An assumption is never presented as a fact. Authorization to assume is not
  proof.
- Elicitation is DONE only under the explicit Stage-E completion condition.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "Unknown",
    "UnknownState",
    "Requirement",
    "RequirementKind",
    "elicitation_status",
    "from_interview",
    "mark_asked",
    "next_batch",
    "prioritize",
    "requirements_summary",
]

_MATERIAL_AREAS = ("correctness", "safety", "feasibility", "cost", "schedule", "acceptance")
_AREA_WEIGHT = {
    "correctness": 3,
    "safety": 3,
    "acceptance": 3,
    "cost": 2,
    "schedule": 2,
    "feasibility": 2,
}
_COST_WEIGHT = {"high": 3, "medium": 2, "low": 1}


class UnknownState(StrEnum):
    """Stage-D state of an unknown, with explicit semantics.

    KNOWN_FROM_USER — the user stated it; source text preserved.
    VERIFIED_EXTERNALLY — checked against an authoritative source.
    DERIVED — computed from other verified values.
    ASSUMED_WITH_AUTHORIZATION — assumed with permission; NOT a fact.
    UNKNOWN — unresolved; ask or produce a conditional result.
    NOT_APPLICABLE — genuinely irrelevant to the objective.
    CONFLICTED — sources disagree; must be resolved.
    """

    KNOWN_FROM_USER = "KNOWN_FROM_USER"
    VERIFIED_EXTERNALLY = "VERIFIED_EXTERNALLY"
    DERIVED = "DERIVED"
    ASSUMED = "ASSUMED_WITH_AUTHORIZATION"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICTED = "CONFLICTED"


_RESOLVED_STATES = (
    UnknownState.KNOWN_FROM_USER,
    UnknownState.VERIFIED_EXTERNALLY,
    UnknownState.DERIVED,
    UnknownState.ASSUMED,
    UnknownState.NOT_APPLICABLE,
)


class RequirementKind(StrEnum):
    """What a requirement is. Hard constraints stay hard (Part 7)."""

    HARD_CONSTRAINT = "hard_constraint"
    PREFERENCE = "preference"
    OBJECTIVE = "objective"
    SUCCESS_CRITERION = "success_criterion"
    EVIDENCE_REQUIREMENT = "evidence_requirement"
    VERIFICATION_REQUIREMENT = "verification_requirement"
    ASSUMPTION_SUPPLIED = "assumption_supplied"


@dataclass
class Requirement:
    """One requirement, preserving the user's exact words where material."""

    id: str
    kind: RequirementKind
    text: str  # the user's words — never paraphrased away
    source: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        """Normalize boundary strings to enums (JSON/CLI deliver plain str)."""
        if not isinstance(self.kind, RequirementKind):
            try:
                self.kind = RequirementKind(str(self.kind))
            except ValueError:
                self.kind = RequirementKind.OBJECTIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "text": self.text,
            "source": self.source,
            "note": self.note,
        }


@dataclass
class Unknown:
    """One unresolved variable with full Stage-B interrogation."""

    id: str
    question: str  # what to ask the user, if asking is needed
    variable: str = ""
    why_it_matters: str = ""
    affects: tuple[str, ...] = ()
    derivable: bool = False
    derivation_note: str = ""
    retrievable: bool = False
    authoritative_source: str = ""
    must_ask_user: bool = True
    if_unknown: str = ""
    wrong_assumption_cost: str = "medium"  # low|medium|high
    range_safe: bool = False
    range_note: str = ""
    state: UnknownState = UnknownState.UNKNOWN
    provenance: str = ""
    depends_on: tuple[str, ...] = ()
    critical: bool = False
    asked_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Normalize boundary strings to enums — unknown state fails closed."""
        if not isinstance(self.state, UnknownState):
            try:
                self.state = UnknownState(str(self.state))
            except ValueError:
                self.state = UnknownState.UNKNOWN

    @property
    def question_key(self) -> str:
        """Normalized identity so the same question is never asked twice."""
        return re.sub(r"\W+", " ", self.question.lower()).strip()

    def materiality(self) -> int:
        """Deterministic priority score (higher = ask first)."""
        score = 0
        for area in self.affects:
            score += _AREA_WEIGHT.get(area, 1)
        if self.critical:
            score += 3
        if self.must_ask_user:
            score += 2
        score += _COST_WEIGHT.get(self.wrong_assumption_cost, 1)
        return score

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "variable": self.variable,
            "why_it_matters": self.why_it_matters,
            "affects": list(self.affects),
            "derivable": self.derivable,
            "derivation_note": self.derivation_note,
            "retrievable": self.retrievable,
            "authoritative_source": self.authoritative_source,
            "must_ask_user": self.must_ask_user,
            "if_unknown": self.if_unknown,
            "wrong_assumption_cost": self.wrong_assumption_cost,
            "range_safe": self.range_safe,
            "range_note": self.range_note,
            "state": self.state.value,
            "provenance": self.provenance,
            "depends_on": list(self.depends_on),
            "critical": self.critical,
            "materiality": self.materiality(),
        }


def prioritize(unknowns: Iterable[Unknown]) -> list[Unknown]:
    """Order unknowns by effect on correctness/safety/feasibility/cost/schedule/acceptance.

    Resolved and not-applicable unknowns drop out entirely — their questions
    are never asked. Derivable unknowns sort below anything the user must
    answer (never ask for a value that can be computed).
    """

    def key(u: Unknown) -> tuple[int, int, int, str]:
        resolved = 1 if u.state in _RESOLVED_STATES else 0
        derivable = 1 if (u.derivable and not u.must_ask_user) else 0
        return (resolved, derivable, -u.materiality(), u.id)

    return sorted(unknowns, key=key)


def _blocked(u: Unknown, open_ids: set[str], asked: set[str]) -> bool:
    if u.question_key in asked:
        return False  # already asked — never repeats, but not "blocked"
    return any(dep in open_ids for dep in u.depends_on)


def next_batch(
    unknowns: Sequence[Unknown],
    *,
    asked: Iterable[str] = (),
    batch_size: int = 5,
) -> list[Unknown]:
    """The next questions to ask, dependency-aware.

    Independent unknowns may be grouped in one concise batch; an unknown whose
    dependencies are still open waits. Unknowns that are resolved, derivable
    (and not must-ask), or already asked are excluded — no repeats, no
    questions the system can answer itself.
    """
    asked_keys = {re.sub(r"\W+", " ", str(k).lower()).strip() for k in asked}
    open_ids = {
        u.id for u in unknowns if u.state in (UnknownState.UNKNOWN, UnknownState.CONFLICTED)
    }
    out: list[Unknown] = []
    for u in prioritize(unknowns):
        if len(out) >= batch_size:
            break
        if u.state in _RESOLVED_STATES:
            continue
        if u.derivable and not u.must_ask_user:
            continue  # derive it; do not ask
        if u.question_key in asked_keys or u.question_key in u.asked_keys:
            continue  # never ask the same question twice
        if _blocked(u, open_ids, asked_keys):
            continue
        out.append(u)
    return out


def mark_asked(unknowns: Sequence[Unknown], questions: Iterable[str]) -> dict[str, int]:
    """Record asked question keys against unknowns. Returns repeat counts.

    A repeated question is a process defect; the count makes it auditable.
    """
    keys = [re.sub(r"\W+", " ", str(q).lower()).strip() for q in questions]
    seen: set[str] = set()
    repeats = 0
    new_keys: list[str] = []
    for k in keys:
        if k in seen:
            repeats += 1
        seen.add(k)
        new_keys.append(k)
    changed = 0
    for u in unknowns:
        if u.question_key in seen and u.question_key not in u.asked_keys:
            u.asked_keys = (*u.asked_keys, u.question_key)
            changed += 1
    return {"marked": changed, "repeats": repeats}


@dataclass
class ElicitationStatus:
    """Stage-E completion report."""

    complete: bool = False
    blocking: list[str] = field(default_factory=list)
    authorized_assumptions: list[str] = field(default_factory=list)
    unresolved_conflicts: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    verification_defined: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "blocking": list(self.blocking),
            "authorized_assumptions": list(self.authorized_assumptions),
            "unresolved_conflicts": list(self.unresolved_conflicts),
            "counts": dict(self.counts),
            "verification_defined": self.verification_defined,
        }


def elicitation_status(
    unknowns: Sequence[Unknown],
    *,
    verification_defined: bool = False,
) -> ElicitationStatus:
    """The Stage-E completion condition — proceed only when this says complete.

    Complete when: no critical/costly unknown is unresolved or conflicted,
    every assumption is authorized (ASSUMED state only), and the final
    verification criteria are defined. Remaining unknowns must not prevent a
    defensible (possibly conditional) result.
    """
    status = ElicitationStatus(verification_defined=verification_defined)
    counts: dict[str, int] = {}
    for u in unknowns:
        counts[u.state.value] = counts.get(u.state.value, 0) + 1
        if u.state == UnknownState.CONFLICTED:
            status.unresolved_conflicts.append(f"{u.id}: {u.question}")
        if u.state in _RESOLVED_STATES:
            if u.state == UnknownState.ASSUMED:
                status.authorized_assumptions.append(f"{u.id}: {u.question} (assumed, not fact)")
            continue
        if u.critical or u.must_ask_user or u.wrong_assumption_cost == "high":
            status.blocking.append(f"{u.id}: {u.question}")
    status.counts = counts
    clear = not status.blocking and not status.unresolved_conflicts
    status.complete = clear and verification_defined
    return status


def requirements_summary(
    requirements: Sequence[Requirement],
    unknowns: Sequence[Unknown],
) -> str:
    """Structured requirements summary to present before finalizing a plan."""
    lines: list[str] = ["# Requirements summary", "", "## Requirements"]
    for r in requirements:
        lines.append(f"- [{r.kind.value}] {r.id}: {r.text}")
    lines += ["", "## Unknowns"]
    for u in prioritize(unknowns):
        lines.append(
            f"- {u.id} ({u.state.value}, materiality {u.materiality()}): {u.question}"
            + (f" — affects: {', '.join(u.affects)}" if u.affects else "")
        )
    status = elicitation_status(unknowns, verification_defined=False)
    lines += ["", "## Unresolved conflicts"]
    lines += [f"- {c}" for c in status.unresolved_conflicts] or ["- none"]
    return "\n".join(lines)


def from_interview(interview: Any) -> list[Unknown]:
    """Adapt a :class:`core.forge.models.Interview` to explicit unknowns.

    Unanswered required questions become must-ask UNKNOWNs. Interview
    open_questions become UNKNOWNs (cost by default). Low-confidence answers
    (< 0.5) become CONFLICTED-flagged unknowns ("the answer is weak").
    High-confidence answers are already KNOWN_FROM_USER and produce nothing.
    """
    unknowns: list[Unknown] = []
    try:
        answers = {a.question_id: a for a in interview.answers}
        for q in interview.questions:
            ans = answers.get(q.id)
            if ans is None:
                if getattr(q, "required", False):
                    unknowns.append(
                        Unknown(
                            id=f"u:{q.id}",
                            question=q.prompt,
                            variable=q.dimension,
                            why_it_matters=(
                                f"required question in dimension {q.dimension!r} unanswered"
                            ),
                            affects=("correctness", "acceptance"),
                            must_ask_user=True,
                            if_unknown="plan proceeds with a hole in this dimension",
                            wrong_assumption_cost="high" if q.required else "medium",
                            state=UnknownState.UNKNOWN,
                            provenance=f"interview question {q.id}",
                            critical=bool(q.required),
                        )
                    )
                continue
            conf = getattr(ans, "confidence", 1.0) or 0.0
            if conf < 0.5:
                unknowns.append(
                    Unknown(
                        id="u:" + q.id + ":weak",
                        question=q.prompt,
                        variable=q.dimension,
                        why_it_matters="answer confidence < 0.5 — may be wrong",
                        affects=("correctness",),
                        must_ask_user=True,
                        if_unknown="a weak answer may silently drive the plan",
                        wrong_assumption_cost="medium",
                        state=UnknownState.CONFLICTED,
                        provenance=f"interview answer {q.id} (confidence {conf})",
                    )
                )
        for i, oq in enumerate(getattr(interview, "open_questions", []) or []):
            unknowns.append(
                Unknown(
                    id=f"u:open:{i}",
                    question=str(oq),
                    variable="open_question",
                    why_it_matters="left open by the interview",
                    affects=("acceptance",),
                    must_ask_user=True,
                    if_unknown="plan carries an acknowledged hole",
                    wrong_assumption_cost="medium",
                    state=UnknownState.UNKNOWN,
                    provenance="interview.open_questions",
                )
            )
    except Exception:  # noqa: BLE001 — fail-open adapter; never break the caller
        return []
    return unknowns
