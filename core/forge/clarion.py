"""clarion — the discovery-interview engine for Forge.

Gathers intent for any kind of work through an adaptive, scored interview and
supports four modes:

- ``INTERVIEW`` — one question per turn, always probing the weakest dimension
- ``BATCH``     — fill a whole form at once
- ``AUTO``      — infer sensible answers, park the rest as open questions
- ``IMPORT``    — seed answers from an existing document, interview the gaps

Every dimension (intent, audience, scope, constraints, success, resources,
risks, sequence, style, edge_cases, glossary, open_questions) carries a score
in ``Interview.dimension_scores``. ``next_question`` always returns the next
un-answered question in the weakest dimension until coverage is high enough
and every required question is answered.

Followup branching convention (set by the banks in ``core.forge.domains``): a
followup ``Question`` whose ``domain_hint`` starts with ``when:`` fires only
when the parent answer matches a trigger — ``when:Yes``,
``when:Option A|Option B``, or ``when:*`` for always. Surfaced followups are
asked before anything else.

Hard rule: every public function is fail-open. Hostile input — ``None``,
ints, dicts, objects whose ``__str__``/``__bool__``/``__hash__`` raise —
returns a safe default and never raises.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from core.forge.domains import get_questionbank
from core.forge.models import (
    _DIMENSIONS,
    Domain,
    Interview,
    InterviewMode,
    Question,
    QuestionType,
    RequirementAnswer,
)

#: Starting score for every dimension before any answer lands.
DEFAULT_DIMENSION_SCORE = 0.5

#: Coverage at which the interview is confident enough to stop asking.
DONE_COVERAGE = 0.85

#: Followup trigger marker inside a question's ``domain_hint``.
WHEN_PREFIX = "when:"

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset({
    "what", "when", "where", "which", "while", "should", "would", "could",
    "about", "there", "their", "them", "they", "this", "that", "these",
    "those", "have", "does", "done", "like", "look", "must", "with",
    "from", "into", "your", "yourself", "will", "want", "some", "than",
    "then", "been", "were", "just", "more", "most",
})


# --- fail-open coercion helpers --------------------------------------------

def _safe_str(v: Any, default: str = "") -> str:
    """Coerce ``v`` to a clean str. Never raises."""
    try:
        if v is None:
            return default
        s = v if isinstance(v, str) else str(v)
        return s.encode("utf-8", "replace").decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    """Coerce ``v`` to a finite float. Never raises."""
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return default
        return f
    except Exception:  # noqa: BLE001
        return default


def _safe_bool(v: Any, default: bool = False) -> bool:
    """Coerce ``v`` to bool. Never raises (hostile ``__bool__`` included)."""
    try:
        return bool(v)
    except Exception:  # noqa: BLE001
        return default


def _clamp01(v: Any, default: float = 0.0) -> float:
    """Clamp ``v`` into [0, 1]. Never raises."""
    return max(0.0, min(1.0, _safe_float(v, default)))


def _coerce_mode(mode: Any) -> InterviewMode:
    """Coerce ``mode`` to an InterviewMode, defaulting to INTERVIEW."""
    try:
        if isinstance(mode, InterviewMode):
            return mode
        s = _safe_str(mode).lower().strip()
        for m in InterviewMode:
            if m.value == s:
                return m
    except Exception:  # noqa: BLE001
        return InterviewMode.INTERVIEW
    return InterviewMode.INTERVIEW


def _metric(fn: Callable[[], Any], default: Any) -> Any:
    """Run ``fn``; on any failure return ``default``. Never raises."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


# --- small safe accessors ---------------------------------------------------

def _qfield(q: Any, name: str, default: Any = "") -> Any:
    """Read a question attribute defensively. Never raises."""
    try:
        return getattr(q, name, default)
    except Exception:  # noqa: BLE001
        return default


def _iter_items(raw: Any) -> list[Any]:
    """Return ``raw`` as a list if iterable-ish, else []. Never raises."""
    try:
        return list(raw) if isinstance(raw, (list, tuple)) else []
    except Exception:  # noqa: BLE001
        return []


def _question_type(q: Any) -> QuestionType:
    """Best-effort QuestionType of ``q``. Never raises."""
    raw = _qfield(q, "type", QuestionType.TEXT)
    if isinstance(raw, QuestionType):
        return raw
    try:
        return QuestionType(_safe_str(raw, "text"))
    except Exception:  # noqa: BLE001
        return QuestionType.TEXT


