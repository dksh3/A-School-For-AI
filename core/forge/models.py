"""Data model for the Forge suite — the shared contract.

Every builder (clarion/blueprint/edict/weave/compass/prism) reads and writes
these types. They are plain dataclasses with fail-open ``to_dict``/``from_dict``
so hostile or partial input never crashes a builder. Universal by design: the
``Domain`` enum covers 11 named domains and always falls back to ``GENERAL``
so any kind of work — coding or otherwise — is first-class.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# --- fail-open coercion helpers -------------------------------------------

def _safe_str(v: Any, default: str = "") -> str:
    """Coerce ``v`` to a clean str. Never raises."""
    try:
        if v is None:
            return default
        s = v if isinstance(v, str) else str(v)
        # scrub lone surrogates that break UTF-8 writes
        return s.encode("utf-8", "replace").decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if isinstance(v, bool):
            return int(v)
        return int(float(v))  # handles "3", 3.0
    except Exception:  # noqa: BLE001
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):  # NaN/inf
            return default
        return f
    except Exception:  # noqa: BLE001
        return default


def _safe_list(v: Any) -> list[Any]:
    try:
        if isinstance(v, list):
            return v
        if isinstance(v, (tuple, set)):
            return list(v)
        return []
    except Exception:  # noqa: BLE001
        return []


def _slug(text: str) -> str:
    s = _safe_str(text).lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:64] or "item"


# --- domains ---------------------------------------------------------------

class Domain(StrEnum):
    """The 11 first-class domains + universal fallback."""

    CODING = "coding"
    WRITING = "writing"
    RESEARCH = "research"
    BUSINESS = "business"
    PLANNING = "planning"
    EDUCATION = "education"
    CREATIVE = "creative"
    OPS = "ops"
    DATA = "data"
    LIFE = "life"
    GENERAL = "general"

    @classmethod
    def coerce(cls, v: Any) -> Domain:
        s = _safe_str(v).lower().strip()
        for d in cls:
            if d.value == s:
                return d
        # light aliasing so users can type "code"/"dev"/"write" etc.
        aliases = {
            "code": "coding", "dev": "coding", "software": "coding",
            "write": "writing", "docs": "writing", "content": "writing",
            "learn": "education", "teach": "education", "study": "education",
            "biz": "business", "startup": "business", "product": "business",
            "plan": "planning", "project": "planning", "roadmap": "planning",
            "art": "creative", "design": "creative", "story": "creative",
            "ops": "ops", "devops": "ops", "infra": "ops", "sre": "ops",
            "data": "data", "ml": "data", "analytics": "data",
            "life": "life", "personal": "life", "health": "life",
            "research": "research", "science": "research",
        }
        mapped = aliases.get(s)
        if mapped:
            return cls(mapped)
        return cls.GENERAL  # universal fallback: never fails


# --- interview vocabulary ---------------------------------------------------

class QuestionType(StrEnum):
    CHOICE = "choice"      # pick one (or "your own")
    MULTI = "multi"        # pick several (or "your own")
    SCALE = "scale"        # 1..N
    TEXT = "text"          # free text
    CONFIRM = "confirm"    # yes/no


class InterviewMode(StrEnum):
    INTERVIEW = "interview"  # one question per turn (adaptive)
    BATCH = "batch"          # fill a form in one go
    AUTO = "auto"            # infer answers, mark open questions
    IMPORT = "import"        # seed from an existing doc/repo, interview gaps


#: The 12 dimensions scored during discovery. Order is the asking order.
_DIMENSIONS: tuple[str, ...] = (
    "intent", "audience", "scope", "constraints", "success",
    "resources", "risks", "sequence", "style", "edge_cases",
    "glossary", "open_questions",
)


@dataclass
class Question:
    """A single discovery question. Universal across domains."""

    id: str
    dimension: str
    prompt: str
    type: QuestionType = QuestionType.TEXT
    options: list[str] = field(default_factory=list)
    allow_custom: bool = True          # every choice has a "(your own)…" escape
    followups: list[Question] = field(default_factory=list)
    required: bool = False
    domain_hint: str = ""              # optional domain-specific phrasing

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dimension": _safe_str(self.dimension),
            "prompt": _safe_str(self.prompt),
            "type": self.type.value if isinstance(self.type, QuestionType)
                    else _safe_str(self.type),
            "options": [_safe_str(o) for o in _safe_list(self.options)],
            "allow_custom": bool(self.allow_custom),
            "followups": [q.to_dict() for q in _safe_list(self.followups)],
            "required": bool(self.required),
            "domain_hint": _safe_str(self.domain_hint),
        }

    @classmethod
    def from_dict(cls, d: Any) -> Question:
        d = d if isinstance(d, dict) else {}
        raw_type = _safe_str(d.get("type"), "text")
        try:
            qtype = QuestionType(raw_type)
        except Exception:  # noqa: BLE001
            qtype = QuestionType.TEXT
        followups = [
            cls.from_dict(q) for q in _safe_list(d.get("followups"))
            if isinstance(q, dict)
        ]
        return cls(
            id=_safe_str(d.get("id"), _slug(_safe_str(d.get("prompt"), "q"))),
            dimension=_safe_str(d.get("dimension"), "intent"),
            prompt=_safe_str(d.get("prompt")),
            type=qtype,
            options=[_safe_str(o) for o in _safe_list(d.get("options"))],
            allow_custom=bool(d.get("allow_custom", True)),
            followups=followups,
            required=bool(d.get("required", False)),
            domain_hint=_safe_str(d.get("domain_hint")),
        )


@dataclass
class RequirementAnswer:
    """A user's answer to one question."""

    question_id: str
    value: Any = ""
    is_custom: bool = False            # free-text "(your own)…" chosen
    confidence: float = 1.0            # 0..1 — how sure the user was

    def to_dict(self) -> dict[str, Any]:
        v = self.value
        if not isinstance(v, (str, int, float, bool, type(None), list, dict)):
            v = _safe_str(v)
        return {
            "question_id": _safe_str(self.question_id),
            "value": v,
            "is_custom": bool(self.is_custom),
            "confidence": max(0.0, min(1.0, _safe_float(self.confidence, 1.0))),
        }

    @classmethod
    def from_dict(cls, d: Any) -> RequirementAnswer:
        d = d if isinstance(d, dict) else {}
        return cls(
            question_id=_safe_str(d.get("question_id")),
            value=d.get("value", ""),
            is_custom=bool(d.get("is_custom", False)),
            confidence=max(0.0, min(1.0, _safe_float(d.get("confidence"), 1.0))),
        )


