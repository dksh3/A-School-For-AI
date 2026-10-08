"""Candidate detection and deterministic value scoring (1A-2Z Phase 1).

The common path: experience -> cheap heuristics -> reject. Only candidates
scoring above the configurable threshold ever reach a model. Reuses
core.routing.v26.experience.is_promotable as the first gate so trivial
actions ("Opened a file") never become candidates.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from core.routing.v26.experience import Experience, ExperienceOutcome, is_promotable

# ---------------------------------------------------------------------------
# Config (env-overridable; see budget.py for model-call budget)
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


MIN_CANDIDATE_SCORE = _env_float("SCHOOL_SKILLGEN_MIN_SCORE", 0.45)
MIN_NOVELTY = _env_float("SCHOOL_SKILLGEN_MIN_NOVELTY", 0.15)
MIN_IMPACT = _env_float("SCHOOL_SKILLGEN_MIN_IMPACT", 0.0)

# Trivial experiences that must never become skills (explicit examples).
_TRIVIAL_PATTERNS = (
    r"^opened?\s+(a|the)\s+\w+$",
    r"^read\s+(a|the)\s+\w+$",
    r"^listed?\s+(the\s+)?\w+\s*(files?)?$",
    r"^(clicked|tapped|scrolled|viewed|looked at)\b.*$",
    r"^(hi|hello|ok|okay|thanks|thank you)[.!]?$",
    r"^wrote\s+(a\s+)?(hello|test)\s*world",
    r"^ran\s+(the\s+)?(ls|dir|pwd|whoami)\b",
)

_RECURRENCE_HINTS = (
    "recurring", "every time", "whenever", "each time", "workflow",
    "step by step", "steps:", "procedure", "always fails", "again and again",
    "routine", "playbook", "checklist",
)
_SOLUTION_HINTS = ("diagnos", "fix", "resolv", "workaround", "root cause",
                   "reliable", "bypass", "avoided", "prevented", "migrat")
_EFFICIENCY_HINTS = ("faster", "shortcut", "saved", "reduced", "optimi",
                     "skipped", "cached", "one-shot", "batch")
_POSITIVE_FEEDBACK = ("great", "perfect", "exactly", "works", "nice",
                      "excellent", "correct", "good job", "yes", "✅")

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(slots=True)
class Candidate:
    """A detected skill candidate with its deterministic score."""

    experience: Experience
    score: float
    signals: dict[str, bool] = field(default_factory=dict)
    factors: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    novelty: float = 1.0
    merge_hint: str = ""

    @property
    def experience_id(self) -> str:
        return self.experience.experience_id


def detect_trivial(text: str) -> bool:
    """True when the experience describes a trivial action."""
    norm = " ".join(text.lower().split())
    if len(norm) < 40 and not any(
        h in norm for h in _SOLUTION_HINTS + _RECURRENCE_HINTS
    ):
        # Very short + no procedure/solution vocabulary = trivial.
        return True
    return any(re.match(pat, norm) for pat in _TRIVIAL_PATTERNS)


def _has_any(text: str, hints: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(h in low for h in hints)


def extract_signals(experience: Experience) -> dict[str, bool]:
    """Cheap deterministic signals for an experience."""
    content = f"{experience.observation} {experience.action}".strip()
    feedback = experience.feedback.lower()
    meta = {str(k).lower() for k in experience.metadata}
    tags = {t.lower() for t in experience.tags}
    success = experience.outcome == ExperienceOutcome.SUCCESS
    return {
        "success": success,
        "non_trivial": not detect_trivial(content),
        "solution": _has_any(content, _SOLUTION_HINTS)
        or bool({"solution", "fix", "resolved"} & tags)
        or "solution" in meta,
        "recurrence": _has_any(content, _RECURRENCE_HINTS),
        "positive_feedback": bool(feedback)
        and any(p in feedback for p in _POSITIVE_FEEDBACK),
        "efficiency": _has_any(content, _EFFICIENCY_HINTS)
        or bool({"tokens_saved", "tool_calls_reduced"} & meta),
        "error_avoided": ("avoided" in content or "prevented" in content
                          and "error" in content) or "avoided_error" in meta,
        "previously_unresolved": "previously_unresolved" in meta
        or "was failing" in content.lower() or "used to fail" in content.lower(),
        "reused": bool(int(_meta_int(experience, "reuse_count")) >= 2),
        "user_positive": "positive" in meta or "user_feedback" in meta,
    }


def _meta_int(experience: Experience, key: str) -> int:
    for k, v in experience.metadata.items():
        if str(k).lower() == key:
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0
    return 0


def score_candidate(
    experience: Experience,
    signals: dict[str, bool],
    novelty: float = 1.0,
) -> tuple[float, dict[str, float], list[str]]:
    """Deterministic value score in [0, 1].

    Weights: usefulness 0.30, repeatability 0.25, novelty 0.15,
    impact 0.15, reliability 0.15. Configurable thresholds gate the
    model call in pipeline.py; weights stay fixed in Phase 1.
    """
    usefulness = (
        0.5
        + (0.2 if signals["success"] else 0.0)
        + (0.15 if signals["positive_feedback"] or signals["user_positive"] else 0.0)
        + (0.15 if signals["solution"] else 0.0)
    )
    repeatability = (
        (0.6 if signals["recurrence"] else 0.0)
        + (0.3 if signals["previously_unresolved"] or signals["error_avoided"] else 0.0)
        + (0.1 if signals["efficiency"] else 0.0)
        + (0.2 if signals["reused"] else 0.0)
    )
    repeatability = min(repeatability, 1.0)
    impact = min(
        1.0,
        (0.4 if signals["efficiency"] else 0.0)
        + (0.3 if signals["error_avoided"] else 0.0)
        + (0.3 if signals["previously_unresolved"] else 0.0),
    )
    reliability = experience.confidence
    factors = {
        "usefulness": round(min(usefulness, 1.0), 4),
        "repeatability": round(repeatability, 4),
        "novelty": round(max(0.0, min(novelty, 1.0)), 4),
        "impact": round(impact, 4),
        "reliability": round(reliability, 4),
    }
    score = (
        0.30 * factors["usefulness"]
        + 0.25 * factors["repeatability"]
        + 0.15 * factors["novelty"]
        + 0.15 * factors["impact"]
        + 0.15 * factors["reliability"]
    )
    reasons = [k for k, v in factors.items() if v > 0.5]
    return round(score, 4), factors, reasons


def detect(
    experience: Experience,
    existing_similarity: float = 0.0,
    existing_merge_hint: str = "",
) -> Candidate | None:
    """Full deterministic gate: promotable -> non-trivial -> scored.

    Returns None when the experience must not consume a model call.
    """
    ok, _reason = is_promotable(experience)
    if not ok:
        return None
    content = f"{experience.observation} {experience.action}".strip()
    if detect_trivial(content):
        return None
    signals = extract_signals(experience)
    novelty = max(0.0, 1.0 - existing_similarity)
    score, factors, reasons = score_candidate(experience, signals, novelty)
    if novelty < MIN_NOVELTY and existing_merge_hint:
        # Near-duplicate of an existing skill: still a candidate, but routed
        # to the duplicate/merge path with a smaller score contribution.
        reasons.append(f"merge_hint:{existing_merge_hint}")
    return Candidate(
        experience=experience,
        score=score,
        signals=signals,
        factors=factors,
        reasons=reasons,
        novelty=novelty,
        merge_hint=existing_merge_hint,
    )


def to_report(candidate: Candidate) -> dict[str, Any]:
    """JSON-safe candidate report (for tool output / observability)."""
    return {
        "experience_id": candidate.experience_id,
        "candidate": True,
        "score": candidate.score,
        "novelty": candidate.novelty,
        "signals": dict(candidate.signals),
        "factors": dict(candidate.factors),
        "reasons": list(candidate.reasons),
        "merge_hint": candidate.merge_hint,
    }