def _answer_map(interview: Any) -> dict[str, RequirementAnswer]:
    """Mapping of question-id -> answer. Never raises."""
    amap: dict[str, RequirementAnswer] = {}
    for a in _iter_items(_qfield(interview, "answers")):
        try:
            amap[_safe_str(_qfield(a, "question_id"))] = a
        except Exception:  # noqa: BLE001
            continue
    return amap


def _dim_score(interview: Any, dim: str) -> float:
    """Current score of one dimension, defaulting to DEFAULT_DIMENSION_SCORE."""
    try:
        scores = _qfield(interview, "dimension_scores", {})
        raw = scores.get(dim) if isinstance(scores, dict) else None
        return _clamp01(_safe_float(raw, DEFAULT_DIMENSION_SCORE),
                        DEFAULT_DIMENSION_SCORE)
    except Exception:  # noqa: BLE001
        return DEFAULT_DIMENSION_SCORE


def _coverage(interview: Any) -> float:
    """Fraction of dimensions answered, 0..1. Never raises."""
    try:
        return _clamp01(_safe_float(interview.coverage()))
    except Exception:  # noqa: BLE001
        return 0.0


def _is_followup(q: Any) -> bool:
    """True when ``q`` is an appended conditional followup."""
    return _safe_str(_qfield(q, "domain_hint")).strip().lower().startswith(WHEN_PREFIX)


def _triggers(q: Any) -> list[str]:
    """Trigger list from ``when:a|b`` hint. [] means the followup always fires."""
    hint = _safe_str(_qfield(q, "domain_hint")).strip()
    if not hint.lower().startswith(WHEN_PREFIX):
        return []
    spec = hint[len(WHEN_PREFIX):]
    return [t.strip().lower() for t in spec.split("|") if t.strip()]


def _matches(value: Any, triggers: list[str]) -> bool:
    """True when the answer value matches any trigger (substring, case-free)."""
    if "*" in triggers:
        return True
    haystack = _safe_str(value).lower()
    return any(t in haystack for t in triggers)


def _clean_value(value: Any) -> Any:
    """Sanitize an answer value to primitives. Never raises."""
    try:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple, set)):
            return [_safe_str(v) for v in value]
        if isinstance(value, dict):
            return {_safe_str(k): _safe_str(v) for k, v in value.items()}
        return _safe_str(value)
    except Exception:  # noqa: BLE001
        return _safe_str(value)


def _as_questions(raw: Any) -> list[Question]:
    """Convert Question-or-dict items into fresh Question copies."""
    out: list[Question] = []
    for item in _iter_items(raw):
        try:
            if isinstance(item, Question):
                out.append(Question.from_dict(item.to_dict()))
            elif isinstance(item, dict):
                out.append(Question.from_dict(item))
        except Exception:  # noqa: BLE001
            continue
    return out


def _assign_ids(questions: list[Question]) -> list[Question]:
    """Renumber questions to q1..qN and return fresh copies."""
    out: list[Question] = []
    for i, q in enumerate(questions):
        try:
            copy = Question.from_dict(q.to_dict())
            copy.id = f"q{i + 1}"
            out.append(copy)
        except Exception:  # noqa: BLE001
            continue
    return out


def _find_question(interview: Any, question_id: Any) -> Question | None:
    """Find a question by id. Never raises."""
    qid = _safe_str(question_id)
    for q in _iter_items(_qfield(interview, "questions")):
        try:
            if _safe_str(_qfield(q, "id")) == qid:
                return q if isinstance(q, Question) else None
        except Exception:  # noqa: BLE001
            continue
    return None


def _add_open(interview: Any, text: Any) -> None:
    """Append a de-duplicated open question. Never raises."""
    try:
        t = _safe_str(text).strip()
        if not t:
            return
        existing = {_safe_str(x) for x in _iter_items(_qfield(interview, "open_questions"))}
        if t in existing:
            return
        interview.open_questions.append(t)
    except Exception:  # noqa: BLE001
        return


def _bump_dimension(interview: Any, dim: Any, confidence: float) -> None:
    """Raise one dimension's score toward 1.0. Never raises."""
    try:
        key = _safe_str(dim, "intent") or "intent"
        current = _dim_score(interview, key)
        conf = max(0.25, _clamp01(confidence, 1.0))
        bumped = current + (1.0 - current) * 0.5 * conf
        interview.dimension_scores[key] = min(1.0, bumped)
    except Exception:  # noqa: BLE001
        return


# --- public engine ----------------------------------------------------------

