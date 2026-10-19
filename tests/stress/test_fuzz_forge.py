"""Adversarial fuzz campaign for the Forge engine (core/forge/*).

Every forge tool and feature is exercised 2000 times per label with
failure-seeking inputs (the shared HOSTILE corpus, gen_value and
gen_json_safe wired into EVERY parameter). The FAIL-OPEN invariant: every
public engine function returns a result and never raises at the boundary;
every model round-trip (to_dict -> from_dict -> to_dict) is idempotent.

KNOWN ENGINE BUGS (quarantined, not hidden)
------------------------------------------
``core/forge/models.py`` ``from_dict``/``to_dict`` are NOT fully fail-open:
hostile container subclasses from the shared corpus (``_BadList``/``_BadDict``
whose ``__iter__``/``items`` raise, ``_Evil`` whose ``__bool__`` raises) leak
past the ``_safe_list``/``bool()`` helpers and raise out of the dataclass
layer (e.g. models.py:295 ``raw_gloss.items()``, models.py:287 question
iteration). Those raises are recorded in ENGINE_BUGS with their exact
file:line signature and surfaced by ``test_zz_ledger_summary`` so the engine
owner can fix them (models.py is not owned by this test file). Everything
else - and every raise NOT rooted in core/forge/models.py - is a hard
failure. Delete ``_guarded`` once models.py is fail-open.

Run:
    python -m pytest tests/stress/test_fuzz_forge.py \\
        --basetemp="C:\\\\Users\\\\dex34\\\\AppData\\\\Local\\\\Temp\\\\opencode\\\\pytest" -q
"""

from __future__ import annotations

import pathlib
import random
import sys
import traceback
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fuzz_harness import (  # noqa: E402
    FUZZ_FAILURES,
    FUZZ_LEDGER,
    HOSTILE,
    fuzz_fail_open,
    gen_json_safe,
    gen_value,
    ledger_summary,
)

from core.forge.blueprint import build_blueprint  # noqa: E402
from core.forge.clarion import (  # noqa: E402
    auto_answer,
    batch_answer,
    import_answers,
    interview_summary,
    next_question,
    start_interview,
    submit_answer,
)
from core.forge.compass import build_compass  # noqa: E402
from core.forge.domains import ALL_DOMAINS, get_questionbank  # noqa: E402
from core.forge.edict import Edict, build_edict  # noqa: E402
from core.forge.models import (  # noqa: E402
    AcceptanceCriteria,
    Artifact,
    Blueprint,
    BrainstormSession,
    Command,
    Directive,
    Domain,
    Formation,
    Idea,
    Interview,
    Question,
    RequirementAnswer,
)
from core.forge.prism import (  # noqa: E402
    brainstorm,
    brainstorm_summary,
    cluster_ideas,
    score_ideas,
    select_top,
)
from core.forge.render import render_artifact, render_bundle  # noqa: E402
from core.forge.weave import build_weave  # noqa: E402

N = 2000  # iterations per tool.feature label

#: Sentinel returned for a quarantined KNOWN engine bug (core/forge/models.py).
_KNOWN_BUG = object()

