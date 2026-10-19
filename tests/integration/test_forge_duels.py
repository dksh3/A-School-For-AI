"""Competitive duels: Forge (universal Idea->Artifact) vs superpowers.

Each duel proves the Forge engine beats the superpowers brainstorming skill it
replaces on measurable criteria: adaptive scored discovery (12 dimensions vs
one static question), five distinct artifacts per interview vs a single design
doc, 11 domains vs coding-only, four interview modes vs one, and divergent
brainstorm breadth (>=5 techniques vs 2-3 approaches).

The baseline simulator models only the *documented* superpowers contract
(static one-question-at-a-time path -> 2-3 approaches -> one design doc) so
every comparison is deterministic and offline. Scratch dirs come from
``tempfile.mkdtemp()`` (OneDrive-safe; never ``tmp_path``).
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import pytest

from core.forge.blueprint import build_blueprint
from core.forge.clarion import (
    DONE_COVERAGE,
    auto_answer,
    batch_answer,
    import_answers,
    interview_summary,
    next_question,
    start_interview,
    submit_answer,
)
from core.forge.compass import build_compass
from core.forge.domains import get_questionbank
from core.forge.edict import build_edict
from core.forge.models import Domain, InterviewMode, QuestionType
from core.forge.prism import brainstorm, cluster_ideas, select_top
from core.forge.render import render_bundle
from core.forge.weave import build_weave

# ---------------------------------------------------------------------------
# Baseline simulator: the documented superpowers brainstorming contract
# ---------------------------------------------------------------------------


def baseline_superpowers_brainstorm(task: str) -> dict[str, object]:
    """superpowers' brainstorming skill: one static question, then 2-3
    approaches and a single design doc. No scoring, no branching, no domains,
    no modes, no persistence, no artifacts beyond the doc."""
    return {
        "questions": ["What are you trying to build?"],
        "approaches": ["Approach A", "Approach B"],
        "design_doc": f"# Design: {task}\n\nUse approach A.",
    }


#: What the baseline can produce, counted for the scoreboard.
BASELINE_ARTIFACTS = 1          # one design doc
BASELINE_TECHNIQUES_MAX = 3     # "2-3 approaches"
BASELINE_DOMAINS = 1            # coding-only
BASELINE_MODES = 1              # single static path
BASELINE_DIMENSIONS = 1         # one question

#: The 12 discovery dimensions clarion scores (mirrors core.forge.models).
DIMENSIONS = (
    "intent", "audience", "scope", "constraints", "success",
    "resources", "risks", "sequence", "style", "edge_cases",
    "glossary", "open_questions",
)

#: Words that betray a coding-only tool. Universal artifacts must avoid all.
CODING_ONLY_RE = re.compile(
    r"\b(code|coded|coder|coding|codebase|repo|repository|git|github|commit|"
    r"compile|compiler|debug|refactor|bugfix|bug|patch|deploy|deployment|"
    r"runtime|pytest|unittest|unit test|pull request|api|sdk|database|"
    r"frontend|backend|javascript|typescript|python|npm|docker|kubernetes|"
    r"software|programming|stack|test|tests|testing)\b",
    re.IGNORECASE,
)

#: Writing-domain answers used by several duels (no coding vocabulary).
WRITING_ANSWERS = {
    "intent": "Draft and publish a cosy mystery novel for avid readers",
    "audience": "Beta readers and fans of cosy mysteries",
    "scope": "Full manuscript, revision passes, and a launch plan",
    "constraints": "Write 500 words per day; never skip the revision pass",
    "success": "Beta readers finish the cosy mystery novel and ask for the sequel",
    "resources": "An existing outline and two quiet hours each morning",
    "risks": "A sagging middle act; mitigate with an early outline review",
    "sequence": "Outline before drafting; drafting before revision",
    "style": "Warm, conversational, character-first prose",
    "edge_cases": "If a beta reader goes quiet, assume feedback after two weeks",
    "glossary": "Cosy means a gentle mystery without gore",
    "open_questions": "Whether to publish under a pen name",
}

#: (domain, title, answers, marker phrase that must appear in the artifacts)
UNIVERSAL_CASES = [
    (
        Domain.LIFE,
        "Morning running habit",
        {
            "intent": "Build a morning running habit that reaches the big race",
            "audience": "Just me and my running buddy",
            "scope": "A weekly plan, rest days, and a simple journal",
            "constraints": "Run before sunrise; never skip the rest day",
            "success": "I finish the spring half marathon feeling strong",
            "resources": "Good shoes, a nearby trail, and early mornings",
            "risks": "Shin splints; ease the mileage slowly",
            "sequence": "Base miles before any speed work",
            "style": "Simple, encouraging, no jargon",
            "edge_cases": "If travel interrupts, a hotel workout keeps the streak",
            "glossary": "Tempo means a comfortably hard run",
            "open_questions": "Whether to join a running club",
        },
        "spring half marathon",
    ),
    (
        Domain.WRITING,
        "Cosy mystery novel",
        WRITING_ANSWERS,
        "cosy mystery novel",
    ),
    (
        Domain.BUSINESS,
        "Subscription bakery retention",
        {
            "intent": "Reduce churn and grow the monthly bread box",
            "audience": "Neighbors on the monthly bread plan",
            "scope": "A retention plan, warmer onboarding, and monthly feedback",
            "constraints": "Stay within the current marketing budget",
            "success": "Monthly churn for the subscription bakery drops below 5 percent",
            "resources": "Sales records, the bakers' time, and the newsletter",
            "risks": "Wrong direction and rework; run a small pilot first",
            "sequence": "Listen to churned subscribers before changing the box",
            "style": "Plain, warm, and specific",
            "edge_cases": "A delivery delay; send a make-good before the next box",
            "glossary": "Churn means subscribers who cancel each month",
            "open_questions": "Whether an annual plan reduces churn",
        },
        "subscription bakery",
    ),
    (
        Domain.CREATIVE,
        "Community mural downtown",
        {
            "intent": "Paint the neighborhood mural on the old granary wall",
            "audience": "The neighborhood and the arts council",
            "scope": "Sketches, volunteer paint days, and a small unveiling",
            "constraints": "Use weatherproof paint; never block the bakery deliveries",
            "success": "The community mural is unveiled at a full block party",
            "resources": "Volunteer painters, donated paint, and scaffolding",
            "risks": "Rain delays; keep a flexible weekend buffer",
            "sequence": "Sketch approval before any paint touches the wall",
            "style": "Bold, colorful, welcoming to everyone",
            "edge_cases": "If a volunteer day is rained out, reschedule within the week",
            "glossary": "Muralist means the lead artist on the wall",
            "open_questions": "Whether the wall needs a primer first",
        },
        "community mural",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def worktree():
    """Isolated scratch dir via tempfile.mkdtemp (not tmp_path: OneDrive-safe)."""
    d = Path(tempfile.mkdtemp(prefix="forge_duel_"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _answer_all(interview, answers: dict[str, str] | None = None):
    """Answer every question in the bank, then any followups that branch."""
    answers = answers or {}
    fallback = "A clear and sensible answer for this discovery step."
    for q in list(interview.questions):
        if q.id not in interview.answer_map():
            submit_answer(interview, q.id, answers.get(q.dimension, fallback))
    for _ in range(50):  # surfaced followups (interview mode would stop early)
        q = next_question(interview)
        if q is None:
            break
        submit_answer(interview, q.id, answers.get(q.dimension, fallback))
    return interview


def _answered_dimensions(interview) -> set[str]:
    amap = interview.answer_map()
    return {q.dimension for q in interview.questions if q.id in amap}


# ---------------------------------------------------------------------------
# Duel 1: adaptive scored interview vs single-path brainstorm
# ---------------------------------------------------------------------------


class TestForgeVsSuperpowers:
    """Forge's clarion interview is adaptive, scored, branching, and pick-one-
    or-custom; superpowers asks one static question and stops."""

    def test_interview_covers_all_12_dimensions(self):
        iv = start_interview("Cosy mystery novel", Domain.WRITING)
        _answer_all(iv, WRITING_ANSWERS)

        assert len(DIMENSIONS) == 12
        assert _answered_dimensions(iv) == set(DIMENSIONS)
        assert iv.coverage() == 1.0
        # every dimension carries a score, not just a yes/no asked-state
        assert set(iv.dimension_scores) == set(DIMENSIONS)
        assert all(0.0 <= s <= 1.0 for s in iv.dimension_scores.values())

        base = baseline_superpowers_brainstorm("a novel")
        assert len(base["questions"]) == BASELINE_DIMENSIONS
        assert "dimension_scores" not in base

    def test_interview_adapts_to_answers(self):
        # (a) weakest-dimension targeting: answering one dimension at full
        # confidence boosts it out of the rotation, so the very next question
        # moves to a strictly weaker dimension.
        iv = start_interview("Cosy mystery novel", Domain.WRITING)
        q1 = next_question(iv)
        assert q1 is not None
        assert iv.dimension_scores[q1.dimension] == pytest.approx(0.5)

        submit_answer(iv, q1.id, "a fully custom discovery answer",
                      is_custom=True, confidence=1.0)
        assert iv.dimension_scores[q1.dimension] == pytest.approx(0.75)

        q2 = next_question(iv)
        assert q2 is not None
        assert q2.dimension != q1.dimension
        assert iv.dimension_scores[q2.dimension] < iv.dimension_scores[q1.dimension]

        # (b) the question sequence depends on what was answered: two
        # identical interviews diverge when different questions go first.
        iv_a = start_interview("Cosy mystery novel", Domain.WRITING)
        iv_b = start_interview("Cosy mystery novel", Domain.WRITING)
        submit_answer(iv_a, next_question(iv_a).id, "a fully custom discovery answer")
        submit_answer(iv_b, iv_b.questions[2].id, "zeta-unique-answer", is_custom=True)
        assert next_question(iv_a).id != next_question(iv_b).id

        # baseline is static: the same question every time
        base = baseline_superpowers_brainstorm("a novel")
        assert base["questions"] == baseline_superpowers_brainstorm("other")["questions"]

    def test_choice_accepts_pick_one_or_custom(self):
        iv_pick = start_interview("Cosy mystery novel", Domain.WRITING)
        iv_custom = start_interview("Cosy mystery novel", Domain.WRITING)
        choice = next(
            q for q in iv_pick.questions
            if q.type == QuestionType.CHOICE and q.options and q.allow_custom
        )

        # pick one of the listed options
        submit_answer(iv_pick, choice.id, choice.options[0], is_custom=False)
        picked = iv_pick.answer_map()[choice.id]
        assert picked.value == choice.options[0]
        assert picked.is_custom is False

        # or supply your own: the escape hatch is first-class
        submit_answer(iv_custom, choice.id, "my own unlisted option",
                      is_custom=True, confidence=0.9)
        custom = iv_custom.answer_map()[choice.id]
        assert custom.value == "my own unlisted option"
        assert custom.is_custom is True
        assert interview_summary(iv_custom)["answered_count"] == 1

    def test_interview_terminates_at_coverage_threshold(self):
        assert DONE_COVERAGE == 0.85
        iv = start_interview("Plan a community festival", Domain.PLANNING)
        steps = 0
        while next_question(iv) is not None:
            submit_answer(iv, next_question(iv).id,
                          "A sensible plan answer for this discovery step.")
            steps += 1
            assert steps < 300, "interview failed to terminate"

        assert next_question(iv) is None
        assert iv.coverage() >= DONE_COVERAGE
        assert len(iv.answers) >= 11

    # -- duel 2: five artifacts from ONE interview -------------------------

    def test_five_artifacts_from_one_interview(self, worktree):
        iv = start_interview("Cosy mystery novel", Domain.WRITING)
        _answer_all(iv, WRITING_ANSWERS)

        # 1) blueprint: the design spec
        bp = build_blueprint(iv)
        assert bp.title and bp.goal and bp.problem and bp.proposed
        assert bp.constraints and bp.success_metrics and bp.risks
        assert bp.decomposition and bp.decomposition[0]["title"]
        assert bp.traceability and len(bp.traceability) >= 10

        # 2) edict: commands AND directives
        commands, directives = build_edict(iv, bp)
        assert len(commands) >= 3
        assert {"check", "ship"} <= {c.kind for c in commands}
        assert all(c.id and c.title for c in commands)
        assert directives
        assert all(d.rule for d in directives)

        # 3) weave: phases + dependencies + parallel lanes + critical path
        weave = build_weave(iv, commands, bp)
        assert weave.phases and weave.phases[0]["name"]
        assert weave.dependencies
        assert weave.lanes and len(weave.lanes) >= 2
        assert weave.critical_path
        assert all(step in {c.id for c in commands} for step in weave.critical_path)

        # 4) compass: Given/When/Then + checklist + metrics
        compass = build_compass(iv, bp, commands)
        assert compass.scenarios
        for scen in compass.scenarios:
            assert scen["given"] and scen["when"] and scen["then"]
        assert compass.checklist
        assert compass.metrics
        assert all("measure" in m or "name" in m for m in compass.metrics)

        # 5) bundle: renders all of the above at once
        bundle = render_bundle(iv, width=60)
        assert set(bundle) == {"blueprint", "edict", "weave", "compass", "bundle"}
        for kind, art in bundle.items():
            assert art.kind == kind
            assert art.markdown.strip() and art.visual.strip()
            assert art.path.startswith(".school/forge/")
            assert art.domain == Domain.WRITING.value

        # artifacts are deliverables: they persist to their promised paths
        for art in bundle.values():
            target = worktree / art.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(art.markdown, encoding="utf-8")
            assert target.read_text(encoding="utf-8") == art.markdown

        # baseline produces exactly one artifact: a design doc
        base = baseline_superpowers_brainstorm("a novel")
        assert set(base) == {"questions", "approaches", "design_doc"}
        assert BASELINE_ARTIFACTS == 1

    # -- duel 3: all 11 domains -------------------------------------------

    @pytest.mark.parametrize("domain", list(Domain), ids=lambda d: d.value)
    def test_all_11_domains_build_artifacts(self, domain):
        assert len(list(Domain)) == 11
        bank = get_questionbank(domain)
        assert len(bank) >= 10

        iv = start_interview(f"{domain.value} outcome", domain)
        _answer_all(iv)
        assert _answered_dimensions(iv) >= {"intent", "success"}

        bp = build_blueprint(iv)
        assert bp.domain == domain
        assert bp.goal and bp.problem and bp.proposed

        commands, directives = build_edict(iv, bp)
        assert commands, f"{domain.value}: no commands derived"
        assert directives, f"{domain.value}: no directives derived"

    # -- duel 4: four interview modes -------------------------------------

    def test_all_four_interview_modes_work(self):
        assert [m.value for m in InterviewMode] == [
            "interview", "batch", "auto", "import",
        ]

        # AUTO: infer what we can, park the rest
        iv_auto = start_interview("Organize a fundraiser", Domain.BUSINESS,
                                  mode=InterviewMode.AUTO)
        auto_answer(iv_auto)
        assert len(iv_auto.answers) >= 1
        assert len(iv_auto.open_questions) >= 1
        s_auto = interview_summary(iv_auto)
        assert s_auto["answered_count"] == len(iv_auto.answers)
        assert s_auto["open_question_count"] == len(iv_auto.open_questions)

        # IMPORT: seed from an existing document, park the gaps
        iv_import = start_interview("Rewrite the handbook", Domain.WRITING,
                                    mode=InterviewMode.IMPORT)
        # a design doc that restates the discovery questions with answers
        doc = "\n".join(
            f"{q.prompt} Answer: rewrite the handbook for new hires and managers."
            for q in iv_import.questions
        )
        import_answers(iv_import, doc)
        assert len(iv_import.answers) >= 5
        # every question is answered or explicitly parked as an open item
        assert (len(iv_import.answers) + len(iv_import.open_questions)
                >= len(iv_import.questions))

        # BATCH: fill the form in one go, unmatched fields are parked
        iv_batch = start_interview("Host a workshop", Domain.EDUCATION,
                                   mode=InterviewMode.BATCH)
        ids = [q.id for q in iv_batch.questions]
        batch_answer(iv_batch, {
            ids[0]: "Teach pottery basics to absolute beginners",
            ids[1]: {"value": "my own unlisted plan", "is_custom": True,
                     "confidence": 0.8},
            "bogus_field": "x",
        })
        assert len(iv_batch.answers) == 2
        assert iv_batch.answer_map()[ids[1]].is_custom is True
        assert iv_batch.answer_map()[ids[1]].value == "my own unlisted plan"
        assert "Unmatched form field: bogus_field" in iv_batch.open_questions

        # superpowers has a single static path and no modes at all
        assert "mode" not in baseline_superpowers_brainstorm("x")

    # -- duel 5: brainstorm breadth ---------------------------------------

    def test_brainstorm_breadth_beats_2_3_approaches(self):
        topic = "reduce churn for the subscription bakery"
        s1 = brainstorm(topic, domain=Domain.BUSINESS, count=12, seed=42)

        assert len(s1.ideas) >= 12
        active = [k for k, v in s1.technique_counts.items() if v > 0]
        assert len(active) >= 5, f"only {active}"
        assert sum(s1.technique_counts.values()) == len(s1.ideas)
        assert all(i.title for i in s1.ideas)

        # deterministic with a seed
        s2 = brainstorm(topic, domain=Domain.BUSINESS, count=12, seed=42)
        assert [i.title for i in s1.ideas] == [i.title for i in s2.ideas]
        assert [i.score for i in s1.ideas] == [i.score for i in s2.ideas]

        # convergent phase picks and clusters too
        top = select_top(s1, 3)
        assert len(top.selected) == 3
        assert cluster_ideas(s1)

        base = baseline_superpowers_brainstorm(topic)
        assert len(base["approaches"]) <= BASELINE_TECHNIQUES_MAX
        assert len(active) > BASELINE_TECHNIQUES_MAX

    # -- duel 6: universal (every agent type) ------------------------------

    @pytest.mark.parametrize(
        ("domain", "title", "answers", "marker"),
        UNIVERSAL_CASES,
        ids=[c[0].value for c in UNIVERSAL_CASES],
    )
    def test_universal_no_coding_bias(self, domain, title, answers, marker):
        iv = start_interview(title, domain)
        _answer_all(iv, answers)
        bundle = render_bundle(iv, width=60)

        joined = "\n".join(art.markdown for art in bundle.values())
        hit = CODING_ONLY_RE.search(joined)
        assert hit is None, f"coding-only term {hit.group(0)!r} leaked into {domain}"

        # the domain-appropriate framing is present instead
        assert marker in joined
        for art in bundle.values():
            assert art.domain == domain.value
        assert f"**Domain:** {domain.value.capitalize()}" in bundle["blueprint"].markdown


# ---------------------------------------------------------------------------
# Overall scoreboard
# ---------------------------------------------------------------------------


class TestForgeScoreboard:
    """Aggregate: Forge wins every duel dimension against superpowers."""

    #: dimension -> (forge, superpowers)
    SCOREBOARD = {
        "artifacts_per_interview": (5, BASELINE_ARTIFACTS),
        "brainstorm_techniques": (5, BASELINE_TECHNIQUES_MAX),
        "domains": (11, BASELINE_DOMAINS),
        "interview_modes": (4, BASELINE_MODES),
        "discovery_dimensions": (12, BASELINE_DIMENSIONS),
    }

    def test_school_wins_all_dimensions(self):
        live = {
            "artifacts_per_interview": self._artifact_kinds(),
            "brainstorm_techniques": self._active_techniques(),
            "domains": len(list(Domain)),
            "interview_modes": len(list(InterviewMode)),
            "discovery_dimensions": len(DIMENSIONS),
        }
        assert set(live) == set(self.SCOREBOARD)
        for dim, count in live.items():
            expected, baseline = self.SCOREBOARD[dim]
            assert count >= expected, f"{dim} drifted: {count} < {expected}"
            assert count > baseline, f"{dim} lost the duel"

    def test_adaptive_beats_static(self):
        iv = start_interview("Cosy mystery novel", Domain.WRITING)
        q1 = next_question(iv)
        submit_answer(iv, q1.id, "a fully custom discovery answer", confidence=1.0)
        q2 = next_question(iv)
        assert q2.dimension != q1.dimension  # adaptive (forge)
        base = baseline_superpowers_brainstorm("a novel")
        assert base["questions"] == baseline_superpowers_brainstorm("x")["questions"]

    @staticmethod
    def _artifact_kinds() -> int:
        iv = start_interview("Cosy mystery novel", Domain.WRITING)
        _answer_all(iv, WRITING_ANSWERS)
        return len(render_bundle(iv, width=60))

    @staticmethod
    def _active_techniques() -> int:
        s = brainstorm("retention ideas", domain=Domain.BUSINESS, count=12, seed=42)
        return sum(1 for v in s.technique_counts.values() if v > 0)

    def test_scoreboard_summary(self):
        """Print and assert the final scoreboard."""
        lines = ["=" * 62, "FORGE vs SUPERPOWERS SCOREBOARD", "=" * 62]
        wins = 0
        for dim, (forge_n, base_n) in self.SCOREBOARD.items():
            school_wins = forge_n > base_n
            wins += int(school_wins)
            lines.append(f"{dim:<26} forge {forge_n:3d}  vs superpowers {base_n:3d}"
                         f"  -> {'WIN' if school_wins else 'LOSS'}")
        lines.append("-" * 62)
        lines.append("adaptive interview: forge yes vs superpowers static")
        lines.append(f"Forge wins: {wins}/{len(self.SCOREBOARD)} dimensions")
        lines.append("=" * 62)
        print("\n".join(lines))

        assert wins == len(self.SCOREBOARD)