def start_interview(
    title: Any = "",
    domain: Any = Domain.GENERAL,
    mode: Any = InterviewMode.INTERVIEW,
    seed_questions: Any = None,
    existing_doc: Any = None,
) -> Interview:
    """Build a fresh Interview with the domain's question bank.

    ``seed_questions`` (Question objects or dicts) are appended after the
    bank; every question is renumbered q1..qN. ``existing_doc`` seeds answers
    via :func:`import_answers`. Fail-open: returns an Interview no matter what.
    """
    interview = Interview()
    try:
        interview = Interview(
            title=_safe_str(title),
            domain=Domain.coerce(domain),
            mode=_coerce_mode(mode),
        )
        questions = get_questionbank(domain)
        questions.extend(_as_questions(seed_questions))
        interview.questions = _assign_ids(questions)
        interview.dimension_scores = {
            dim: DEFAULT_DIMENSION_SCORE for dim in _DIMENSIONS
        }
        doc = _safe_str(existing_doc)
        if doc.strip():
            return import_answers(interview, doc)
        return interview
    except Exception:  # noqa: BLE001
        return interview


def next_question(interview: Any) -> Question | None:
    """Return the next question to ask, adaptively, or None when done.

    Surfaced followups come first; after that the unanswered question in the
    weakest (lowest-scoring) dimension is asked. Returns None once coverage is
    >= DONE_COVERAGE and every required question is answered (and no followup
    is pending), or when nothing is left. Fail-open: never raises, worst case
    None.
    """
    try:
        if not isinstance(interview, Interview):
            return None
        amap = _answer_map(interview)
        unanswered = [
            q for q in _iter_items(interview.questions)
            if _safe_str(_qfield(q, "id")) not in amap
        ]
        if not unanswered:
            return None
        pending = [q for q in unanswered if _is_followup(q)]
        required_unanswered = [
            q for q in unanswered if _safe_bool(_qfield(q, "required", False))
        ]
        done = (_coverage(interview) >= DONE_COVERAGE and not required_unanswered)
        if done and not pending:
            return None
        if pending:
            return pending[0]
        return _weakest_question(interview, unanswered)
    except Exception:  # noqa: BLE001
        return None


def submit_answer(
    interview: Any,
    question_id: Any,
    value: Any,
    is_custom: Any = False,
    confidence: Any = 1.0,
) -> Interview:
    """Record one answer, bump its dimension score, append matched followups.

    Re-submitting a question replaces its earlier answer. Fail-open: returns
    the interview (whatever was parsed) and never raises.
    """
    if not isinstance(interview, Interview):
        return Interview()
    try:
        q = _find_question(interview, question_id)
        qid = _safe_str(question_id) or _safe_str(_qfield(q, "id"))
        ans = RequirementAnswer(
            question_id=qid,
            value=_clean_value(value),
            is_custom=_safe_bool(is_custom),
            confidence=_clamp01(_safe_float(confidence, 1.0), 1.0),
        )
        kept = []
        for a in _iter_items(_qfield(interview, "answers")):
            try:
                if _safe_str(_qfield(a, "question_id")) != qid:
                    kept.append(a)
            except Exception:  # noqa: BLE001
                kept.append(a)
        kept.append(ans)
        interview.answers = kept
        if q is not None:
            _bump_dimension(interview, _qfield(q, "dimension", "intent"), ans.confidence)
            _append_followups(interview, q, value)
        return interview
    except Exception:  # noqa: BLE001
        return interview


def _append_followups(interview: Interview, q: Question, value: Any) -> None:
    """Append followups whose trigger matches the answer. Never raises."""
    try:
        for idx, fu in enumerate(_iter_items(_qfield(q, "followups"))):
            try:
                triggers = _triggers(fu)
                if triggers and not _matches(value, triggers):
                    continue
                new_id = f"{_safe_str(_qfield(q, 'id'), 'q')}.f{idx}"
                if _find_question(interview, new_id) is not None:
                    continue
                clone = Question.from_dict(_as_question_dict(fu))
                clone.id = new_id
                interview.questions.append(clone)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return


def _as_question_dict(q: Any) -> dict[str, Any]:
    """Safely serialize one question to a dict for copying."""
    try:
        d = q.to_dict()
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {"id": "", "dimension": "open_questions", "prompt": _safe_str(q)}


def _weakest_question(interview: Interview, unanswered: list[Any]) -> Any:
    """First unanswered question in the lowest-scoring dimension."""
    best: Any = None
    best_score = 2.0
    for q in unanswered:
        try:
            dim = _safe_str(_qfield(q, "dimension", "intent")) or "intent"
            score = _dim_score(interview, dim)
            if score < best_score:
                best, best_score = q, score
        except Exception:  # noqa: BLE001
            continue
    return best