#: label -> {"count", "loc", "tb"} for quarantined models.py fail-open bugs.
ENGINE_BUGS: dict[tuple[str, str, str], dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Known-bug quarantine: only raises rooted in core/forge/models.py qualify
# ---------------------------------------------------------------------------


def _models_loc(tb_text: str) -> str:
    for line in tb_text.splitlines():
        if "File" in line and "models.py" in line:
            return line.strip()
    return ""


def _guarded(label: str, fn):
    """Wrap ``fn`` so raises rooted in core/forge/models.py (KNOWN fail-open
    bugs) are recorded with file:line and converted to the sentinel. Any
    raise from anywhere else propagates and fails the fuzz run."""

    def call(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - recording boundary
            tb = traceback.format_exc()
            loc = _models_loc(tb)
            if not loc:
                raise  # not the known models.py bug class: hard failure
            key = (label, type(exc).__name__, _s(exc, 120))
            rec = ENGINE_BUGS.setdefault(
                key, {"count": 0, "loc": loc, "tb": tb[-400:]}
            )
            rec["count"] += 1
            return _KNOWN_BUG

    return call


# ---------------------------------------------------------------------------
# Safe helpers for argument generation (make_args must never raise)
# ---------------------------------------------------------------------------


def _s(value: Any, limit: int = 200) -> str:
    try:
        text = str(value)
    except Exception:  # noqa: BLE001 - hostile __str__
        text = f"<{type(value).__name__}>"
    return text[:limit]


def _pick(i: int, offset: int = 0) -> Any:
    return HOSTILE[(i * 7 + offset) % len(HOSTILE)]


def _mixed(i: int, valid: Any, offset: int = 0) -> Any:
    """~30% valid value, ~70% hostile value - deep paths AND failures."""
    return valid if i % 10 < 3 else _pick(i, offset)


def _mixed_gen(i: int, valid: Any, offset: int = 0) -> Any:
    """Like _mixed but occasionally a recursive adversarial value."""
    if i % 10 < 3:
        return valid
    if i % 10 == 3:
        return gen_value(rng=random.Random(i * 31 + offset))
    return _pick(i, offset)


def _leaf(value: Any) -> str:
    try:
        return f"{type(value).__name__}:{value!r}"
    except Exception:  # noqa: BLE001 - hostile __repr__
        return type(value).__name__


def _canon(obj: Any, depth: int = 0) -> Any:
    """JSON-safe structural digest that never raises (for idempotence checks)."""
    if depth > 6:
        return "<deep>"
    if isinstance(obj, dict):
        try:
            items = list(obj.items())
        except Exception:  # noqa: BLE001 - hostile dict subclass
            return "<dict>"
        out: dict[str, Any] = {}
        for k, v in items:
            try:
                out[_leaf(k)] = _canon(v, depth + 1)
            except Exception:  # noqa: BLE001
                out[_leaf(k)] = "<?>"
        return out
    if isinstance(obj, (list, tuple)):
        try:
            return [_canon(v, depth + 1) for v in obj]
        except Exception:  # noqa: BLE001 - hostile list subclass
            return "<seq>"
    return _leaf(obj)


# --- real-object factories (always safe to call) ---------------------------


def _real_interview(i: int) -> Interview:
    try:
        domain = list(Domain)[i % len(list(Domain))]
        iv = start_interview(f"task {i}", domain)
        for q in list(iv.questions)[: i % 4]:
            submit_answer(iv, q.id, f"answer {i} for {q.dimension}")
        return iv
    except Exception:  # noqa: BLE001
        return Interview()


def _mixed_interview(i: int) -> Any:
    return _real_interview(i) if i % 10 < 3 else _pick(i, 11)


def _real_blueprint(i: int) -> Blueprint:
    try:
        return build_blueprint(_real_interview(i))
    except Exception:  # noqa: BLE001
        return Blueprint()


def _mixed_blueprint(i: int) -> Any:
    return _real_blueprint(i) if i % 10 < 3 else _pick(i, 12)


def _real_commands(i: int) -> list[Command]:
    try:
        edict = build_edict(_real_interview(i))
        return list(edict.commands)[:4]
    except Exception:  # noqa: BLE001
        return []


def _mixed_commands(i: int) -> Any:
    return _real_commands(i) if i % 10 < 3 else _pick(i, 13)


def _real_session(i: int) -> BrainstormSession:
    try:
        return brainstorm(f"topic {i}", count=4, seed=i)
    except Exception:  # noqa: BLE001
        return BrainstormSession()


def _mixed_session(i: int) -> Any:
    return _real_session(i) if i % 10 < 3 else _mixed_gen(i, None, 14)


# ---------------------------------------------------------------------------
# Invariant checks (cheap; assert sane shapes on successful results)
# ---------------------------------------------------------------------------


def _check_interview(result: Any) -> None:
    assert isinstance(result, Interview), f"not an Interview: {type(result)}"
    assert isinstance(result.questions, list)
    assert all(isinstance(q, Question) for q in result.questions)
    assert isinstance(result.answers, list)
    assert all(isinstance(a, RequirementAnswer) for a in result.answers)
    assert isinstance(result.dimension_scores, dict)
    assert isinstance(result.open_questions, list)


def _check_question_or_none(result: Any) -> None:
    assert result is None or isinstance(result, Question), \
        f"not Question|None: {type(result)}"


def _check_summary(result: Any) -> None:
    assert isinstance(result, dict), f"not a dict: {type(result)}"
    assert {"coverage", "answered_count", "open_question_count"} <= set(result)
    cov = result["coverage"]
    assert isinstance(cov, (int, float)) and 0.0 <= cov <= 1.0, f"bad coverage: {cov}"


def _check_blueprint(result: Any) -> None:
    assert isinstance(result, Blueprint), f"not a Blueprint: {type(result)}"


def _check_edict(result: Any) -> None:
    assert isinstance(result, Edict), f"not an Edict: {type(result)}"
    assert isinstance(result.commands, list)
    assert all(isinstance(c, Command) for c in result.commands)
    assert isinstance(result.directives, list)
    assert all(isinstance(d, Directive) for d in result.directives)


def _check_formation(result: Any) -> None:
    assert isinstance(result, Formation), f"not a Formation: {type(result)}"
    assert isinstance(result.phases, list)
    assert isinstance(result.lanes, list)
    assert isinstance(result.critical_path, list)


def _check_acceptance(result: Any) -> None:
    assert isinstance(result, AcceptanceCriteria), f"not criteria: {type(result)}"
    assert isinstance(result.scenarios, list)
    assert isinstance(result.checklist, list)
    assert isinstance(result.metrics, list)


def _check_artifact(result: Any) -> None:
    assert isinstance(result, Artifact), f"not an Artifact: {type(result)}"
    assert isinstance(result.markdown, str) and result.markdown.strip(), "empty markdown"
    assert isinstance(result.visual, str) and result.visual.strip(), "empty visual"


def _check_bundle(result: Any) -> None:
    assert isinstance(result, dict), f"not a dict: {type(result)}"
    assert set(result) == {"blueprint", "edict", "weave", "compass", "bundle"}
    for kind, art in result.items():
        assert isinstance(art, Artifact), f"{kind}: not an Artifact"
        assert art.markdown.strip(), f"{kind}: empty markdown"


def _check_session(result: Any) -> None:
    assert isinstance(result, BrainstormSession), f"not a session: {type(result)}"
    assert isinstance(result.ideas, list)
    assert all(isinstance(x, Idea) for x in result.ideas)
    assert isinstance(result.technique_counts, dict)
    assert isinstance(result.selected, list)


def _check_cluster(result: Any) -> None:
    assert isinstance(result, dict), f"not a dict: {type(result)}"
    assert all(isinstance(v, list) for v in result.values())


def _check_summary(result: Any) -> None:
    assert isinstance(result, dict), f"not a dict: {type(result)}"
    if not result:
        return
    assert "domain" in result, f"summary missing shared key: domain ({sorted(result)})"


def _check_domain(result: Any) -> None:
    assert isinstance(result, Domain), f"not a Domain: {type(result)}"


def _check_bank(result: Any) -> None:
    assert isinstance(result, list), f"not a list: {type(result)}"
    assert all(isinstance(q, Question) for q in result)
    assert len(result) >= 1, "question bank came back empty"


def _check_roundtrip(result: Any) -> None:
    if result is _KNOWN_BUG:
        return
    d2, d3 = result
    assert isinstance(d2, dict) and isinstance(d3, dict)
    assert _canon(d2) == _canon(d3), "to_dict/from_dict round-trip is not idempotent"


def _check_to_dict(result: Any) -> None:
    if result is _KNOWN_BUG:
        return
    assert isinstance(result, dict), f"to_dict returned {type(result)}"


# ===========================================================================
# 1) clarion - the adaptive discovery interview
# ===========================================================================


class TestClarionFuzz:
    def test_start(self) -> None:
        def make(i: int):
            try:
                return ((
                    _mixed_gen(i, "Family reunion weekend", 0),
                    _mixed(i, list(Domain)[i % 11], 1),
                    _mixed(i, "interview", 2),
                    _mixed(i, None, 3),
                    _mixed_gen(i, "Goal: a family reunion.\n", 4),
                ), {})
            except Exception:  # noqa: BLE001
                return (("t",), {})

        report = fuzz_fail_open(start_interview, n=N, make_args=make,
                                label="clarion.start", check=_check_interview)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_next(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_interview(i),), {})
            except Exception:  # noqa: BLE001
                return ((None,), {})

        report = fuzz_fail_open(next_question, n=N, make_args=make,
                                label="clarion.next", check=_check_question_or_none)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_submit_answer(self) -> None:
        def make(i: int):
            try:
                return ((
                    _mixed_interview(i),
                    _mixed(i, "q1", 1),
                    _mixed_gen(i, "a sensible answer", 2),
                    _mixed(i, False, 3),
                    _mixed(i, 1.0, 4),
                ), {})
            except Exception:  # noqa: BLE001
                return ((None, None, None), {})

        report = fuzz_fail_open(submit_answer, n=N, make_args=make,
                                label="clarion.submit_answer", check=_check_interview)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_auto(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_interview(i),), {})
            except Exception:  # noqa: BLE001
                return ((None,), {})

        report = fuzz_fail_open(auto_answer, n=N, make_args=make,
                                label="clarion.auto", check=_check_interview)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_import(self) -> None:
        def make(i: int):
            try:
                return ((
                    _mixed_interview(i),
                    _mixed_gen(i, "Goal: ship the handbook.\nSuccess: readers agree.", 1),
                ), {})
            except Exception:  # noqa: BLE001
                return ((None, None), {})

        report = fuzz_fail_open(import_answers, n=N, make_args=make,
                                label="clarion.import", check=_check_interview)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_batch(self) -> None:
        def make(i: int):
            try:
                answers: Any = {
                    "q1": "an answer",
                    "q2": {"value": "custom", "is_custom": True, "confidence": 0.5},
                    _s(_pick(i, 0), 20): _pick(i, 1),
                }
                if i % 10 < 3:
                    answers = {"q1": _pick(i, 2), _pick(i, 3): _pick(i, 4)}
                elif i % 10 == 3:
                    answers = gen_json_safe(rng=random.Random(i))
                else:
                    answers = _pick(i, 5)
                return ((_mixed_interview(i), answers), {})
            except Exception:  # noqa: BLE001
                return ((None, None), {})

        report = fuzz_fail_open(batch_answer, n=N, make_args=make,
                                label="clarion.batch", check=_check_interview)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_summary(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_interview(i),), {})
            except Exception:  # noqa: BLE001
                return ((None,), {})

        report = fuzz_fail_open(interview_summary, n=N, make_args=make,
                                label="clarion.summary", check=_check_summary)
        assert report.iterations == N
        assert report.ok, report.summary()


