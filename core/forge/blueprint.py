"""Blueprint builder — the Forge design-spec artifact.

``build_blueprint(interview, title=None, **overrides) -> Blueprint`` derives a
senior-architect design spec from a discovery ``Interview``: goal, problem,
proposed solution, non-goals, constraints, assumptions, success metrics,
risks, open questions, glossary, a top-level work-breakdown decomposition and
full question → section traceability.

Universal by design: the spec adapts to any ``Domain``. A writing project, a
business plan and a research study get the same rigor as a codebase — the
domain label simply changes the framing.

Fail-open: every public boundary catches ``Exception`` and returns a safe
(possibly empty) ``Blueprint``. This module never raises.

Shared helpers
--------------
This module also hosts the small fail-open extraction helpers reused by
``edict.py``, ``weave.py`` and ``compass.py`` (``collect_answers``,
``by_dimension``, ``answer_texts``, ``clean_item``, ``split_items``,
``domain_label``, ``default_phases``, ``match_any``, ``parse_minutes``) so
every artifact reads the interview through exactly the same lens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.forge.models import (
    Blueprint,
    Domain,
    Interview,
    _safe_float,
    _safe_int,
    _safe_list,
    _safe_str,
    _slug,
)

__all__ = [
    "AnswerRec",
    "answer_texts",
    "by_dimension",
    "build_blueprint",
    "clean_item",
    "collect_answers",
    "default_phases",
    "domain_label",
    "is_exclusion",
    "match_any",
    "parse_minutes",
    "split_items",
]

# --- shared extraction helpers ---------------------------------------------

#: Default phase plans per domain. Every plan ends with verification and
#: delivery because every kind of work has both.
_DOMAIN_PHASES: dict[str, tuple[str, ...]] = {
    "coding": ("Plan", "Implement", "Test", "Ship"),
    "writing": ("Outline", "Draft", "Revise", "Publish"),
    "research": ("Design", "Collect", "Analyze", "Report"),
    "business": ("Plan", "Execute", "Measure", "Review"),
    "planning": ("Define", "Organize", "Execute", "Review"),
    "education": ("Plan", "Teach", "Practice", "Assess"),
    "creative": ("Explore", "Create", "Refine", "Release"),
    "ops": ("Prepare", "Deploy", "Monitor", "Harden"),
    "data": ("Ingest", "Model", "Validate", "Deliver"),
    "life": ("Plan", "Act", "Review", "Sustain"),
    "general": ("Prepare", "Execute", "Verify", "Deliver"),
}

_VERIFY_RE = re.compile(r"verif|test|valid|qa|check|review|revis|assess|audit", re.I)
_DELIVER_RE = re.compile(r"ship|deliver|publish|launch|release|finish|complete|hand-?off", re.I)

#: "N unit" effort hints embedded in answers, e.g. "(30 minutes)", "2 hours".
_EFFORT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(days?|weeks?|hours?|hrs?|minutes?|mins?)\b",
    re.I,
)
_EFFORT_MINUTES = {"day": 480, "week": 2400, "hour": 60, "hr": 60, "minute": 1, "min": 1}

_BULLET_RE = re.compile(r"^\s*(?:[-*+>\u2022\u25cf]|\d+[.)])\s+")


@dataclass(frozen=True)
class AnswerRec:
    """One cleaned answer fragment with its provenance."""

    question_id: str
    dimension: str
    text: str
    confidence: float

    @property
    def search(self) -> str:
        """Lower-cased haystack used for keyword matching."""
        return f"{self.question_id} {self.text}".lower()


def clean_item(text: Any) -> str:
    """Coerce one answer fragment to clean single-line text. Never raises."""
    try:
        s = _safe_str(text).strip()
        s = _BULLET_RE.sub("", s)
        s = re.sub(r"\s+", " ", s)
        return s[:300]
    except Exception:  # noqa: BLE001
        return ""


def split_items(value: Any) -> list[str]:
    """Flatten an answer value into clean items. Never raises."""
    out: list[str] = []
    try:
        if isinstance(value, (list, tuple, set)):
            raw_items: list[Any] = list(value)
        elif isinstance(value, dict):
            raw_items = [f"{_safe_str(k)}: {_safe_str(v)}" for k, v in value.items()]
        elif isinstance(value, str):
            raw_items = re.split(r"[\n\r;|]+|\u2022", value)
        else:
            raw_items = [value]
        for item in raw_items:
            t = clean_item(item)
            if t:
                out.append(t)
    except Exception:  # noqa: BLE001
        return out
    return out


def _infer_dimension(question_id: str) -> str:
    """Guess a dimension from a question id. Falls back to ``extra``."""
    try:
        norm = re.sub(r"[^a-z0-9]+", "-", _safe_str(question_id).lower())
        padded = f"-{norm}-"
        for dim in (
            "intent", "audience", "scope", "constraints", "success", "resources",
            "risks", "sequence", "style", "edge_cases", "glossary", "open_questions",
        ):
            d = dim.replace("_", "-")
            if norm == d or norm.startswith(f"{d}-") or f"-{d}-" in padded:
                return dim
    except Exception:  # noqa: BLE001
        return "extra"
    return "extra"


def collect_answers(interview: Any) -> list[AnswerRec]:
    """Flatten an interview's answers into clean, dimension-tagged records.

    Never raises: hostile questions, answers and values are skipped or
    coerced to empty strings.
    """
    out: list[AnswerRec] = []
    try:
        qmap: dict[str, Any] = {}
        for q in _safe_list(getattr(interview, "questions", [])):
            try:
                qid = _safe_str(getattr(q, "id", ""))
                if qid:
                    qmap[qid] = q
                for f in _safe_list(getattr(q, "followups", [])):
                    fid = _safe_str(getattr(f, "id", ""))
                    if fid:
                        qmap[fid] = f
            except Exception:  # noqa: BLE001
                continue
        for a in _safe_list(getattr(interview, "answers", [])):
            try:
                qid = _safe_str(getattr(a, "question_id", ""))
                q = qmap.get(qid)
                dim = ""
                if q is not None:
                    dim = _safe_str(getattr(q, "dimension", ""))
                if not dim:
                    dim = _infer_dimension(qid)
                conf = max(0.0, min(1.0, _safe_float(getattr(a, "confidence", 1.0), 1.0)))
                for text in split_items(getattr(a, "value", "")):
                    out.append(AnswerRec(qid, dim, text, conf))
                    if len(out) >= 200:  # hard cap keeps hostile input cheap
                        return out
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return out
    return out


def by_dimension(answers: list[AnswerRec]) -> dict[str, list[AnswerRec]]:
    """Group answer records by dimension. Never raises."""
    out: dict[str, list[AnswerRec]] = {}
    try:
        for a in answers or []:
            try:
                out.setdefault(_safe_str(a.dimension) or "extra", []).append(a)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return out
    return out


def answer_texts(buckets: dict[str, list[AnswerRec]], dimension: str) -> list[str]:
    """Clean text items for one dimension, de-duplicated in order."""
    out: list[str] = []
    try:
        for a in buckets.get(_safe_str(dimension), []) or []:
            t = _safe_str(getattr(a, "text", ""))
            if t and t not in out:
                out.append(t)
    except Exception:  # noqa: BLE001
        return out
    return out


def match_any(text: Any, words: tuple[str, ...]) -> bool:
    """True when any keyword appears in the safe-lowered text. Never raises."""
    try:
        s = _safe_str(text).lower()
        return any(w in s for w in words)
    except Exception:  # noqa: BLE001
        return False


def is_exclusion(text: Any) -> bool:
    """True when an item phrases an exclusion ("out of scope", "won't", …)."""
    try:
        return match_any(text, _EXCLUSION_WORDS)
    except Exception:  # noqa: BLE001
        return False


def domain_label(domain: Any) -> str:
    """Human label for a domain, e.g. ``"Writing"``. Never fails."""
    try:
        d = domain if isinstance(domain, Domain) else Domain.coerce(domain)
        return d.value.capitalize()
    except Exception:  # noqa: BLE001
        return "General"


def default_phases(domain: Any) -> list[str]:
    """Universal default phase plan for a domain. Never raises."""
    try:
        d = domain if isinstance(domain, Domain) else Domain.coerce(domain)
        return list(_DOMAIN_PHASES.get(d.value, _DOMAIN_PHASES["general"]))
    except Exception:  # noqa: BLE001
        return list(_DOMAIN_PHASES["general"])


def parse_minutes(text: Any, default: int = 45) -> int:
    """Extract an effort estimate ("30 minutes", "2 hours") from text.

    Falls back to *default* and never raises.
    """
    try:
        s = _safe_str(text)
        m = _EFFORT_RE.search(s)
        if m:
            amount = _safe_float(m.group(1), 0.0)
            unit = m.group(2).lower().rstrip("s") or "minute"
            minutes = amount * _EFFORT_MINUTES.get(unit, 1)
            if 0 < minutes <= 100000:
                return int(minutes)
        return max(1, _safe_int(default, 45))
    except Exception:  # noqa: BLE001
        return max(1, _safe_int(default, 45))


def dedupe(items: list[str]) -> list[str]:
    """De-duplicate a list of strings preserving first-seen order."""
    out: list[str] = []
    try:
        for t in items or []:
            s = _safe_str(t)
            if s and s not in out:
                out.append(s)
    except Exception:  # noqa: BLE001
        return out
    return out


# --- blueprint derivation ---------------------------------------------------

_GOAL_WORDS = (
    "goal", "objective", "outcome", "aim", "want", "need", "deliver",
    "achieve", "success", "hope", "vision",
)
_PROBLEM_WORDS = (
    "problem", "pain", "issue", "why", "currently", "gap", "struggle",
    "fail", "lack", "miss", "frustrat", "broken", "slow",
)
_EXCLUSION_WORDS = (
    "out of scope", "not in scope", "non-goal", "non goal", "exclude",
    "excluding", "won't", "will not", "don't", "do not", "not part",
    "beyond", "later", "future", "defer", "skip", "explicitly not",
)
_EXCLUSION_PREFIX_RE = re.compile(
    r"^(out of scope|not in scope|non-goal|non goal|excluded?|not)\s*[:\-]?\s*",
    re.I,
)
_TERM_RE = re.compile(r"^\s*([^:=]{1,60}?)\s*[:=]\s*(.+)$")


def _pick(answers: list[AnswerRec], words: tuple[str, ...]) -> AnswerRec | None:
    try:
        for a in answers or []:
            if match_any(getattr(a, "search", ""), words):
                return a
    except Exception:  # noqa: BLE001
        return None
    return None


def _short(text: str, limit: int = 60) -> str:
    s = _safe_str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 3].rsplit(" ", 1)[0] + "..."


def _impact(text: str) -> str:
    if match_any(text, (
        "data loss", "security", "breach", "legal", "privacy", "outage",
        "crash", "cancel", "blocker", "blocked", "deadline", "over budget",
    )):
        return "high"
    if match_any(text, ("delay", "slow", "minor", "cosmetic", "nice to have")):
        return "low"
    return "medium"


def _mitigation(text: str) -> str:
    if match_any(text, ("deadline", "time", "schedule", "delay", "late", "slip")):
        return "Protect the schedule: checkpoint early and cut scope before quality."
    if match_any(text, ("cost", "budget", "money", "spend", "price")):
        return "Track spend against the budget weekly; cap discretionary cost."
    if match_any(text, ("people", "team", "contributor", "resource", "staff", "avail")):
        return "Line up backup capacity before work starts; document hand-offs."
    if match_any(text, ("quality", "error", "mistake", "accuracy", "wrong", "bug")):
        return "Add a verification gate before delivery; review risky items first."
    if match_any(text, ("scope", "creep")):
        return "Hold the non-goals list as the scope boundary; backlog new asks."
    return "Track at every phase gate and assign an owner before work starts."


def build_blueprint(
    interview: Interview,
    title: str | None = None,
    **overrides: Any,
) -> Blueprint:
    """Build the design-spec ``Blueprint`` from a discovery interview.

    Dimension → field mapping: ``intent`` → goal/problem, ``scope`` → proposed
    + decomposition (+ non-goals from exclusion phrasing), ``constraints`` →
    constraints, ``resources`` → assumptions, ``success`` → success metrics,
    ``risks`` → risks, ``open_questions`` → open questions, ``glossary`` →
    glossary.  Every answer is recorded in ``traceability``.

    ``overrides`` may set any ``Blueprint`` field explicitly (e.g.
    ``goal="..."``, ``constraints=[...]``); unknown keys are ignored.

    FAIL-OPEN: never raises; returns a safe (possibly empty) Blueprint.
    """
    try:
        return _build_blueprint_impl(interview, title, overrides)
    except Exception:  # noqa: BLE001
        try:
            return Blueprint(title=_safe_str(title))
        except Exception:  # noqa: BLE001
            return Blueprint()


def _build_blueprint_impl(
    interview: Any,
    title: Any,
    overrides: dict[str, Any],
) -> Blueprint:
    bp = Blueprint()
    try:
        dom = Domain.coerce(getattr(interview, "domain", Domain.GENERAL))
    except Exception:  # noqa: BLE001
        dom = Domain.GENERAL
    answers = collect_answers(interview)
    bydim = by_dimension(answers)

    # where each question's answer landed in the spec
    landings: dict[str, set[str]] = {}
    excerpt: dict[str, str] = {}
    qdim: dict[str, str] = {}

    def mark(recs: list[AnswerRec] | list[Any], section: str) -> None:
        try:
            for a in recs:
                qid = _safe_str(getattr(a, "question_id", ""))
                landings.setdefault(qid, set()).add(section)
                excerpt.setdefault(qid, _short(_safe_str(getattr(a, "text", "")), 80))
                qdim.setdefault(qid, _safe_str(getattr(a, "dimension", "")))
        except Exception:  # noqa: BLE001
            return

    # -- core narrative --------------------------------------------------
    intent = bydim.get("intent", [])
    goal_ans = _pick(intent, _GOAL_WORDS) or (intent[0] if intent else None)
    problem_ans = _pick(answers, _PROBLEM_WORDS)
    if problem_ans is not None and goal_ans is not None and (
            problem_ans.question_id == goal_ans.question_id
            and problem_ans.text == goal_ans.text):
        problem_ans = None

    bp.title = _safe_str(title) or _safe_str(getattr(interview, "title", "")) \
        or f"{domain_label(dom)} Blueprint"
    bp.domain = dom
    bp.slug = _safe_str(getattr(interview, "slug", "")) or _slug(bp.title)

    bp.goal = _safe_str(getattr(goal_ans, "text", "")) if goal_ans else ""
    if goal_ans is not None:
        mark([goal_ans], "goal")
    bp.problem = _safe_str(getattr(problem_ans, "text", "")) if problem_ans else ""
    if problem_ans is not None:
        mark([problem_ans], "problem")
    if not bp.problem and bp.goal:
        bp.problem = f"The gap this blueprint closes: {bp.goal}"

    # -- scope: proposed + decomposition + non-goals ----------------------
    scope = bydim.get("scope", [])
    in_scope = [a for a in scope if not is_exclusion(getattr(a, "search", ""))]
    out_scope = [a for a in scope if is_exclusion(getattr(a, "search", ""))]
    seq = bydim.get("sequence", [])

    audience = bydim.get("audience", [])
    mark(audience, "compass.scenarios")
    who = _short(audience[0].text, 60) if audience else ""
    target = f" to {who}" if who else ""

    if in_scope:
        mark(in_scope, "proposed")
        mark(in_scope, "decomposition")
        bp.proposed = f"Deliver the following{target}: " + \
            "; ".join(_safe_str(a.text) for a in in_scope[:6]) + "."
        breakdown_src = in_scope
    elif seq:
        mark(seq, "proposed")
        bp.proposed = f"Execute the staged effort{target}: " + \
            "; ".join(_safe_str(a.text) for a in seq[:6]) + "."
        breakdown_src = seq
    else:
        bp.proposed = f"A staged {domain_label(dom).lower()} effort{target}" + \
            (f" to {bp.goal.rstrip('.')}." if bp.goal else ".")
        breakdown_src = []

    for i, a in enumerate(breakdown_src[:12], start=1):
        try:
            bp.decomposition.append({
                "id": f"wb-{i:02d}",
                "title": _short(_safe_str(a.text), 60),
                "detail": _safe_str(a.text),
                "source": _safe_str(a.question_id),
                "order": i,
                "children": [],
            })
        except Exception:  # noqa: BLE001
            continue

    mark(out_scope, "non_goals")
    for a in out_scope[:12]:
        t = _safe_str(a.text)
        cleaned = _EXCLUSION_PREFIX_RE.sub("", t)
        bp.non_goals.append(cleaned or t)

    # -- constraint / assumption / metric surfaces -----------------------
    constraints = bydim.get("constraints", [])
    mark(constraints, "constraints")
    bp.constraints = [_safe_str(a.text) for a in constraints[:20]]

    resources = bydim.get("resources", [])
    mark(resources, "assumptions")
    bp.assumptions = [f"Available: {_safe_str(a.text)}" for a in resources[:12]]
    for a in answers:
        try:
            if a.confidence < 0.55:
                mark([a], "assumptions")
                bp.assumptions.append(f"Needs confirmation: {_safe_str(a.text)}")
        except Exception:  # noqa: BLE001
            continue
    bp.assumptions = dedupe(bp.assumptions)[:20]

    success = bydim.get("success", [])
    mark(success, "success_metrics")
    bp.success_metrics = [_safe_str(a.text) for a in success[:20]]

    risk_recs = bydim.get("risks", [])
    mark(risk_recs, "risks")
    for a in risk_recs[:12]:
        try:
            bp.risks.append({
                "risk": _safe_str(a.text),
                "impact": _impact(_safe_str(a.text)),
                "mitigation": _mitigation(_safe_str(a.text)),
                "source": _safe_str(a.question_id),
            })
        except Exception:  # noqa: BLE001
            continue

    # -- open questions --------------------------------------------------
    open_recs = bydim.get("open_questions", [])
    mark(open_recs, "open_questions")
    oq = [_safe_str(a.text) for a in open_recs[:20]]
    for extra in _safe_list(getattr(interview, "open_questions", [])):
        try:
            t = clean_item(extra)
            if t:
                qid = "(session)"
                landings.setdefault(qid, set()).add("open_questions")
                excerpt.setdefault(qid, _short(t, 80))
                qdim.setdefault(qid, "open_questions")
                oq.append(t)
        except Exception:  # noqa: BLE001
            continue
    bp.open_questions = dedupe(oq)[:20]

    # -- glossary --------------------------------------------------------
    try:
        raw_gloss = getattr(interview, "glossary", {})
        if isinstance(raw_gloss, dict):
            for k, v in raw_gloss.items():
                term = clean_item(k)
                if term:
                    bp.glossary[term] = _safe_str(v)
                    landings.setdefault("(glossary)", set()).add("glossary")
                    excerpt.setdefault("(glossary)", _short(term, 80))
                    qdim.setdefault("(glossary)", "glossary")
    except Exception:  # noqa: BLE001
        pass
    for a in bydim.get("glossary", [])[:20]:
        mark([a], "glossary")
        m = _TERM_RE.match(_safe_str(a.text))
        if m:
            term = clean_item(m.group(1))
            if term:
                bp.glossary[term] = clean_item(m.group(2))
        else:
            term = clean_item(a.text)
            if term:
                bp.glossary.setdefault(term, "")

    # -- traceability: question_id → where it landed ---------------------
    # answers consumed by companion artifacts get honest cross-references
    mark(bydim.get("sequence", []), "edict.phases")
    mark(bydim.get("style", []), "edict.directives")
    mark(bydim.get("edge_cases", []), "edict.directives")
    for a in answers:
        try:
            qid = _safe_str(a.question_id)
            if qid and qid not in excerpt:
                excerpt[qid] = _short(_safe_str(a.text), 80)
                qdim.setdefault(qid, _safe_str(a.dimension))
        except Exception:  # noqa: BLE001
            continue
    for qid in sorted(set(landings) | set(excerpt)):
        sections = sorted(landings.get(qid, set())) or ["context"]
        for section in sections:
            try:
                bp.traceability.append({
                    "question_id": qid,
                    "dimension": qdim.get(qid, ""),
                    "lands_in": section,
                    "excerpt": excerpt.get(qid, ""),
                })
            except Exception:  # noqa: BLE001
                continue

    _apply_overrides(bp, overrides)
    return bp


_STR_FIELDS = ("title", "goal", "problem", "proposed", "slug")
_LIST_FIELDS = (
    "non_goals", "constraints", "assumptions", "success_metrics", "open_questions",
)
_ROW_FIELDS = ("risks", "decomposition", "traceability")


def _apply_overrides(bp: Blueprint, overrides: dict[str, Any]) -> None:
    """Apply explicit caller overrides onto the derived blueprint. Never raises."""
    try:
        for key, value in (overrides or {}).items():
            try:
                k = _safe_str(key)
                if k in _STR_FIELDS:
                    s = _safe_str(value)
                    if s:
                        setattr(bp, k, s)
                elif k == "domain":
                    bp.domain = Domain.coerce(value)
                elif k in _LIST_FIELDS:
                    items = split_items(value)
                    if items:
                        setattr(bp, k, items[:20])
                elif k == "glossary":
                    if isinstance(value, dict):
                        for term, defn in value.items():
                            t = clean_item(term)
                            if t:
                                bp.glossary[t] = clean_item(defn)
                elif k in _ROW_FIELDS:
                    rows = [r for r in _safe_list(value) if isinstance(r, dict)]
                    if rows:
                        setattr(bp, k, rows[:20])
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return
