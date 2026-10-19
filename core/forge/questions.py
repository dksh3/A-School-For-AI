"""Configurable adaptive questioning controller.

A thin session layer over the existing elicitation machinery in
``core.forge.requirements``: it reuses ``prioritize``/``next_batch``/
``mark_asked``/``elicitation_status`` as the single source of question
selection and completion logic, and adds:

- a validated session configuration (``QuestionBudget``),
- strict user-facing question-budget accounting (``QuestioningSession``),
- deterministic adaptive follow-ups and contradiction handling,
- early stopping that is never confused with success,
- strict save/load so a resumed session never silently regains budget.

Design rules encoded here (see mission docs):

- every question actually presented consumes one unit of the budget;
- follow-ups consume units from the same budget;
- duplicates are refused and never refill the budget;
- budget exhaustion is not success; unresolved questions stay blocking;
- malformed persisted state fails closed — it never restores a full budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.forge.requirements import (
    Unknown,
    UnknownState,
    elicitation_status,
    mark_asked,
    next_batch,
)

#: Documented default budget when the feature is engaged without a custom
#: value: 4 default batches (``next_batch`` default batch size is 5).
DEFAULT_QUESTION_BUDGET = 20

#: Documented safety limit. A single investigation session asking more than
#: this many user-facing questions is out of scope for one sitting and would
#: risk an unbounded questioning loop. Values above the limit are rejected,
#: never silently clamped.
MAX_QUESTION_BUDGET = 100

#: Answers that do not settle a question (deterministic markers).
UNCERTAIN_MARKERS = frozenset(
    {"unknown", "not sure", "unsure", "tbd", "no idea", "cannot say", "ask later", "?"}
)

SESSION_VERSION = 1


def _norm_key(text: str) -> str:
    import re

    return re.sub(r"\W+", " ", str(text).lower()).strip()


def _coerce_state(value: Any) -> UnknownState:
    """Boundary coercion for loader input — mirrors Unknown.__post_init__ (fail-closed)."""
    try:
        return UnknownState(str(value or "UNKNOWN"))
    except ValueError:
        return UnknownState.UNKNOWN


def _unknown_from_dict(d: dict[str, Any]) -> Unknown:
    """Rebuild an Unknown from ``Unknown.to_dict`` output (session snapshots)."""
    return Unknown(
        id=str(d.get("id") or ""),
        question=str(d.get("question") or ""),
        variable=str(d.get("variable") or ""),
        why_it_matters=str(d.get("why_it_matters") or ""),
        affects=tuple(str(a) for a in (d.get("affects") or ())),
        derivable=bool(d.get("derivable")),
        derivation_note=str(d.get("derivation_note") or ""),
        retrievable=bool(d.get("retrievable")),
        authoritative_source=str(d.get("authoritative_source") or ""),
        must_ask_user=bool(d.get("must_ask_user", True)),
        if_unknown=str(d.get("if_unknown") or ""),
        wrong_assumption_cost=str(d.get("wrong_assumption_cost") or "medium"),
        range_safe=bool(d.get("range_safe")),
        range_note=str(d.get("range_note") or ""),
        state=_coerce_state(d.get("state")),
        provenance=str(d.get("provenance") or ""),
        depends_on=tuple(str(x) for x in (d.get("depends_on") or ())),
        critical=bool(d.get("critical")),
        asked_keys=tuple(str(k) for k in (d.get("asked_keys") or ())),
    )


@dataclass(frozen=True)
class QuestionBudget:
    """Validated session configuration for adaptive questioning."""

    question_budget: int = DEFAULT_QUESTION_BUDGET
    strategy: str = "adaptive"
    depth: str = "balanced"
    allow_followups: bool = True
    stop_early: bool = True

    def __post_init__(self) -> None:
        budget = self.question_budget
        if isinstance(budget, bool) or not isinstance(budget, int):
            raise ValueError(
                f"question_budget must be a positive integer, got "
                f"{type(budget).__name__} ({budget!r}) — pass an integer "
                f"1..{MAX_QUESTION_BUDGET}"
            )
        if budget < 1:
            raise ValueError(
                f"question_budget must be at least 1, got {budget} — a budget of "
                f"0 would forbid every question; say what you want to allow"
            )
        if budget > MAX_QUESTION_BUDGET:
            raise ValueError(
                f"question_budget {budget} exceeds the safety limit "
                f"{MAX_QUESTION_BUDGET} — lower the budget (values above the "
                f"limit are rejected, never silently clamped)"
            )
        if self.strategy != "adaptive":
            raise ValueError(
                f"strategy must be 'adaptive', got {self.strategy!r} — "
                f"adaptive is the only supported strategy"
            )
        if self.depth != "balanced":
            raise ValueError(
                f"depth must be 'balanced', got {self.depth!r} — "
                f"balanced is the only supported depth"
            )
        flags = (("allow_followups", self.allow_followups), ("stop_early", self.stop_early))
        for name, value in flags:
            if not isinstance(value, bool):
                raise ValueError(
                    f"{name} must be a boolean, got {type(value).__name__} ({value!r})"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_budget": self.question_budget,
            "strategy": self.strategy,
            "depth": self.depth,
            "allow_followups": self.allow_followups,
            "stop_early": self.stop_early,
        }

    @classmethod
    def from_dict(cls, data: Any) -> QuestionBudget:
        """Strict loader: unknown keys and malformed values raise ValueError."""
        if not isinstance(data, dict):
            raise ValueError(
                f"question budget config must be a JSON object, got "
                f"{type(data).__name__}"
            )
        allowed = {
            "question_budget",
            "strategy",
            "depth",
            "allow_followups",
            "stop_early",
        }
        unknown_keys = sorted(set(data) - allowed)
        if unknown_keys:
            raise ValueError(
                f"unknown question budget config key(s): {', '.join(unknown_keys)} "
                f"— allowed: {', '.join(sorted(allowed))}"
            )
        return cls(
            question_budget=data.get("question_budget", DEFAULT_QUESTION_BUDGET),
            strategy=data.get("strategy", "adaptive"),
            depth=data.get("depth", "balanced"),
            allow_followups=data.get("allow_followups", True),
            stop_early=data.get("stop_early", True),
        )


@dataclass(frozen=True)
class Presentation:
    """One question actually presented to the user (consumes one budget unit)."""

    id: str
    question: str
    why: str
    index: int
    remaining_after: int
    kind: str = "original"  # "original" | "follow-up"


@dataclass
class QuestioningSession:
    """Adaptive questioning controller with strict budget accounting."""

    config: QuestionBudget
    unknowns: list[Unknown] = field(default_factory=list)
    presented: int = 0
    asked_keys: list[str] = field(default_factory=list)
    answers: list[dict[str, Any]] = field(default_factory=list)
    followups_asked: int = 0
    repeats_refused: int = 0
    verification_defined: bool = False
    stop_reason: str | None = None
    stop_detail: str = ""

    # ------------------------------------------------------------------ state

    @property
    def remaining(self) -> int:
        return max(0, self.config.question_budget - self.presented)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def _find(self, question: str) -> Unknown | None:
        key = _norm_key(question)
        for u in self.unknowns:
            if u.id == question or u.question_key == key or _norm_key(u.question) == key:
                return u
        return None

    def _followup(self, orig: Unknown, answer: str, reason: str) -> Unknown:
        n = sum(1 for u in self.unknowns if u.id.startswith(f"{orig.id}:fu:")) + 1
        followup = Unknown(
            id=f"{orig.id}:fu:{n}",
            question=(
                f"Follow-up on {orig.id}: {orig.question} — the answer "
                f"{answer!r} does not settle it ({reason})"
            ),
            variable=orig.variable or orig.id,
            why_it_matters=orig.why_it_matters or reason,
            affects=orig.affects or ("correctness",),
            derivable=False,
            derivation_note="",
            retrievable=False,
            authoritative_source="",
            must_ask_user=True,
            if_unknown=orig.if_unknown or "record an explicit unknown",
            wrong_assumption_cost="high",
            range_safe=orig.range_safe,
            range_note=orig.range_note,
            state=UnknownState.UNKNOWN,
            provenance=f"follow-up to {orig.id} (adaptive questioning)",
            depends_on=(),
            critical=orig.critical,
            asked_keys=(),
        )
        self.unknowns.append(followup)
        return followup

    def record_answer(
        self, question: str, answer: str, *, confidence: float | None = None
    ) -> dict[str, Any]:
        """Validate and record one answer; may raise a deterministic follow-up.

        Semantics (existing mechanisms):
        - the question is marked asked (``mark_asked``);
        - a normal answer resolves the unknown as KNOWN_FROM_USER;
        - a low-confidence (< 0.5) answer marks it CONFLICTED (weak evidence);
        - an uncertain marker / empty / question-shaped answer leaves it open
          and, when follow-ups are enabled, raises a follow-up unknown;
        - an answer that contradicts an earlier answer for the same variable
          marks both states CONFLICTED and raises a follow-up.
        """
        unknown = self._find(question)
        if unknown is None:
            raise ValueError(
                f"question not in this session: {question!r} — ask a question "
                f"from the current batch (ids like u-tax)"
            )
        text = str(answer or "").strip()
        marks = mark_asked(self.unknowns, [unknown.question])
        key = unknown.question_key
        if key not in self.asked_keys:
            self.asked_keys.append(key)
        result: dict[str, Any] = {
            "id": unknown.id,
            "question_key": key,
            "answer": text,
            "confidence": confidence,
            "followup": None,
            "state": str(unknown.state),
        }

        uncertain = (
            not text or text.casefold().rstrip(".") in UNCERTAIN_MARKERS or text.endswith("?")
        )
        weak = confidence is not None and confidence < 0.5
        contradiction = self._contradiction(unknown, text) if text and not uncertain else None

        self.answers.append(
            {
                "id": unknown.id,
                "question_key": key,
                "answer": text,
                "confidence": confidence,
                "at_state": str(unknown.state),
            }
        )

        if contradiction is not None:
            contradiction.state = UnknownState.CONFLICTED
            unknown.state = UnknownState.CONFLICTED
            result["state"] = str(unknown.state)
            if self.config.allow_followups:
                fu = self._followup(unknown, text, f"contradicts {contradiction.id}")
                result["followup"] = fu.id
            result["repeats"] = marks["repeats"]
            return result

        if weak:
            unknown.state = UnknownState.CONFLICTED
            result["state"] = str(unknown.state)
            if self.config.allow_followups:
                fu = self._followup(unknown, text, "answer confidence below 0.5")
                result["followup"] = fu.id
            result["repeats"] = marks["repeats"]
            return result

        if uncertain:
            # does not settle the unknown; leave state open
            if self.config.allow_followups:
                fu = self._followup(unknown, text or "(empty)", "answer is uncertain")
                result["followup"] = fu.id
            result["repeats"] = marks["repeats"]
            return result

        unknown.state = UnknownState.KNOWN_FROM_USER
        unknown.provenance = unknown.provenance or "user answer (questioning session)"
        result["state"] = str(unknown.state)
        result["repeats"] = marks["repeats"]
        return result

    def _contradiction(self, unknown: Unknown, text: str) -> Unknown | None:
        want = _norm_key(text)
        for other in self.unknowns:
            if other.id == unknown.id or other.id.startswith(f"{unknown.id}:fu:"):
                continue
            if other.variable and other.variable == unknown.variable:
                for a in self.answers:
                    same = a["id"] == other.id
                    given = _norm_key(str(a.get("answer") or ""))
                    if same and given not in ("", want):
                        return other
        return None

    # ------------------------------------------------------------- selection

    def ask_next(self) -> Presentation | None:
        """Present the next question, or stop with an honest reason.

        Returns None when nothing more may be presented. ``stop_reason`` is
        then one of: 'complete', 'early-stopped', 'budget-exhausted',
        'blocked', 'no-questions-remaining'. None of these except
        'complete'/'early-stopped' imply success.
        """
        if self.stop_reason is not None:
            return None

        candidates = next_batch(self.unknowns, asked=set(self.asked_keys), batch_size=5)
        # Defensive de-duplication: a duplicate must never be presented to
        # consume or refill the budget.
        asked = set(self.asked_keys)
        filtered = [c for c in candidates if c.question_key not in asked]
        self.repeats_refused += len(candidates) - len(filtered)
        candidates = filtered
        if not candidates:
            status = elicitation_status(
                self.unknowns, verification_defined=self.verification_defined
            )
            if status.complete:
                if self.config.stop_early and self.remaining > 0:
                    self.stop_reason = "early-stopped"
                    self.stop_detail = (
                        "completion criteria satisfied: no blocking unknowns, no "
                        "unresolved conflicts, verification defined — remaining "
                        "budget need not be spent"
                    )
                else:
                    self.stop_reason = "complete"
                    self.stop_detail = (
                        "completion criteria satisfied (no blocking unknowns, no "
                        "unresolved conflicts, verification defined)"
                    )
            elif not status.blocking and not status.unresolved_conflicts:
                # Nothing askable, no conflicts, but completion criteria are NOT
                # met (e.g. verification is not defined): honest, not success.
                self.stop_reason = "no-questions-remaining"
                self.stop_detail = (
                    "no further questions are askable but completion criteria are "
                    "not met (verification defined: "
                    f"{'yes' if status.verification_defined else 'no'}) — this is "
                    "not a success claim"
                )
            else:
                self.stop_reason = "blocked"
                self.stop_detail = (
                    "questions remain but none can be asked now — blocking: "
                    + (", ".join(status.blocking) or "(none recorded)")
                )
            return None

        if self.exhausted:
            self.stop_reason = "budget-exhausted"
            self.stop_detail = (
                f"the question budget of {self.config.question_budget} is spent "
                f"with questions still to ask; unresolved questions remain "
                f"unresolved (exhaustion is not success)"
            )
            return None

        unknown = candidates[0]
        key = unknown.question_key
        self.presented += 1
        self.asked_keys.append(key)
        marks = mark_asked(self.unknowns, [unknown.question])
        self.repeats_refused += marks.get("repeats", 0)
        if unknown.id.split(":")[-1].startswith("fu-") or ":fu:" in unknown.id:
            self.followups_asked += 1
        return Presentation(
            id=unknown.id,
            question=unknown.question,
            why=unknown.why_it_matters,
            index=self.presented,
            remaining_after=self.remaining,
            kind="follow-up" if ":fu:" in unknown.id else "original",
        )

    # ------------------------------------------------------------- reporting

    def outcome(self) -> str:
        if self.stop_reason in ("complete", "early-stopped"):
            return "succeeded"
        if self.stop_reason == "budget-exhausted":
            return "budget exhausted (not success)"
        if self.stop_reason in ("blocked", "no-questions-remaining"):
            return "incomplete (not success)"
        return "in progress"

    def status_report(self) -> dict[str, Any]:
        status = elicitation_status(
            self.unknowns, verification_defined=self.verification_defined
        )
        return {
            "config": self.config.to_dict(),
            "presented": self.presented,
            "remaining": self.remaining,
            "followups_enabled": self.config.allow_followups,
            "followups_asked": self.followups_asked,
            "early_stopping": self.config.stop_early,
            "repeats_refused": self.repeats_refused,
            "stop_reason": self.stop_reason,
            "stop_detail": self.stop_detail,
            "outcome": self.outcome(),
            "complete": status.complete,
            "blocking": list(status.blocking),
            "unresolved_conflicts": list(status.unresolved_conflicts),
            "unresolved_questions": [
                u.id
                for u in self.unknowns
                if u.state in (UnknownState.UNKNOWN, UnknownState.CONFLICTED)
            ],
        }

    def questions_log(self) -> list[dict[str, Any]]:
        """Investigation-compatible question log ({id, question, why, answer, effect})."""
        answers_by_id = {a["id"]: a for a in self.answers}
        log = []
        for u in self.unknowns:
            a = answers_by_id.get(u.id)
            log.append(
                {
                    "id": u.id,
                    "question": u.question,
                    "why": u.why_it_matters,
                    "answer": (a or {}).get("answer", ""),
                    "effect": (
                        "recorded in questioning session"
                        if a
                        else "UNRESOLVED (affected conclusions are marked BLOCKED)"
                    ),
                }
            )
        return log

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SESSION_VERSION,
            "config": self.config.to_dict(),
            "presented": self.presented,
            "asked_keys": list(self.asked_keys),
            "answers": [dict(a) for a in self.answers],
            "followups_asked": self.followups_asked,
            "repeats_refused": self.repeats_refused,
            "verification_defined": self.verification_defined,
            "stop_reason": self.stop_reason,
            "stop_detail": self.stop_detail,
            "unknowns": [u.to_dict() for u in self.unknowns],
        }

    @classmethod
    def from_dict(cls, data: Any) -> QuestioningSession:
        """Strict loader: malformed state raises ValueError.

        A broken session file must never silently restore a full question
        budget; callers surface the error instead.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"session state must be a JSON object, got {type(data).__name__}"
            )
        version = data.get("version")
        if version != SESSION_VERSION:
            raise ValueError(
                f"unsupported session version: {version!r} — this build reads "
                f"version {SESSION_VERSION} only (no legacy session files exist; "
                f"refusing to guess)"
            )
        config = QuestionBudget.from_dict(data.get("config"))
        presented = data.get("presented")
        if (
            isinstance(presented, bool)
            or not isinstance(presented, int)
            or presented < 0
            or presented > config.question_budget
        ):
            raise ValueError(
                f"malformed session state: presented={presented!r} is not an "
                f"integer in 0..{config.question_budget} — refusing to restore "
                f"a question budget from it"
            )
        asked = data.get("asked_keys")
        if not isinstance(asked, list) or not all(isinstance(k, str) for k in asked):
            raise ValueError("malformed session state: asked_keys must be a list of strings")
        answers = data.get("answers")
        if not isinstance(answers, list) or not all(isinstance(a, dict) for a in answers):
            raise ValueError("malformed session state: answers must be a list of objects")
        raw_unknowns = data.get("unknowns")
        if not isinstance(raw_unknowns, list) or not all(isinstance(u, dict) for u in raw_unknowns):
            raise ValueError("malformed session state: unknowns must be a list of objects")
        stop_reason = data.get("stop_reason")
        if stop_reason is not None and not isinstance(stop_reason, str):
            raise ValueError("malformed session state: stop_reason must be a string or null")
        return cls(
            config=config,
            unknowns=[_unknown_from_dict(u) for u in raw_unknowns],
            presented=presented,
            asked_keys=list(asked),
            answers=[dict(a) for a in answers],
            followups_asked=int(data.get("followups_asked") or 0),
            repeats_refused=int(data.get("repeats_refused") or 0),
            verification_defined=bool(data.get("verification_defined")),
            stop_reason=stop_reason,
            stop_detail=str(data.get("stop_detail") or ""),
        )