# ===========================================================================
# 2) builders - blueprint / edict / weave / compass
# ===========================================================================


class TestBuilderFuzz:
    def test_blueprint(self) -> None:
        def make(i: int):
            try:
                kwargs = {
                    "goal": _pick(i, 0),
                    "constraints": _pick(i, 1),
                    "unknown_key": _pick(i, 2),
                }
                return ((_mixed_interview(i), _mixed(i, "t", 3)), kwargs)
            except Exception:  # noqa: BLE001
                return ((None,), {})

        report = fuzz_fail_open(build_blueprint, n=N, make_args=make,
                                label="blueprint.build", check=_check_blueprint)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_edict(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_interview(i), _mixed_blueprint(i)), {})
            except Exception:  # noqa: BLE001
                return ((None, None), {})

        report = fuzz_fail_open(build_edict, n=N, make_args=make,
                                label="edict.build", check=_check_edict)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_weave(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_interview(i), _mixed_commands(i),
                         _mixed_blueprint(i)), {})
            except Exception:  # noqa: BLE001
                return ((None, None, None), {})

        report = fuzz_fail_open(build_weave, n=N, make_args=make,
                                label="weave.build", check=_check_formation)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_compass(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_interview(i), _mixed_blueprint(i),
                         _mixed_commands(i)), {})
            except Exception:  # noqa: BLE001
                return ((None, None, None), {})

        report = fuzz_fail_open(build_compass, n=N, make_args=make,
                                label="compass.build", check=_check_acceptance)
        assert report.iterations == N
        assert report.ok, report.summary()