def auto_answer(interview: Any) -> Interview:
    """AUTO mode: infer answers from the title and earlier answers.

    Inferred answers are marked low-confidence; questions that cannot be
    inferred are pushed into ``interview.open_questions``. Fail-open.
    """
    if not isinstance(interview, Interview):
        return Interview()
    try:
        title = _safe_str(_qfield(interview, "title"))
        context = title + " " + " ".join(
            _safe_str(_qfield(a, "value"))
            for a in _iter_items(_qfield(interview, "answers"))
        )
        for _round in range(3):
            targets = [
                q for q in _iter_items(interview.questions)
                if _safe_str(_qfield(q, "id")) not in _answer_map(interview)
            ]
            if not targets:
                break
            progressed = False
            for q in targets:
                guess = _infer(q, title, context)
                if guess is None:
                    continue
                value, conf = guess
                submit_answer(interview, _qfield(q, "id"), value, confidence=conf)
                context += " " + _safe_str(value)
                progressed = True
            if not progressed:
                break
        for q in _iter_items(interview.questions):
            if _safe_str(_qfield(q, "id")) not in _answer_map(interview):
                _add_open(interview, _safe_str(_qfield(q, "prompt"))
                          or _safe_str(_qfield(q, "id")))
        return interview
    except Exception:  # noqa: BLE001
        return interview


def _infer(q: Any, title: str, context: str) -> tuple[Any, float] | None:
    """Guess an answer for ``q`` or return None. Never raises."""
    try:
        qtype = _question_type(q)
        dim = _safe_str(_qfield(q, "dimension", "intent")) or "intent"
        if qtype == QuestionType.SCALE:
            return ("3", 0.3)
        if qtype == QuestionType.CONFIRM:
            return ("No", 0.35)
        if qtype in (QuestionType.CHOICE, QuestionType.MULTI):
            options = [_safe_str(o) for o in _iter_items(_qfield(q, "options"))]
            hits = [o for o in options if _overlap(o, context)]
            if not hits:
                return None
            if qtype == QuestionType.MULTI:
                return (hits, 0.45)
            return (hits[0], 0.45)
        if dim == "intent" and title:
            return (title, 0.4)
        return None
    except Exception:  # noqa: BLE001
        return None


def _overlap(text: str, context: str) -> bool:
    """True when any significant word of ``text`` appears in ``context``."""
    ctx = context.lower()
    words = [w for w in _WORD_RE.findall(_safe_str(text).lower()) if len(w) >= 4]
    return any(w in ctx for w in words)


def import_answers(interview: Any, doc_text: Any) -> Interview:
    """IMPORT mode: fill unanswered questions from keyword hits in ``doc_text``.

    Matching lines become answers (choice options when they appear); gaps are
    pushed into ``interview.open_questions``. Fail-open.
    """
    if not isinstance(interview, Interview):
        return Interview()
    try:
        doc = _safe_str(doc_text)
        lines = [ln.strip() for ln in doc.splitlines() if ln.strip()] or [doc]
        for q in _iter_items(interview.questions):
            try:
                qid = _safe_str(_qfield(q, "id"))
                if not qid or qid in _answer_map(interview):
                    continue
                best = _best_line(q, lines)
                if best is None:
                    _add_open(interview, _safe_str(_qfield(q, "prompt")) or qid)
                    continue
                value, is_custom, conf = _value_from_evidence(q, best, doc)
                submit_answer(interview, qid, value, is_custom=is_custom, confidence=conf)
            except Exception:  # noqa: BLE001
                continue
        return interview
    except Exception:  # noqa: BLE001
        return interview


def _prompt_tokens(text: Any) -> list[str]:
    """Significant lowercase words of a prompt."""
    words = _WORD_RE.findall(_safe_str(text).lower())
    return [w for w in words if len(w) >= 4 and w not in _STOPWORDS]


def _best_line(q: Any, lines: list[str]) -> str | None:
    """The earliest line sharing the most prompt keywords (>= 2), else None."""
    tokens = _prompt_tokens(_qfield(q, "prompt"))
    best: str | None = None
    best_score = 0
    for line in lines:
        low = line.lower()
        score = sum(1 for t in tokens if t in low)
        if score > best_score:
            best, best_score = line, score
    if best_score >= 2 or (best_score >= 1 and len(tokens) <= 2):
        return best
    return None


def _option_hits(q: Any, text: str) -> list[str]:
    """Options of ``q`` whose wording appears in ``text`` (order preserved)."""
    low = _safe_str(text).lower()
    hits: list[str] = []
    for opt in _iter_items(_qfield(q, "options")):
        o = _safe_str(opt)
        if not o:
            continue
        if o.lower() in low:
            hits.append(o)
    return hits


