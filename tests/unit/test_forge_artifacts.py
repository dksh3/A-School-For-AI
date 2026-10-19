"""Unit tests for the Forge artifact builders + renderer (10x quality bar).

Covers ``build_blueprint`` / ``build_edict`` / ``build_weave`` /
``build_compass`` / ``render_artifact`` / ``render_bundle``: population,
ordering, dependency structure, Given/When/Then acceptance, universal
domains (WRITING, LIFE — not just CODING) and hard fail-open against
hostile input.

Temp files use ``tempfile.mkdtemp()`` + ``shutil.rmtree`` (OneDrive-safe;
never ``tmp_path``).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

import pytest

from core.forge.blueprint import build_blueprint
from core.forge.compass import build_compass
from core.forge.edict import Edict, build_edict
from core.forge.models import (
    AcceptanceCriteria,
    Artifact,
    Blueprint,
    Command,
    Domain,
    Formation,
    FormationKind,
    Interview,
    Question,
    RequirementAnswer,
)
from core.forge.render import (
    render_artifact,
    render_bundle,
    to_markdown_blueprint,
    to_markdown_bundle,
    to_markdown_compass,
    to_markdown_edict,
    to_markdown_weave,
)
from core.forge.weave import build_weave

# --- hostile objects --------------------------------------------------------

class _Evil:
    """Hostile object: __str__/__bool__/__hash__ all raise."""

    def __str__(self) -> str:
        raise RuntimeError("evil __str__")

    def __bool__(self) -> bool:
        raise RuntimeError("evil __bool__")

    def __hash__(self) -> int:
        raise RuntimeError("evil __hash__")


# --- fixtures ---------------------------------------------------------------

@pytest.fixture
def forge_tmp():
    d = tempfile.mkdtemp(prefix="forge_artifacts_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _q(qid: str, dim: str, prompt: str) -> Question:
    return Question(id=qid, dimension=dim, prompt=prompt)


def _a(qid: str, value: str, conf: float = 1.0) -> RequirementAnswer:
    return RequirementAnswer(question_id=qid, value=value, confidence=conf)


def make_interview(domain: Domain = Domain.WRITING,
                   title: str = "Launch Field Notes Newsletter") -> Interview:
    """A fully populated, domain-universal discovery interview."""
    questions = [
        _q("intent-goal", "intent", "What is the goal?"),
        _q("intent-problem", "intent", "What problem does it solve?"),
        _q("audience-1", "audience", "Who is it for?"),
        _q("scope-1", "scope", "What is in scope?"),
        _q("scope-2", "scope", "What else is in scope?"),
        _q("scope-3", "scope", "What is out of scope?"),
        _q("constraints-1", "constraints", "What constraints apply?"),
        _q("constraints-2", "constraints", "Any hard rules?"),
        _q("success-1", "success", "What does success look like?"),
        _q("success-2", "success", "How is it measured?"),
        _q("resources-1", "resources", "What resources exist?"),
        _q("risks-1", "risks", "What could go wrong?"),
        _q("sequence-1", "sequence", "In what order?"),
        _q("sequence-2", "sequence", "Then what?"),
        _q("style-1", "style", "What style rules apply?"),
        _q("edge-1", "edge_cases", "What edge cases matter?"),
        _q("glossary-1", "glossary", "Any terms?"),
        _q("open-1", "open_questions", "What is undecided?"),
    ]
    answers = [
        _a("intent-goal", "Goal: publish the Field Notes newsletter every Friday"),
        _a("intent-problem",
           "The problem: readers miss essays because publishing is irregular"),
        _a("audience-1", "Working designers"),
        _a("scope-1", "Draft and edit four founding essays (60 minutes)"),
        _a("scope-2", "Set up the mailing list and signup page"),
        _a("scope-3", "Out of scope: paid advertising and sponsorships"),
        _a("constraints-1", "Must not exceed 5 hours per week"),
        _a("constraints-2", "Always fact-check every claim"),
        _a("success-1", "Publish 4 issues with 95% on-time rate"),
        _a("success-2", "Reach 500 subscribers within 3 months"),
        _a("resources-1", "A shared editorial calendar"),
        _a("risks-1", "Contributors drop out mid-series"),
        _a("sequence-1", "Outline the essay series first (30 minutes)"),
        _a("sequence-2", "Draft each essay from the outline"),
        _a("style-1", "Prefer plain language over jargon"),
        _a("edge-1", "A scheduled issue has no finished draft"),
        _a("glossary-1", "Evergreen: an essay that stays useful over time"),
        _a("open-1", "Which platform hosts the archive?"),
    ]
    return Interview(
        id="itv-1",
        title=title,
        domain=domain,
        questions=questions,
        answers=answers,
        open_questions=["Should the newsletter be free forever?"],
        glossary={"Draft": "A complete but unpolished essay"},
    )


def make_interview_no_seq(domain: Domain = Domain.WRITING) -> Interview:
    """Interview without sequence answers → default domain phases apply."""
    itv = make_interview(domain=domain)
    itv.questions = [q for q in itv.questions if q.dimension != "sequence"]
    itv.answers = [a for a in itv.answers
                   if a.question_id not in ("sequence-1", "sequence-2")]
    return itv


def hostile_interview() -> Interview:
    """A real Interview mutated with hostile, wrong-typed payloads."""
    itv = Interview()
    itv.title = _Evil()
    itv.slug = _Evil()
    itv.domain = _Evil()
    itv.questions = [_Evil(), None, "junk", 42]
    itv.answers = [
        _Evil(),
        None,
        "not-an-answer",
        RequirementAnswer(question_id=_Evil(), value=_Evil(), confidence=_Evil()),
        RequirementAnswer(question_id="x", value={"a": _Evil()}, confidence=0.5),
    ]
    itv.open_questions = [_Evil(), None, 5]
    itv.glossary = {"k": _Evil()}
    itv.dimension_scores = {"intent": _Evil()}
    return itv


# === blueprint ==============================================================

def test_blueprint_populates_all_fields():
    bp = build_blueprint(make_interview())
    assert isinstance(bp, Blueprint)
    assert "field notes" in bp.goal.lower()
    assert "irregular" in bp.problem.lower()
    assert bp.proposed.startswith("Deliver the following")
    assert len(bp.constraints) >= 2
    assert bp.assumptions and bp.assumptions[0].startswith("Available:")
    assert len(bp.success_metrics) >= 2
    assert len(bp.risks) >= 1
    assert len(bp.open_questions) >= 2
    assert bp.glossary


def test_blueprint_title_parameter_wins():
    bp = build_blueprint(make_interview(), title="Custom Spec Title")
    assert bp.title == "Custom Spec Title"
    bp2 = build_blueprint(make_interview())
    assert bp2.title == "Launch Field Notes Newsletter"


def test_blueprint_overrides_replace_fields():
    bp = build_blueprint(
        make_interview(),
        goal="A different goal entirely",
        constraints=["Only work on Tuesdays", "No paid tools"],
        domain="research",
    )
    assert bp.goal == "A different goal entirely"
    assert bp.constraints == ["Only work on Tuesdays", "No paid tools"]
    assert bp.domain == Domain.RESEARCH


def test_blueprint_traceability_covers_every_answer():
    itv = make_interview()
    bp = build_blueprint(itv)
    assert bp.traceability
    seen = {t["question_id"] for t in bp.traceability}
    for a in itv.answers:
        assert a.question_id in seen
    goal_rows = [t for t in bp.traceability if t["question_id"] == "intent-goal"]
    assert goal_rows and "goal" in {t["lands_in"] for t in goal_rows}
    dims = {t["dimension"] for t in bp.traceability}
    assert "intent" in dims and "constraints" in dims


def test_blueprint_decomposition_from_scope():
    bp = build_blueprint(make_interview())
    assert len(bp.decomposition) == 2
    first = bp.decomposition[0]
    assert first["id"] == "wb-01"
    assert "founding essays" in first["title"].lower()
    assert first["source"] == "scope-1"
    assert first["order"] == 1


def test_blueprint_non_goals_from_exclusion_phrasing():
    bp = build_blueprint(make_interview())
    assert any("advertising" in x.lower() for x in bp.non_goals)
    assert all(not x.lower().startswith("out of scope") for x in bp.non_goals)


def test_blueprint_glossary_from_interview_and_answers():
    bp = build_blueprint(make_interview())
    terms = {k.lower(): v for k, v in bp.glossary.items()}
    assert "evergreen" in terms
    assert "stays useful" in terms["evergreen"]
    assert terms.get("draft") == "A complete but unpolished essay"


def test_blueprint_risks_have_shape_and_mitigation():
    bp = build_blueprint(make_interview())
    risk = bp.risks[0]
    assert {"risk", "impact", "mitigation", "source"} <= set(risk)
    assert "contributor" in risk["risk"].lower()
    assert risk["impact"] in {"low", "medium", "high"}
    assert risk["mitigation"]
    assert risk["source"] == "risks-1"


def test_blueprint_slug_and_domain():
    bp = build_blueprint(make_interview())
    assert bp.slug == "launch-field-notes-newsletter"
    assert bp.domain == Domain.WRITING
    assert bp.slug == _slug_of(bp.title)


def _slug_of(text: str) -> str:
    import re

    s = re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")
    return s[:64] or "item"


def test_blueprint_empty_interview_safe():
    bp = build_blueprint(Interview())
    assert isinstance(bp, Blueprint)
    assert bp.traceability == [] or isinstance(bp.traceability, list)
    assert build_blueprint(None).__class__ is Blueprint  # type: ignore[arg-type]


# === edict ==================================================================

def test_edict_return_type_and_unpacking():
    itv = make_interview()
    edict = build_edict(itv)
    assert isinstance(edict, Edict)
    assert isinstance(edict.commands, list) and isinstance(edict.directives, list)
    commands, directives = build_edict(itv)  # tuple-style unpacking
    assert [c.id for c in commands] == [c.id for c in edict.commands]
    assert [d.id for d in directives] == [d.id for d in edict.directives]


def test_edict_commands_stable_order_and_unique_ids():
    itv = make_interview()
    first = [c.id for c in build_edict(itv).commands]
    second = [c.id for c in build_edict(itv).commands]
    assert first == second  # stable + deterministic
    assert len(first) == len(set(first))
    kinds = [c.kind for c in build_edict(itv).commands]
    assert "setup" in kinds and "step" in kinds and "check" in kinds
    assert kinds.index("check") > kinds.index("step")
    assert kinds[-1] == "ship"


def test_edict_command_fields():
    edict = build_edict(make_interview())
    for c in edict.commands:
        assert c.id and c.title
        assert c.phase
        assert c.estimated_minutes > 0
        assert c.kind in {"step", "check", "setup", "ship", "learn"}
    titles = " ".join(c.title for c in edict.commands).lower()
    assert "founding essays" in titles
    assert any(c.title.lower().startswith("verify:") for c in edict.commands)


def test_edict_directives_kinds():
    edict = build_edict(make_interview())
    kinds = {d.kind for d in edict.directives}
    assert {"always", "never", "prefer"} <= kinds
    for d in edict.directives:
        assert d.id and d.rule
        assert 0.0 <= d.strength <= 1.0
    prefer = [d for d in edict.directives if d.kind == "prefer"]
    assert any("plain language" in d.rule.lower() for d in prefer)


def test_edict_never_directive_strips_negation():
    edict = build_edict(make_interview())
    never = [d for d in edict.directives if d.kind == "never"]
    assert never
    assert any(d.rule.lower().startswith("exceed 5 hours") for d in never)
    always = [d for d in edict.directives if d.kind == "always"]
    assert any(d.rule.lower().startswith("fact-check") for d in always)


def test_edict_dependencies_resolvable_and_chained():
    edict = build_edict(make_interview())
    ids = {c.id for c in edict.commands}
    assert ids
    chained = False
    for c in edict.commands:
        for dep in c.depends_on:
            assert dep in ids  # every dependency resolves
            assert dep != c.id
            chained = True
    assert chained
    ship = [c for c in edict.commands if c.kind == "ship"][0]
    checks = [c for c in edict.commands if c.kind == "check"]
    assert set(ship.depends_on) == {c.id for c in checks}


def test_edict_estimated_minutes_parsed():
    edict = build_edict(make_interview())
    step = [c for c in edict.commands if "founding essays" in c.title][0]
    assert step.estimated_minutes == 60
    setup = [c for c in edict.commands if c.kind == "setup"][0]
    assert setup.estimated_minutes > 0


def test_edict_with_blueprint_adds_guardrails():
    bp = Blueprint(title="Guarded", constraints=["Never share raw survey data"],
                   non_goals=["A paid tier"])
    edict = build_edict(make_interview_no_seq(), blueprint=bp)
    never = [d for d in edict.directives if d.kind == "never"]
    avoid = [d for d in edict.directives if d.kind == "avoid"]
    assert any("share raw survey data" in d.rule.lower() for d in never)
    assert any("paid tier" in d.rule.lower() for d in avoid)


def test_edict_excludes_out_of_scope_items():
    edict = build_edict(make_interview())
    titles = " ".join(c.title for c in edict.commands).lower()
    assert "advertising" not in titles  # non-goals never become work steps
    assert sum(1 for c in edict.commands if c.kind == "step") == 2


def test_edict_dedupes_blueprint_overlap():
    itv = make_interview()
    bp = build_blueprint(itv)  # shares constraints with the interview
    edict = build_edict(itv, blueprint=bp)
    rules = [(d.kind, d.rule.lower()) for d in edict.directives]
    assert len(rules) == len(set(rules))
    acc = build_compass(itv, blueprint=bp)
    measures = [m["measure"].lower() for m in acc.metrics]
    assert len(measures) == len(set(measures))


def test_edict_empty_interview_safe():
    edict = build_edict(Interview())
    assert isinstance(edict, Edict)
    assert isinstance(edict.to_dict(), dict)
    assert edict.to_markdown().startswith("#")
    assert isinstance(build_edict(None).commands, list)  # type: ignore[arg-type]


# --- exact phase-count constraints (D-02 regression) ------------------------

def _ordered_phases(edict: Edict) -> list[str]:
    seen: list[str] = []
    for c in edict.commands:
        if c.phase not in seen:
            seen.append(c.phase)
    return seen


def test_edict_exact_phase_count_honored():
    """D-02: an "exactly N phases" constraint must survive the generator.
    The old plan force-appended Verify/Deliver and emitted 4 phases against
    an EXACTLY-3 directive (Campaign A near-loss)."""
    itv = make_interview()
    itv.answers.append(_a("constraints-1", "EXACTLY 3 phases for the plan"))
    phases = _ordered_phases(build_edict(itv))
    assert len(phases) == 3, f"exactly-3 constraint violated: {phases}"
    assert phases[:2] == ["Outline the essay series first (30 minutes)",
                          "Draft each essay from the outline"]


def test_edict_exact_phase_count_pads_to_n():
    itv = make_interview_no_seq()
    itv.answers.append(_a("constraints-1", "exactly 5 phases"))
    phases = _ordered_phases(build_edict(itv))
    assert len(phases) == 5, phases


def test_edict_exact_phase_count_trims_to_n():
    itv = make_interview()
    itv.answers.append(_a("constraints-2", "2 phases — no more"))
    phases = _ordered_phases(build_edict(itv))
    assert len(phases) == 2, phases


def test_edict_exact_phase_count_from_blueprint():
    bp = build_blueprint(make_interview_no_seq())
    bp.constraints = ["Exactly 4 phases, no extras"]
    phases = _ordered_phases(build_edict(make_interview_no_seq(), blueprint=bp))
    assert len(phases) == 4, phases


def test_edict_exact_phase_count_edges():
    one = make_interview_no_seq()
    one.answers.append(_a("constraints-1", "exactly 1 phase"))
    assert len(_ordered_phases(build_edict(one))) == 1
    many = make_interview_no_seq()
    many.answers.append(_a("constraints-1", "exactly 9 phases"))
    assert len(_ordered_phases(build_edict(many))) == 8  # clamped


def test_edict_without_count_constraint_unchanged():
    """No count constraint → the safety append still adds Verify/Deliver."""
    phases = _ordered_phases(build_edict(make_interview()))
    assert phases[:2] == ["Outline the essay series first (30 minutes)",
                          "Draft each essay from the outline"]
    assert phases[-2:] == ["Verify", "Deliver"]


# === weave ==================================================================

def test_weave_phases_grouped_with_milestones():
    edict = build_edict(make_interview())
    f = build_weave(make_interview(), edict.commands)
    assert isinstance(f, Formation)
    assert f.phases
    phase_names = {p["name"] for p in f.phases}
    for c in edict.commands:
        assert c.phase in phase_names
    for p in f.phases:
        assert p["milestone"]
        assert isinstance(p["commands"], list) and p["commands"]
        assert p["estimated_minutes"] > 0


def test_weave_dependencies_from_depends_on():
    edict = build_edict(make_interview())
    f = build_weave(make_interview(), edict.commands)
    assert f.dependencies
    ids = {c.id for c in edict.commands}
    for a, b in f.dependencies:
        assert a in ids and b in ids
    expected = {(dep, c.id) for c in edict.commands for dep in c.depends_on}
    assert set(f.dependencies) <= expected


def test_weave_critical_path_longest_chain():
    cmds = [
        Command(id="a", title="A", phase="One", estimated_minutes=10),
        Command(id="b", title="B", phase="One", estimated_minutes=5,
                depends_on=["a"]),
        Command(id="c", title="C", phase="Two", estimated_minutes=20,
                depends_on=["b"]),
        Command(id="d", title="D", phase="Two", estimated_minutes=40,
                depends_on=["a"]),
    ]
    f = build_weave(make_interview(), cmds)
    assert f.critical_path == ["a", "d"]  # 50 min beats 35 min
    assert f.kind == FormationKind.CRITICAL_PATH


def test_weave_lanes_partition_commands():
    cmds = [
        Command(id="a", title="A", phase="One", estimated_minutes=10),
        Command(id="b", title="B", phase="One", estimated_minutes=5,
                depends_on=["a"]),
        Command(id="c", title="C", phase="Two", estimated_minutes=20,
                depends_on=["b"]),
        Command(id="d", title="D", phase="Two", estimated_minutes=40,
                depends_on=["a"]),
    ]
    f = build_weave(make_interview(), cmds)
    assert len(f.lanes) == 3
    assert f.lanes[0]["commands"] == ["a"]
    assert set(f.lanes[1]["commands"]) == {"b", "d"}
    assert f.lanes[2]["commands"] == ["c"]
    union = [c for lane in f.lanes for c in lane["commands"]]
    assert sorted(union) == ["a", "b", "c", "d"]
    assert f.lanes[1]["can_start"] == "when Lane 1 completes"


def test_weave_kind_selection():
    f = build_weave(make_interview(), [Command(id="only", title="Solo", phase="One")])
    assert f.kind == FormationKind.PHASES
    assert f.critical_path == ["only"]
    f2 = build_weave(make_interview(), build_edict(make_interview()).commands)
    assert f2.kind == FormationKind.CRITICAL_PATH


def test_weave_infers_commands_when_missing():
    f = build_weave(make_interview())
    assert f.phases and f.dependencies
    assert f.critical_path


def test_weave_from_dict_commands():
    f = build_weave(make_interview(), [
        {"id": "a", "title": "A", "phase": "One", "estimated_minutes": 5},
        {"id": "b", "title": "B", "phase": "Two", "estimated_minutes": 7,
         "depends_on": ["a"]},
    ])
    assert f.dependencies == [("a", "b")]
    assert f.critical_path == ["a", "b"]
    assert f.kind == FormationKind.CRITICAL_PATH


# === compass ================================================================

def test_compass_scenarios_have_gwt():
    acc = build_compass(make_interview())
    assert isinstance(acc, AcceptanceCriteria)
    assert len(acc.scenarios) == 3  # 2 success + 1 edge
    for s in acc.scenarios:
        assert {"given", "when", "then"} <= set(s)
        assert s["given"] and s["when"] and s["then"]
    happy = [s for s in acc.scenarios if s["id"].startswith("happy")]
    assert len(happy) == 2
    assert any("working designers" in s["given"].lower() for s in happy)
    assert any("field notes" in s["given"].lower() for s in happy)


def test_compass_edge_scenarios():
    acc = build_compass(make_interview())
    edges = [s for s in acc.scenarios if s["id"].startswith("edge")]
    assert len(edges) == 1
    assert "no finished draft" in edges[0]["given"]
    assert "handled" in edges[0]["then"].lower()
    assert edges[0]["source"] == "edge-1"


def test_compass_checklist():
    acc = build_compass(make_interview())
    assert acc.checklist
    constraints = [c for c in acc.checklist if c.startswith("Constraint holds")]
    successes = [c for c in acc.checklist if c.startswith("Success demonstrated")]
    assert len(constraints) == 2
    assert len(successes) == 2
    assert all(isinstance(c, str) and c for c in acc.checklist)


def test_compass_metrics_targets():
    acc = build_compass(make_interview())
    assert len(acc.metrics) == 2
    subs = [m for m in acc.metrics if "subscribers" in m["measure"].lower()]
    assert subs
    assert subs[0]["target"] == 500
    assert subs[0]["unit"] == "subscribers"
    assert subs[0]["direction"] == "increase"
    for m in acc.metrics:
        assert {"name", "target", "unit", "direction", "measure", "source"} <= set(m)


def test_compass_with_blueprint_and_commands():
    itv = make_interview()
    bp = build_blueprint(itv)
    edict = build_edict(itv, bp)
    acc = build_compass(itv, blueprint=bp, commands=edict.commands)
    phase_gates = [c for c in acc.checklist if c.startswith("All ")]
    assert len(phase_gates) >= 2
    assert any("complete" in c for c in phase_gates)
    assert any("open questions" in c.lower() for c in acc.checklist)


# === render =================================================================

@pytest.mark.parametrize("kind", ["blueprint", "edict", "weave", "compass", "bundle"])
def test_render_artifact_each_kind(kind):
    itv = make_interview()
    objs = {
        "blueprint": build_blueprint(itv),
        "edict": build_edict(itv),
        "weave": build_weave(itv),
        "compass": build_compass(itv),
        "bundle": {"artifacts": render_bundle(itv)},
    }
    art = render_artifact(kind, objs[kind], itv, width=60)
    assert isinstance(art, Artifact)
    assert art.kind == kind
    assert art.markdown.strip() and art.visual.strip()
    assert art.title
    assert art.path.endswith(f"{kind}.md")
    assert art.domain == "writing"


def test_render_artifact_markdown_sections():
    itv = make_interview()
    bp_md = to_markdown_blueprint(build_blueprint(itv), itv)
    for heading in ("# Blueprint", "## Goal", "## Problem", "## Proposed Solution",
                    "## Work Breakdown", "## Non-Goals", "## Constraints",
                    "## Success Metrics", "## Risks", "## Open Questions",
                    "## Glossary", "## Traceability"):
        assert heading in bp_md
    edict_md = to_markdown_edict(build_edict(itv), itv)
    assert "## Commands" in edict_md and "## Directives" in edict_md
    assert "### Never" in edict_md
    weave_md = to_markdown_weave(build_weave(itv), itv)
    for heading in ("## Phases", "## Dependencies", "## Parallel Lanes",
                    "## Critical Path"):
        assert heading in weave_md
    compass_md = to_markdown_compass(build_compass(itv), itv)
    for heading in ("## Scenarios", "## Checklist", "## Metrics"):
        assert heading in compass_md
    assert "**Given**" in compass_md and "- [ ]" in compass_md
    bundle_md = to_markdown_bundle({"artifacts": render_bundle(itv)}, itv)
    assert "## Contents" in bundle_md and "## The Forge Pipeline" in bundle_md


def test_render_artifact_visuals_attached():
    itv = make_interview()
    cases = {
        "blueprint": (build_blueprint(itv), "coverage"),
        "edict": (build_edict(itv), "Commands per phase"),
        "weave": (build_weave(itv), "Phase timeline"),
        "compass": (build_compass(itv), "Checklist completion"),
    }
    for kind, (obj, needle) in cases.items():
        art = render_artifact(kind, obj, itv, width=60)
        assert art.visual.strip()
        assert needle.lower() in art.visual.lower()


def test_render_artifact_garbage_never_raises():
    art = render_artifact(_Evil(), _Evil(), interview=_Evil(), width=_Evil())
    assert isinstance(art, Artifact)
    assert art.markdown.strip() and art.visual.strip()
    art2 = render_artifact("blueprint", None, interview=None, width=0)
    assert isinstance(art2, Artifact) and art2.markdown.strip()
    art3 = render_artifact("totally-unknown", {"x": 1})
    assert isinstance(art3, Artifact) and art3.visual.strip()
    art4 = render_artifact("weave", "garbage-string", interview=123)
    assert isinstance(art4, Artifact) and art4.markdown.strip()


def test_render_bundle_five_artifacts():
    arts = render_bundle(make_interview())
    assert set(arts) == {"blueprint", "edict", "weave", "compass", "bundle"}
    for kind, art in arts.items():
        assert isinstance(art, Artifact)
        assert art.kind == kind
        assert art.markdown.strip() and art.visual.strip()
        assert art.metadata is not None
    assert arts["bundle"].markdown.count("|") > 5  # index table rendered


def test_render_bundle_roundtrip_files(forge_tmp):
    arts = render_bundle(make_interview())
    for kind, art in arts.items():
        md_path = os.path.join(forge_tmp, f"{kind}.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(art.markdown + "\n\n```\n" + art.visual + "\n```\n")
        assert os.path.getsize(md_path) > 0
        json_path = os.path.join(forge_tmp, f"{kind}.json")
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(art.to_dict(), fh)
        with open(json_path, encoding="utf-8") as fh:
            back = json.load(fh)
        assert back["kind"] == kind
        assert back["markdown"].strip()


def test_blueprint_dict_roundtrip(forge_tmp):
    bp = build_blueprint(make_interview())
    path = os.path.join(forge_tmp, "bp.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bp.to_dict(), fh)
    with open(path, encoding="utf-8") as fh:
        back = Blueprint.from_dict(json.load(fh))
    assert back.title == bp.title
    assert back.glossary == bp.glossary
    assert len(back.decomposition) == len(bp.decomposition)


# === universal ==============================================================

def test_universal_writing_domain():
    itv = make_interview(domain=Domain.WRITING)
    bp = build_blueprint(itv)
    assert bp.domain == Domain.WRITING
    md = to_markdown_blueprint(bp, itv)
    assert "**Domain:** Writing" in md
    assert "coding" not in md.lower()
    edict = build_edict(make_interview_no_seq(domain=Domain.WRITING))
    phases = {c.phase for c in edict.commands}
    assert {"Outline", "Draft", "Revise"} & phases
    assert "Publish" in phases


def test_universal_life_domain():
    itv = make_interview(domain=Domain.LIFE, title="Run a household move")
    bp = build_blueprint(itv)
    assert bp.domain == Domain.LIFE
    assert "field notes" in bp.goal.lower()  # derived from answers, not domain
    edict = build_edict(make_interview_no_seq(domain=Domain.LIFE))
    phases = {c.phase for c in edict.commands}
    assert {"Plan", "Act"} <= phases
    arts = render_bundle(itv)
    assert "**Domain:** Life" in arts["blueprint"].markdown
    assert all(art.markdown.strip() for art in arts.values())


# === fail-open ==============================================================

def test_hostile_interview_builders_never_raise():
    itv = hostile_interview()
    bp = build_blueprint(itv)
    assert isinstance(bp, Blueprint)
    edict = build_edict(itv)
    assert isinstance(edict, Edict)
    f = build_weave(itv)
    assert isinstance(f, Formation)
    acc = build_compass(itv)
    assert isinstance(acc, AcceptanceCriteria)
    assert isinstance(bp.to_dict(), dict)
    assert isinstance(edict.to_dict(), dict)
    assert isinstance(f.to_dict(), dict)
    assert isinstance(acc.to_dict(), dict)


def test_hostile_interview_renderers_never_raise():
    itv = hostile_interview()
    for kind in ("blueprint", "edict", "weave", "compass", "bundle"):
        obj = {
            "blueprint": build_blueprint(itv),
            "edict": build_edict(itv),
            "weave": build_weave(itv),
            "compass": build_compass(itv),
            "bundle": None,
        }[kind]
        art = render_artifact(kind, obj, itv, width=_Evil())
        assert isinstance(art, Artifact)
        assert art.markdown.strip() and art.visual.strip()
    arts = render_bundle(itv)
    assert set(arts) == {"blueprint", "edict", "weave", "compass", "bundle"}
    for art in arts.values():
        assert art.markdown.strip() and art.visual.strip()
        json.dumps(art.to_dict())  # metadata stays JSON-safe


def test_wrong_typed_answers_and_collections():
    itv = make_interview()
    itv.answers = "not-a-list"  # type: ignore[assignment]
    itv.questions = {"not": "a list"}  # type: ignore[assignment]
    itv.glossary = ["junk"]  # type: ignore[assignment]
    itv.open_questions = _Evil()  # type: ignore[assignment]
    bp = build_blueprint(itv)
    assert isinstance(bp, Blueprint)
    edict = build_edict(itv)
    assert isinstance(edict, Edict)
    f = build_weave(itv, commands={"bad": "shape"})
    assert isinstance(f, Formation)
    acc = build_compass(itv, blueprint="not-a-blueprint", commands=[_Evil()])
    assert isinstance(acc, AcceptanceCriteria)
    art = render_artifact("edict", ("bad", "tuple"), itv)
    assert isinstance(art, Artifact) and art.markdown.strip()


def test_hostile_answer_values_never_raise():
    itv = make_interview()
    itv.answers = [
        RequirementAnswer(question_id="intent-goal", value=_Evil()),
        RequirementAnswer(question_id=_Evil(), value=[_Evil(), None, 3]),
        RequirementAnswer(question_id="success-1", value=12345),
        RequirementAnswer(question_id="constraints-1", value=("a", "b")),
    ]
    bp = build_blueprint(itv)
    assert isinstance(bp, Blueprint)
    assert bp.goal == "" or isinstance(bp.goal, str)
    acc = build_compass(itv)
    assert isinstance(acc, AcceptanceCriteria)
    art = render_artifact("blueprint", bp, itv)
    assert art.markdown.strip()


def test_empty_interview_render_bundle():
    arts = render_bundle(Interview())
    assert set(arts) == {"blueprint", "edict", "weave", "compass", "bundle"}
    for art in arts.values():
        assert isinstance(art, Artifact)
        assert art.markdown.strip() and art.visual.strip()
    assert "_Not yet specified._" in arts["blueprint"].markdown