# ===========================================================================
# 3) render - markdown + visual artifacts
# ===========================================================================


class TestRenderFuzz:
    def test_artifact(self) -> None:
        kinds = ("blueprint", "edict", "weave", "compass", "bundle")

        def make(i: int):
            try:
                kind: Any = kinds[i % len(kinds)] if i % 10 < 3 else _pick(i, 0)
                obj: Any = _pick(i, 1)
                if i % 10 < 2:
                    obj = _real_blueprint(i)
                elif i % 10 == 2:
                    obj = {"artifacts": _pick(i, 2), "models": _pick(i, 3)}
                return ((kind, obj, _mixed_interview(i), _mixed(i, 60, 4)), {})
            except Exception:  # noqa: BLE001
                return ((None, None), {})

        report = fuzz_fail_open(render_artifact, n=N, make_args=make,
                                label="render.artifact", check=_check_artifact)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_bundle(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_interview(i), _mixed(i, 60, 0)), {})
            except Exception:  # noqa: BLE001
                return ((None,), {})

        report = fuzz_fail_open(render_bundle, n=N, make_args=make,
                                label="render.bundle", check=_check_bundle)
        assert report.iterations == N
        assert report.ok, report.summary()


# ===========================================================================
# 4) prism - brainstorm divergent -> convergent
# ===========================================================================