@dataclass
class Interview:
    """A discovery interview session. Holds questions, answers, confidence."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    domain: Domain = Domain.GENERAL
    mode: InterviewMode = InterviewMode.INTERVIEW
    questions: list[Question] = field(default_factory=list)
    answers: list[RequirementAnswer] = field(default_factory=list)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    open_questions: list[str] = field(default_factory=list)
    glossary: dict[str, str] = field(default_factory=dict)
    slug: str = ""

    def __post_init__(self) -> None:
        self.domain = self.domain if isinstance(self.domain, Domain) \
            else Domain.coerce(self.domain)
        self.mode = self.mode if isinstance(self.mode, InterviewMode) \
            else InterviewMode.coerce(self.mode) \
            if hasattr(InterviewMode, "coerce") \
            else InterviewMode(_safe_str(self.mode, "interview")
                               if _safe_str(self.mode) in
                               {m.value for m in InterviewMode}
                               else "interview")
        self.slug = _safe_str(self.slug) or _slug(self.title or self.id)

    def answer_map(self) -> dict[str, RequirementAnswer]:
        return {_safe_str(a.question_id): a for a in self.answers}

    def coverage(self) -> float:
        """Fraction of dimensions with at least one answer, 0..1."""
        if not self.questions:
            return 0.0
        answered_dims = set()
        amap = self.answer_map()
        for q in self.questions:
            if q.id in amap:
                answered_dims.add(q.dimension)
        return len(answered_dims) / max(1, len(_DIMENSIONS))

    def overall_confidence(self) -> float:
        confs = [a.confidence for a in self.answers] or [0.0]
        return sum(confs) / len(confs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": _safe_str(self.title),
            "domain": self.domain.value if isinstance(self.domain, Domain)
                      else _safe_str(self.domain),
            "mode": self.mode.value if isinstance(self.mode, InterviewMode)
                    else _safe_str(self.mode),
            "questions": [q.to_dict() for q in self.questions],
            "answers": [a.to_dict() for a in self.answers],
            "dimension_scores": {
                k: _safe_float(v) for k, v in self.dimension_scores.items()
            },
            "open_questions": [_safe_str(o) for o in self.open_questions],
            "glossary": {
                _safe_str(k): _safe_str(v) for k, v in self.glossary.items()
            },
            "slug": self.slug,
        }

    @classmethod
    def from_dict(cls, d: Any) -> Interview:
        d = d if isinstance(d, dict) else {}
        questions = [Question.from_dict(q) for q in _safe_list(d.get("questions"))
                     if isinstance(q, dict)]
        answers = [RequirementAnswer.from_dict(a) for a in _safe_list(d.get("answers"))
                   if isinstance(a, dict)]
        glossary = {}
        raw_gloss = d.get("glossary")
        if isinstance(raw_gloss, dict):
            glossary = {_safe_str(k): _safe_str(v)
                        for k, v in raw_gloss.items()}
        return cls(
            id=_safe_str(d.get("id"), uuid.uuid4().hex[:12]),
            title=_safe_str(d.get("title")),
            domain=Domain.coerce(d.get("domain")),
            mode=InterviewMode(_safe_str(d.get("mode"), "interview"))
            if _safe_str(d.get("mode")) in {m.value for m in InterviewMode}
            else InterviewMode.INTERVIEW,
            questions=questions,
            answers=answers,
            dimension_scores={
                _safe_str(k): _safe_float(v)
                for k, v in (d.get("dimension_scores")
                             if isinstance(d.get("dimension_scores"), dict)
                             else {}).items()
            },
            open_questions=[_safe_str(o) for o in _safe_list(d.get("open_questions"))],
            glossary=glossary,
            slug=_safe_str(d.get("slug")),
        )


# --- artifact model --------------------------------------------------------

class FormationKind(StrEnum):
    PHASES = "phases"
    ROADMAP = "roadmap"
    DEPENDENCY_GRAPH = "dependency_graph"
    PARALLEL_LANES = "parallel_lanes"
    CRITICAL_PATH = "critical_path"


@dataclass
class Command:
    """An ordered, executable action in the edict."""

    id: str
    title: str
    detail: str = ""
    kind: str = "step"          # step | check | setup | ship | learn
    phase: str = ""
    estimated_minutes: int = 0
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": _safe_str(self.id),
            "title": _safe_str(self.title),
            "detail": _safe_str(self.detail),
            "kind": _safe_str(self.kind, "step"),
            "phase": _safe_str(self.phase),
            "estimated_minutes": max(0, _safe_int(self.estimated_minutes)),
            "depends_on": [_safe_str(x) for x in _safe_list(self.depends_on)],
        }

    @classmethod
    def from_dict(cls, d: Any) -> Command:
        d = d if isinstance(d, dict) else {}
        return cls(
            id=_safe_str(d.get("id"), _slug(_safe_str(d.get("title"), "cmd"))),
            title=_safe_str(d.get("title")),
            detail=_safe_str(d.get("detail")),
            kind=_safe_str(d.get("kind"), "step"),
            phase=_safe_str(d.get("phase")),
            estimated_minutes=max(0, _safe_int(d.get("estimated_minutes"))),
            depends_on=[_safe_str(x) for x in _safe_list(d.get("depends_on"))],
        )


@dataclass
class Directive:
    """An always/never rule that governs execution."""

    id: str
    rule: str
    kind: str = "always"        # always | never | prefer | avoid
    rationale: str = ""
    strength: float = 1.0       # 0..1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": _safe_str(self.id),
            "rule": _safe_str(self.rule),
            "kind": _safe_str(self.kind, "always"),
            "rationale": _safe_str(self.rationale),
            "strength": max(0.0, min(1.0, _safe_float(self.strength, 1.0))),
        }

    @classmethod
    def from_dict(cls, d: Any) -> Directive:
        d = d if isinstance(d, dict) else {}
        return cls(
            id=_safe_str(d.get("id"), _slug(_safe_str(d.get("rule"), "dir"))),
            rule=_safe_str(d.get("rule")),
            kind=_safe_str(d.get("kind"), "always"),
            rationale=_safe_str(d.get("rationale")),
            strength=max(0.0, min(1.0, _safe_float(d.get("strength"), 1.0))),
        )


@dataclass
class Formation:
    """A roadmap/plan shape derived from the interview."""

    kind: FormationKind = FormationKind.PHASES
    phases: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[tuple[str, str]] = field(default_factory=list)
    lanes: list[dict[str, Any]] = field(default_factory=list)
    critical_path: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        deps = []
        for dep in _safe_list(self.dependencies):
            try:
                a, b = dep
                deps.append([_safe_str(a), _safe_str(b)])
            except Exception:  # noqa: BLE001
                continue
        return {
            "kind": self.kind.value if isinstance(self.kind, FormationKind)
                    else _safe_str(self.kind),
            "phases": _safe_list(self.phases),
            "dependencies": deps,
            "lanes": _safe_list(self.lanes),
            "critical_path": [_safe_str(x) for x in _safe_list(self.critical_path)],
        }

    @classmethod
    def from_dict(cls, d: Any) -> Formation:
        d = d if isinstance(d, dict) else {}
        raw_kind = _safe_str(d.get("kind"), "phases")
        try:
            kind = FormationKind(raw_kind)
        except Exception:  # noqa: BLE001
            kind = FormationKind.PHASES
        deps = []
        for dep in _safe_list(d.get("dependencies")):
            items = _safe_list(dep) if not isinstance(dep, (list, tuple)) else list(dep)
            if len(items) >= 2:
                deps.append((_safe_str(items[0]), _safe_str(items[1])))
        return cls(
            kind=kind,
            phases=_safe_list(d.get("phases")),
            dependencies=deps,
            lanes=_safe_list(d.get("lanes")),
            critical_path=[_safe_str(x) for x in _safe_list(d.get("critical_path"))],
        )


@dataclass
class AcceptanceCriteria:
    """Given/When/Then acceptance + checklist + success metrics."""

    scenarios: list[dict[str, str]] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarios": _safe_list(self.scenarios),
            "checklist": [_safe_str(c) for c in _safe_list(self.checklist)],
            "metrics": _safe_list(self.metrics),
        }

    @classmethod
    def from_dict(cls, d: Any) -> AcceptanceCriteria:
        d = d if isinstance(d, dict) else {}
        return cls(
            scenarios=_safe_list(d.get("scenarios")),
            checklist=[_safe_str(c) for c in _safe_list(d.get("checklist"))],
            metrics=_safe_list(d.get("metrics")),
        )


@dataclass
class Blueprint:
    """The design-spec artifact — the primary deliverable of clarion."""

    title: str = ""
    goal: str = ""
    domain: Domain = Domain.GENERAL
    problem: str = ""
    proposed: str = ""
    non_goals: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    success_metrics: list[str] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    glossary: dict[str, str] = field(default_factory=dict)
    decomposition: list[dict[str, Any]] = field(default_factory=list)
    traceability: list[dict[str, Any]] = field(default_factory=list)
    slug: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": _safe_str(self.title),
            "goal": _safe_str(self.goal),
            "domain": self.domain.value if isinstance(self.domain, Domain)
                      else _safe_str(self.domain),
            "problem": _safe_str(self.problem),
            "proposed": _safe_str(self.proposed),
            "non_goals": [_safe_str(x) for x in _safe_list(self.non_goals)],
            "constraints": [_safe_str(x) for x in _safe_list(self.constraints)],
            "assumptions": [_safe_str(x) for x in _safe_list(self.assumptions)],
            "success_metrics": [_safe_str(x) for x in _safe_list(self.success_metrics)],
            "risks": _safe_list(self.risks),
            "open_questions": [_safe_str(x) for x in _safe_list(self.open_questions)],
            "glossary": {
                _safe_str(k): _safe_str(v) for k, v in self.glossary.items()
            },
            "decomposition": _safe_list(self.decomposition),
            "traceability": _safe_list(self.traceability),
            "slug": _safe_str(self.slug),
        }

    @classmethod
    def from_dict(cls, d: Any) -> Blueprint:
        d = d if isinstance(d, dict) else {}
        glossary = {}
        if isinstance(d.get("glossary"), dict):
            glossary = {_safe_str(k): _safe_str(v)
                        for k, v in d["glossary"].items()}
        return cls(
            title=_safe_str(d.get("title")),
            goal=_safe_str(d.get("goal")),
            domain=Domain.coerce(d.get("domain")),
            problem=_safe_str(d.get("problem")),
            proposed=_safe_str(d.get("proposed")),
            non_goals=[_safe_str(x) for x in _safe_list(d.get("non_goals"))],
            constraints=[_safe_str(x) for x in _safe_list(d.get("constraints"))],
            assumptions=[_safe_str(x) for x in _safe_list(d.get("assumptions"))],
            success_metrics=[_safe_str(x) for x in _safe_list(d.get("success_metrics"))],
            risks=_safe_list(d.get("risks")),
            open_questions=[_safe_str(x) for x in _safe_list(d.get("open_questions"))],
            glossary=glossary,
            decomposition=_safe_list(d.get("decomposition")),
            traceability=_safe_list(d.get("traceability")),
            slug=_safe_str(d.get("slug")),
        )


@dataclass
class Idea:
    """One brainstorm idea (prism)."""

    title: str
    description: str = ""
    technique: str = ""        # which divergent technique produced it
    score: float = 0.0         # convergent score (impact/effort blend)
    feasibility: float = 0.0
    impact: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": _safe_str(self.title),
            "description": _safe_str(self.description),
            "technique": _safe_str(self.technique),
            "score": _safe_float(self.score),
            "feasibility": _safe_float(self.feasibility),
            "impact": _safe_float(self.impact),
            "tags": [_safe_str(t) for t in _safe_list(self.tags)],
        }

    @classmethod
    def from_dict(cls, d: Any) -> Idea:
        d = d if isinstance(d, dict) else {}
        return cls(
            title=_safe_str(d.get("title")),
            description=_safe_str(d.get("description")),
            technique=_safe_str(d.get("technique")),
            score=_safe_float(d.get("score")),
            feasibility=_safe_float(d.get("feasibility")),
            impact=_safe_float(d.get("impact")),
            tags=[_safe_str(t) for t in _safe_list(d.get("tags"))],
        )


@dataclass
class BrainstormSession:
    """A divergent→convergent brainstorm (prism)."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    topic: str = ""
    domain: Domain = Domain.GENERAL
    ideas: list[Idea] = field(default_factory=list)
    technique_counts: dict[str, int] = field(default_factory=dict)
    selected: list[str] = field(default_factory=list)
    slug: str = ""

    def __post_init__(self) -> None:
        self.domain = self.domain if isinstance(self.domain, Domain) \
            else Domain.coerce(self.domain)
        self.slug = _safe_str(self.slug) or _slug(self.topic or self.id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic": _safe_str(self.topic),
            "domain": self.domain.value if isinstance(self.domain, Domain)
                      else _safe_str(self.domain),
            "ideas": [i.to_dict() for i in self.ideas],
            "technique_counts": {
                _safe_str(k): _safe_int(v)
                for k, v in self.technique_counts.items()
            },
            "selected": [_safe_str(s) for s in _safe_list(self.selected)],
            "slug": self.slug,
        }

    @classmethod
    def from_dict(cls, d: Any) -> BrainstormSession:
        d = d if isinstance(d, dict) else {}
        ideas = [Idea.from_dict(i) for i in _safe_list(d.get("ideas"))
                 if isinstance(i, dict)]
        tc = {}
        if isinstance(d.get("technique_counts"), dict):
            tc = {_safe_str(k): _safe_int(v)
                  for k, v in d["technique_counts"].items()}
        return cls(
            id=_safe_str(d.get("id"), uuid.uuid4().hex[:12]),
            topic=_safe_str(d.get("topic")),
            domain=Domain.coerce(d.get("domain")),
            ideas=ideas,
            technique_counts=tc,
            selected=[_safe_str(s) for s in _safe_list(d.get("selected"))],
            slug=_safe_str(d.get("slug")),
        )


@dataclass
class Artifact:
    """A rendered deliverable: Markdown body + School visual + metadata."""

    kind: str                 # blueprint | edict | weave | compass | prism | bundle
    title: str
    markdown: str = ""
    visual: str = ""
    path: str = ""
    domain: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": _safe_str(self.kind),
            "title": _safe_str(self.title),
            "markdown": _safe_str(self.markdown),
            "visual": _safe_str(self.visual),
            "path": _safe_str(self.path),
            "domain": _safe_str(self.domain),
            "metadata": dict(self.metadata) if isinstance(self.metadata, dict) else {},
        }