def _value_from_evidence(q: Any, line: str, doc: str) -> tuple[Any, bool, float]:
    """Derive (value, is_custom, confidence) from a matched line."""
    qtype = _question_type(q)
    if qtype in (QuestionType.CHOICE, QuestionType.MULTI):
        hits = _option_hits(q, doc) or _option_hits(q, line)
        if hits and qtype == QuestionType.MULTI:
            return (hits, False, 0.6)
        if hits:
            return (hits[0], False, 0.6)
        return (line[:400], True, 0.5)
    if qtype == QuestionType.CONFIRM:
        low = line.lower()
        if re.search(r"\byes\b", low):
            return ("Yes", False, 0.55)
        if re.search(r"\bno\b", low):
            return ("No", False, 0.55)
        return (line[:400], True, 0.5)
    if qtype == QuestionType.SCALE:
        m = re.search(r"\b([1-5])\b", line)
        return (m.group(1), False, 0.5) if m else ("3", False, 0.3)
    return (line[:400], False, 0.55)


def batch_answer(interview: Any, answers: Any) -> Interview:
    """BATCH mode: apply a whole form of {question_id: value} at once.

    Values may be plain, or dicts with ``value``/``is_custom``/``confidence``.
    Unmatched fields are recorded in ``open_questions``. Fail-open.
    """
    if not isinstance(interview, Interview):
        return Interview()
    try:
        items = answers.items() if isinstance(answers, dict) else []
        for k, v in items:
            try:
                key = _safe_str(k)
                if _find_question(interview, key) is None:
                    _add_open(interview, f"Unmatched form field: {key}")
                    continue
                value, is_custom, conf = _unpack(v)
                submit_answer(interview, key, value, is_custom=is_custom, confidence=conf)
            except Exception:  # noqa: BLE001
                continue
        return interview
    except Exception:  # noqa: BLE001
        return interview


def _unpack(v: Any) -> tuple[Any, bool, float]:
    """Normalize a batch form value to (value, is_custom, confidence)."""
    try:
        if isinstance(v, dict):
            return (
                _clean_value(v.get("value", "")),
                _safe_bool(v.get("is_custom", False)),
                _clamp01(_safe_float(v.get("confidence", 1.0), 1.0), 1.0),
            )
    except Exception:  # noqa: BLE001
        return ("", False, 1.0)
    return (_clean_value(v), False, 1.0)


def interview_summary(interview: Any) -> dict[str, Any]:
    """A snapshot of coverage, confidence, dimension scores and open items.

    Fail-open: returns a zeroed summary dict on any hostile input.
    """
    summary: dict[str, Any] = {
        "title": "",
        "slug": "",
        "domain": Domain.GENERAL.value,
        "mode": InterviewMode.INTERVIEW.value,
        "question_count": 0,
        "answered_count": 0,
        "coverage": 0.0,
        "overall_confidence": 0.0,
        "dimension_scores": {},
        "open_question_count": 0,
        "open_questions": [],
        "required_outstanding": 0,
    }
    if not isinstance(interview, Interview):
        return summary
    amap = _answer_map(interview)
    summary["title"] = _safe_str(_qfield(interview, "title"))
    summary["slug"] = _safe_str(_qfield(interview, "slug"))
    summary["domain"] = _safe_str(_qfield(interview, "domain", Domain.GENERAL.value))
    summary["mode"] = _safe_str(_qfield(interview, "mode", InterviewMode.INTERVIEW.value))
    questions = _iter_items(_qfield(interview, "questions"))
    summary["question_count"] = _metric(lambda: len(questions), 0)
    summary["answered_count"] = len(amap)
    summary["coverage"] = _metric(lambda: _coverage(interview), 0.0)
    summary["overall_confidence"] = _metric(
        lambda: _clamp01(_safe_float(interview.overall_confidence())), 0.0
    )
    summary["dimension_scores"] = {
        _safe_str(k): _clamp01(_safe_float(v))
        for k, v in _metric(
            lambda: dict(_qfield(interview, "dimension_scores", {})), {}
        ).items()
    }
    open_qs = _iter_items(_qfield(interview, "open_questions"))
    summary["open_question_count"] = _metric(lambda: len(open_qs), 0)
    summary["open_questions"] = [_safe_str(o) for o in open_qs]
    summary["required_outstanding"] = sum(
        1 for q in questions
        if _safe_bool(_qfield(q, "required", False))
        and _safe_str(_qfield(q, "id")) not in amap
    )
    return summary