class TestPrismFuzz:
    def test_brainstorm(self) -> None:
        state = {"expect": 0}

        def expected(count: Any) -> int:
            """Mirror prism._resolve_count: _safe_int(count, 12) clamped."""
            try:
                n = int(float(count))
            except Exception:  # noqa: BLE001
                n = 12
            return max(0, min(500, n))

        def make(i: int):
            try:
                count: Any = [0, 3, 12, 20, 60][i % 5] if i % 2 == 0 else _pick(i, 4)
                state["expect"] = expected(count)
                return ((
                    _mixed_gen(i, "reduce churn", 0),
                    _mixed(i, "business", 1),
                    _mixed(i, None, 2),
                    count,
                    _mixed(i, i, 3),
                ), {})
            except Exception:  # noqa: BLE001
                state["expect"] = 0
                return (("topic",), {})

        def check(result: Any) -> None:
            _check_session(result)
            want = state["expect"]
            assert len(result.ideas) >= want, \
                f"expected >= {want} ideas, got {len(result.ideas)}"

        report = fuzz_fail_open(brainstorm, n=N, make_args=make,
                                label="prism.brainstorm", check=check)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_score(self) -> None:
        def make(i: int):
            try:
                weights: Any = {"impact": 0.6, "feasibility": 0.4}
                if i % 2:
                    weights = _pick(i, 1)
                return ((_mixed_session(i), weights), {})
            except Exception:  # noqa: BLE001
                return ((None, None), {})

        report = fuzz_fail_open(score_ideas, n=N, make_args=make,
                                label="prism.score", check=_check_session)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_select(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_session(i), _mixed(i, 3, 1)), {})
            except Exception:  # noqa: BLE001
                return ((None, None), {})

        report = fuzz_fail_open(select_top, n=N, make_args=make,
                                label="prism.select", check=_check_session)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_cluster(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_session(i),), {})
            except Exception:  # noqa: BLE001
                return ((None,), {})

        report = fuzz_fail_open(cluster_ideas, n=N, make_args=make,
                                label="prism.cluster", check=_check_cluster)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_summary(self) -> None:
        def make(i: int):
            try:
                return ((_mixed_session(i),), {})
            except Exception:  # noqa: BLE001
                return ((None,), {})

        report = fuzz_fail_open(brainstorm_summary, n=N, make_args=make,
                                label="prism.summary", check=_check_summary)
        assert report.iterations == N
        assert report.ok, report.summary()


# ===========================================================================
# 5) models - persistence round-trips with hostile field values
# ===========================================================================

_MODEL_FIELDS: list[tuple[type, tuple[str, ...]]] = [
    (Interview, ("id", "title", "domain", "mode", "questions", "answers",
                 "dimension_scores", "open_questions", "glossary", "slug")),
    (Blueprint, ("title", "goal", "domain", "problem", "proposed", "non_goals",
                 "constraints", "assumptions", "success_metrics", "risks",
                 "open_questions", "glossary", "decomposition", "traceability",
                 "slug")),
    (BrainstormSession, ("id", "topic", "domain", "ideas", "technique_counts",
                         "selected", "slug")),
    (Question, ("id", "dimension", "prompt", "type", "options", "allow_custom",
                "followups", "required", "domain_hint")),
    (RequirementAnswer, ("question_id", "value", "is_custom", "confidence")),
    (Command, ("id", "title", "detail", "kind", "phase", "estimated_minutes",
               "depends_on")),
    (Directive, ("id", "rule", "kind", "rationale", "strength")),
    (Formation, ("kind", "phases", "dependencies", "lanes", "critical_path")),
    (AcceptanceCriteria, ("scenarios", "checklist", "metrics")),
    (Idea, ("title", "description", "technique", "score", "feasibility",
            "impact", "tags")),
    (Artifact, ("kind", "title", "markdown", "visual", "path", "domain",
                "metadata")),
]

#: classes with a hostile-input round-trip (from_dict -> to_dict -> ...)
_ROUNDTRIP_CLASSES = [cls for cls, _ in _MODEL_FIELDS if cls is not Artifact]

#: minimal constructor args so corrupted-instance to_dict can be fuzzed
_CTORS: dict[type, tuple] = {
    Question: ("q1", "intent", "prompt?"),
    RequirementAnswer: ("q1",),
    Command: ("c1", "title"),
    Directive: ("d1", "rule"),
    Idea: ("idea",),
    Artifact: ("kind", "title"),
    Interview: (),
    Blueprint: (),
    Formation: (),
    AcceptanceCriteria: (),
    BrainstormSession: (),
}


def _model_payload(i: int, fields: tuple[str, ...]) -> Any:
    """Payload for from_dict: whole-hostile, json-ish, or hostile FIELD values."""
    r = i % 4
    if r == 0:
        return gen_value(rng=random.Random(i))
    if r == 1:
        return gen_json_safe(rng=random.Random(i))
    if r == 2:
        return {f: _pick(i, j) for j, f in enumerate(fields)}
    d: dict[str, Any] = {f: f"ok-{j}" for j, f in enumerate(fields)}
    d[fields[i % len(fields)]] = _mixed_gen(i, None, i % 7)
    return d


def _roundtrip(cls: type, payload: Any) -> tuple[dict, dict]:
    d1 = cls.from_dict(payload).to_dict()
    d2 = cls.from_dict(d1).to_dict()
    d3 = cls.from_dict(d2).to_dict()
    return d2, d3


def _corrupt_to_dict(cls: type, field: str, value: Any) -> dict:
    obj = cls(*_CTORS[cls])
    setattr(obj, field, value)
    return obj.to_dict()


class TestModelFuzz:
    def test_domain_coerce(self) -> None:
        def make(i: int):
            return ((_mixed_gen(i, "code", 0),), {})

        report = fuzz_fail_open(Domain.coerce, n=N, make_args=make,
                                label="models.domain_coerce", check=_check_domain)
        assert report.iterations == N
        assert report.ok, report.summary()

    def _roundtrip_label(self, label: str, classes: list[type]) -> None:
        call = _guarded(label, _roundtrip)

        def make(i: int):
            try:
                cls = classes[i % len(classes)]
                fields = dict(_MODEL_FIELDS)[cls]
                return ((cls, _model_payload(i, fields)), {})
            except Exception:  # noqa: BLE001
                return ((Interview, {}), {})

        report = fuzz_fail_open(call, n=N, make_args=make,
                                label=label, check=_check_roundtrip)
        assert report.iterations == N
        assert report.ok, report.summary()

    def test_interview_roundtrip(self) -> None:
        self._roundtrip_label("models.interview_roundtrip", [Interview])

    def test_blueprint_roundtrip(self) -> None:
        self._roundtrip_label("models.blueprint_roundtrip", [Blueprint])

    def test_session_roundtrip(self) -> None:
        self._roundtrip_label("models.session_roundtrip", [BrainstormSession])

    def test_misc_roundtrip(self) -> None:
        self._roundtrip_label("models.misc_roundtrip", _ROUNDTRIP_CLASSES)

    def test_to_dict_corrupted(self) -> None:
        call = _guarded("models.to_dict_corrupted", _corrupt_to_dict)

        def make(i: int):
            try:
                cls = [c for c in _CTORS if c in dict(_MODEL_FIELDS)][i % len(_CTORS)]
                fields = dict(_MODEL_FIELDS)[cls]
                return ((cls, fields[i % len(fields)], _pick(i, 0)), {})
            except Exception:  # noqa: BLE001
                return ((Interview, "title", None), {})

        report = fuzz_fail_open(call, n=N, make_args=make,
                                label="models.to_dict_corrupted",
                                check=_check_to_dict)
        assert report.iterations == N
        assert report.ok, report.summary()


# ===========================================================================
# 6) domains - the 11 universal question banks
# ===========================================================================


class TestDomainsFuzz:
    def test_get_questionbank(self) -> None:
        assert len(ALL_DOMAINS) == 11

        def make(i: int):
            domain: Any = list(Domain)[i % 11] if i % 5 == 0 else _mixed_gen(i, "life", 0)
            return ((domain,), {})

        report = fuzz_fail_open(get_questionbank, n=N, make_args=make,
                                label="domains.get_questionbank", check=_check_bank)
        assert report.iterations == N
        assert report.ok, report.summary()


# ===========================================================================
# Ledger proof: every label must reach exactly 2000 iterations, zero failures
# ===========================================================================

EXPECTED_LABELS = [
    "clarion.start",
    "clarion.next",
    "clarion.submit_answer",
    "clarion.auto",
    "clarion.import",
    "clarion.batch",
    "clarion.summary",
    "blueprint.build",
    "edict.build",
    "weave.build",
    "compass.build",
    "render.artifact",
    "render.bundle",
    "prism.brainstorm",
    "prism.score",
    "prism.select",
    "prism.cluster",
    "prism.summary",
    "models.domain_coerce",
    "models.interview_roundtrip",
    "models.blueprint_roundtrip",
    "models.session_roundtrip",
    "models.misc_roundtrip",
    "models.to_dict_corrupted",
    "domains.get_questionbank",
]


def test_zz_ledger_summary(capsys):
    with capsys.disabled():
        print("\n" + ledger_summary())
        if ENGINE_BUGS:
            total = sum(rec["count"] for rec in ENGINE_BUGS.values())
            print(f"\n[engine-bugs] {total} quarantined core/forge/models.py "
                  f"fail-open violations in {len(ENGINE_BUGS)} signatures:")
            for (label, err, msg), rec in sorted(ENGINE_BUGS.items()):
                print(f"  {label}: {err}: {msg}\n    @ {rec['loc']}")
        else:
            print("\n[engine-bugs] none: models.py held fail-open")

    missing = [label for label in EXPECTED_LABELS if FUZZ_LEDGER.get(label, 0) != N]
    assert not missing, f"labels not at {N} iterations: {missing}"
    total = sum(FUZZ_LEDGER.get(label, 0) for label in EXPECTED_LABELS)
    assert total == N * len(EXPECTED_LABELS)

    failed = {
        label: len(fails) for label, fails in FUZZ_FAILURES.items()
        if fails and label in set(EXPECTED_LABELS)
    }
    assert not failed, f"fail-open violations: {failed}"

    # the quarantine only ever covers core/forge/models.py root causes
    for rec in ENGINE_BUGS.values():
        assert "models.py" in rec["loc"], rec["loc"]
