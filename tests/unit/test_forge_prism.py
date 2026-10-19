"""Unit tests for core.forge.prism — the divergent→convergent brainstorm engine.

Coverage: multi-technique generation, technique bookkeeping, determinism,
convergent scoring/selection/clustering, the summary shape, universality
across domains, the six repo-shipped Forge skills, and — first-class —
fail-open behavior under hostile input (None, ints, objects whose
``__str__``/``__bool__`` explode). OneDrive-safe: temp dirs come from
``tempfile.mkdtemp`` + ``shutil.rmtree`` (never ``tmp_path``).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from core.forge.models import BrainstormSession, Domain, Idea
from core.forge.prism import (
    TECHNIQUES,
    brainstorm,
    brainstorm_summary,
    cluster_ideas,
    score_ideas,
    select_top,
)

_SKILL_NAMES = ("forge", "triage", "chart", "gate", "relay", "scrutinize")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / "skills"
_ARTIFACT_WORDS = ("blueprint", "edict", "weave", "compass", "prism")

_SUMMARY_KEYS = {
    "id",
    "topic",
    "domain",
    "slug",
    "idea_count",
    "selected",
    "selected_count",
    "technique_counts",
    "techniques_used",
    "top_ideas",
    "cluster_sizes",
    "averages",
}


class _Evil:
    """Hostile object: every dunder a builder might touch explodes."""

    def __str__(self) -> str:
        raise RuntimeError("str")

    def __repr__(self) -> str:
        raise RuntimeError("repr")

    def __bool__(self) -> bool:
        raise RuntimeError("bool")

    def __int__(self) -> int:
        raise RuntimeError("int")

    def __float__(self) -> float:
        raise RuntimeError("float")

    def __iter__(self):
        raise RuntimeError("iter")

    def __getattr__(self, name: str):
        raise RuntimeError("getattr")


@pytest.fixture
def workdir():
    """OneDrive-safe temp dir via tempfile.mkdtemp (never tmp_path)."""
    d = tempfile.mkdtemp(prefix="forge_prism_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _manual_session(*ideas: Idea) -> BrainstormSession:
    return BrainstormSession(topic="manual", ideas=list(ideas))


def _parse_skill(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{path} must open with frontmatter"
    parts = text.split("---", 2)
    assert len(parts) == 3, f"{path} needs closing --- on its frontmatter"
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip()
    return meta, parts[2]


# --- generation -------------------------------------------------------------

def test_brainstorm_generates_at_least_count_ideas():
    s = brainstorm("Ship the beta", seed=1, count=12)
    assert isinstance(s, BrainstormSession)
    assert len(s.ideas) >= 12


def test_brainstorm_spans_multiple_techniques():
    s = brainstorm("Ship the beta", seed=1, count=12)
    used = {i.technique for i in s.ideas}
    assert len(used) >= 3
    assert sum(1 for v in s.technique_counts.values() if v > 0) >= 3


def test_brainstorm_records_technique_per_idea():
    s = brainstorm("Ship the beta", seed=1, count=12)
    for idea in s.ideas:
        assert idea.technique
        assert idea.technique in s.technique_counts


def test_brainstorm_technique_counts_populated():
    s = brainstorm("Ship the beta", seed=1, count=12)
    assert s.technique_counts
    assert sum(s.technique_counts.values()) == len(s.ideas)
    for name in s.technique_counts:
        assert name in TECHNIQUES or name == "baseline"


def test_brainstorm_titles_unique():
    s = brainstorm("Ship the beta", seed=1, count=25)
    titles = [i.title for i in s.ideas]
    assert len(titles) == len(set(titles))


def test_brainstorm_ideas_reference_the_topic():
    s = brainstorm("Ship the beta", seed=1, count=12)
    for idea in s.ideas:
        assert "ship the beta" in idea.description.lower()
        assert idea.title


def test_brainstorm_ideas_sorted_desc_after_run():
    s = brainstorm("Ship the beta", seed=1, count=12)
    scores = [i.score for i in s.ideas]
    assert scores == sorted(scores, reverse=True)
    assert all(sc > 0 for sc in scores)


def test_brainstorm_deterministic_with_same_seed():
    a = brainstorm("Ship the beta", seed=7, count=12)
    b = brainstorm("Ship the beta", seed=7, count=12)
    assert [i.to_dict() for i in a.ideas] == [i.to_dict() for i in b.ideas]
    assert a.technique_counts == b.technique_counts
    assert a.slug == b.slug


def test_brainstorm_seed_zero_is_deterministic():
    a = brainstorm("Ship the beta", seed=0, count=6)
    b = brainstorm("Ship the beta", seed=0, count=6)
    assert [i.title for i in a.ideas] == [i.title for i in b.ideas]


def test_brainstorm_different_seeds_differ():
    a = brainstorm("Ship the beta", seed=1, count=12)
    b = brainstorm("Ship the beta", seed=2, count=12)
    assert [i.title for i in a.ideas] != [i.title for i in b.ideas]


def test_brainstorm_respects_requested_count():
    assert len(brainstorm("Small", seed=3, count=3).ideas) >= 3
    assert len(brainstorm("Big", seed=3, count=25).ideas) >= 25


def test_brainstorm_count_zero_yields_no_ideas():
    s = brainstorm("Ship the beta", seed=3, count=0)
    assert s.ideas == []
    assert brainstorm_summary(s)["idea_count"] == 0


def test_brainstorm_custom_techniques_respected():
    s = brainstorm("Ship the beta", seed=4, count=6, techniques=["worst_idea", "analogy"])
    used = {i.technique for i in s.ideas}
    assert used and used <= {"worst_idea", "analogy"}


def test_brainstorm_technique_aliases_normalized():
    s = brainstorm(
        "Ship the beta", seed=5, count=6, techniques=["role-storming", "worst", "brain_writing"]
    )
    used = {i.technique for i in s.ideas}
    assert used and used <= {"role_storm", "worst_idea", "brainwriting"}


def test_brainstorm_single_string_technique():
    s = brainstorm("Ship the beta", seed=6, count=5, techniques="scamper")
    assert {i.technique for i in s.ideas} == {"scamper"}
    assert s.technique_counts == {"scamper": len(s.ideas)}


def test_brainstorm_unknown_techniques_fall_back_to_default():
    s = brainstorm("Ship the beta", seed=7, count=12, techniques=["nonsense", 42, _Evil()])
    assert len(s.ideas) >= 12
    assert len({i.technique for i in s.ideas}) >= 3


def test_brainstorm_default_techniques_match_registry():
    s = brainstorm("Ship the beta", seed=8, count=18)
    assert set(s.technique_counts) == set(TECHNIQUES)


# --- convergent scoring -----------------------------------------------------

def test_score_ideas_default_formula():
    sess = _manual_session(
        Idea(title="a", impact=8.0, feasibility=2.0),
        Idea(title="b", impact=5.0, feasibility=5.0),
        Idea(title="c", impact=3.0, feasibility=9.0),
    )
    out = score_ideas(sess)
    by = {i.title: i for i in out.ideas}
    assert by["a"].score == pytest.approx(8 * 0.6 + 2 * 0.4)
    assert by["b"].score == pytest.approx(5 * 0.6 + 5 * 0.4)
    assert by["c"].score == pytest.approx(3 * 0.6 + 9 * 0.4)


def test_score_ideas_sorts_desc():
    sess = _manual_session(
        Idea(title="a", impact=8.0, feasibility=2.0),
        Idea(title="b", impact=5.0, feasibility=5.0),
        Idea(title="c", impact=3.0, feasibility=9.0),
    )
    out = score_ideas(sess)
    assert [i.title for i in out.ideas] == ["a", "c", "b"]
    scores = [i.score for i in out.ideas]
    assert scores == sorted(scores, reverse=True)


def test_score_ideas_custom_weights():
    sess = _manual_session(
        Idea(title="hi-impact", impact=9.0, feasibility=1.0),
        Idea(title="hi-feas", impact=1.0, feasibility=9.0),
    )
    out = score_ideas(sess, weights={"impact": 0.0, "feasibility": 1.0})
    assert out.ideas[0].title == "hi-feas"
    assert out.ideas[0].score == pytest.approx(9.0)
    out = score_ideas(sess, weights={"impact": 1.0, "feasibility": 0.0})
    assert out.ideas[0].title == "hi-impact"


def test_score_ideas_returns_same_session_object():
    sess = _manual_session(Idea(title="a", impact=2.0, feasibility=2.0))
    assert score_ideas(sess) is sess


def test_score_ideas_estimates_when_axes_unset():
    sess = _manual_session(
        Idea(title="unscored one"),
        Idea(title="unscored two", description="longer description here"),
    )
    out = score_ideas(sess)
    for idea in out.ideas:
        assert idea.score > 0
        assert 0 < idea.impact <= 10
        assert 0 < idea.feasibility <= 10


@pytest.mark.parametrize(
    "weights",
    [_Evil(), "garbage", {"impact": "x"}, {"impact": _Evil()}, [1, 2], 3.0],
    ids=["evil", "str", "bad-value", "evil-value", "list", "float"],
)
def test_score_ideas_hostile_weights_never_raise(weights):
    s = brainstorm("Ship the beta", seed=9, count=6)
    out = score_ideas(s, weights=weights)
    assert isinstance(out, BrainstormSession)
    assert len(out.ideas) == 6


def test_score_ideas_garbage_weight_falls_back_to_default():
    sess = _manual_session(Idea(title="a", impact=8.0, feasibility=2.0))
    out = score_ideas(sess, weights={"impact": "x", "feasibility": "y"})
    assert out.ideas[0].score == pytest.approx(8 * 0.6 + 2 * 0.4)


# --- selection --------------------------------------------------------------

def test_select_top_fills_selected():
    s = brainstorm("Ship the beta", seed=10, count=12)
    out = select_top(s, 3)
    assert out.selected == [i.title for i in out.ideas[:3]]
    assert len(out.selected) == 3


def test_select_top_respects_scores_not_order():
    sess = _manual_session(
        Idea(title="low", impact=1.0, feasibility=1.0),
        Idea(title="high", impact=10.0, feasibility=10.0),
        Idea(title="mid", impact=5.0, feasibility=5.0),
    )
    score_ideas(sess)
    out = select_top(sess, 2)
    assert out.selected == ["high", "mid"]


def test_select_top_caps_at_available():
    sess = _manual_session(Idea(title="only one", impact=4.0, feasibility=4.0))
    out = select_top(sess, 10)
    assert out.selected == ["only one"]


def test_select_top_empty_session_selects_nothing():
    out = select_top(BrainstormSession(), 3)
    assert out.selected == []


@pytest.mark.parametrize(
    "n", [_Evil(), -5, "abc", None, 2.9], ids=["evil", "negative", "str", "none", "float"]
)
def test_select_top_hostile_n_never_raises(n):
    s = brainstorm("Ship the beta", seed=11, count=6)
    out = select_top(s, n)
    assert isinstance(out.selected, list)
    assert len(out.selected) <= 6


# --- clustering -------------------------------------------------------------

def test_cluster_ideas_groups_by_tag():
    s = brainstorm("Ship the beta", seed=12, count=12)
    clusters = cluster_ideas(s)
    assert clusters
    # every idea lands in at least one cluster
    covered = {t for titles in clusters.values() for t in titles}
    assert covered == {i.title for i in s.ideas}
    # technique buckets agree with the bookkeeping
    for name, n in s.technique_counts.items():
        if n:
            assert len(clusters[name]) == n
    assert len(clusters) >= 5


def test_cluster_ideas_untagged_bucket():
    sess = _manual_session(Idea(title="solo"), Idea(title="tagged", tags=["alpha"]))
    clusters = cluster_ideas(sess)
    assert clusters["untagged"] == ["solo"]
    assert clusters["alpha"] == ["tagged"]


def test_cluster_ideas_empty_session():
    assert cluster_ideas(BrainstormSession()) == {}


def test_cluster_ideas_multi_tag_idea_appears_in_each():
    sess = _manual_session(Idea(title="x", tags=["one", "two"]))
    clusters = cluster_ideas(sess)
    assert clusters["one"] == ["x"]
    assert clusters["two"] == ["x"]


# --- summary ----------------------------------------------------------------

def test_brainstorm_summary_shape():
    s = brainstorm("Ship the beta", seed=13, count=12)
    select_top(s, 3)
    summary = brainstorm_summary(s)
    assert set(summary) >= _SUMMARY_KEYS
    assert summary["topic"] == "Ship the beta"
    assert summary["domain"] == Domain.GENERAL.value
    assert summary["idea_count"] == len(s.ideas) == 12
    assert summary["selected_count"] == 3
    assert summary["selected"] == s.selected
    assert sum(summary["technique_counts"].values()) == 12
    assert summary["techniques_used"] == sorted(
        k for k, v in summary["technique_counts"].items() if v > 0
    )
    assert 1 <= len(summary["top_ideas"]) <= 5
    top_scores = [t["score"] for t in summary["top_ideas"]]
    assert top_scores == sorted(top_scores, reverse=True)
    assert set(summary["averages"]) == {"impact", "feasibility", "score"}


def test_brainstorm_summary_of_empty_session():
    summary = brainstorm_summary(BrainstormSession())
    assert summary["idea_count"] == 0
    assert summary["top_ideas"] == []
    assert summary["technique_counts"] == {}
    assert summary["techniques_used"] == []


def test_brainstorm_summary_views_are_json_safe():
    s = brainstorm("Ship the beta", seed=14, count=6)
    assert json.dumps(brainstorm_summary(s))


# --- universality across domains -------------------------------------------

@pytest.mark.parametrize(
    "domain", [Domain.CREATIVE, Domain.BUSINESS, Domain.LIFE], ids=["creative", "business", "life"]
)
def test_brainstorm_universal_domains(domain):
    s = brainstorm("Launch the workshop", domain=domain, seed=15, count=9)
    assert s.domain == domain
    assert len(s.ideas) >= 9
    assert len({i.technique for i in s.ideas}) >= 3
    assert brainstorm_summary(s)["domain"] == domain.value


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("business", Domain.BUSINESS),
        ("WRITING", Domain.WRITING),
        (999, Domain.GENERAL),
        (_Evil(), Domain.GENERAL),
        (None, Domain.GENERAL),
    ],
    ids=["str", "upper", "int", "evil", "none"],
)
def test_brainstorm_domain_coercion(raw, expected):
    s = brainstorm("Launch the workshop", domain=raw, seed=16, count=3)
    assert s.domain == expected


# --- fail-open under hostile input -----------------------------------------

@pytest.mark.parametrize(
    "topic",
    [None, 123, 3.14, b"bytes", "", _Evil(), object(), "x" * 5000],
    ids=["none", "int", "float", "bytes", "empty", "evil", "object", "huge"],
)
def test_brainstorm_hostile_topic_never_raises(topic):
    s = brainstorm(topic, seed=17, count=6)
    assert isinstance(s, BrainstormSession)
    assert len(s.ideas) >= 6


@pytest.mark.parametrize(
    "domain", [_Evil(), None, 999, {"a": 1}], ids=["evil", "none", "int", "dict"]
)
def test_brainstorm_hostile_domain_never_raises(domain):
    s = brainstorm("Ship the beta", domain=domain, seed=18, count=4)
    assert isinstance(s.domain, Domain)
    assert len(s.ideas) >= 4


@pytest.mark.parametrize(
    "count", [_Evil(), -5, "abc", None, 2.9], ids=["evil", "negative", "str", "none", "float"]
)
def test_brainstorm_hostile_count_never_raises(count):
    s = brainstorm("Ship the beta", count=count, seed=19)
    assert isinstance(s, BrainstormSession)
    assert len(s.ideas) <= 500


@pytest.mark.parametrize(
    "seed", [_Evil(), object(), [1, 2], 3.14], ids=["evil", "object", "list", "float"]
)
def test_brainstorm_hostile_seed_never_raises(seed):
    s = brainstorm("Ship the beta", seed=seed, count=4)
    assert len(s.ideas) >= 4


@pytest.mark.parametrize(
    "techniques",
    [_Evil(), ["nonsense"], 42, {"a": 1}, [None, _Evil()]],
    ids=["evil", "unknown", "int", "dict", "mixed"],
)
def test_brainstorm_hostile_techniques_never_raises(techniques):
    s = brainstorm("Ship the beta", techniques=techniques, seed=20, count=6)
    assert len(s.ideas) >= 6
    assert s.technique_counts


@pytest.mark.parametrize(
    "arg",
    [None, "str", {}, 42, [1, 2], _Evil()],
    ids=["none", "str", "dict", "int", "list", "evil"],
)
def test_hostile_session_inputs_never_raise(arg):
    assert isinstance(score_ideas(arg), BrainstormSession)
    assert isinstance(select_top(arg, 3).selected, list)
    assert isinstance(cluster_ideas(arg), dict)
    assert isinstance(brainstorm_summary(arg), dict)


def test_session_with_evil_ideas_never_raises():
    s = brainstorm("Ship the beta", seed=21, count=3)
    s.ideas.append(_Evil())
    assert isinstance(score_ideas(s), BrainstormSession)
    assert isinstance(select_top(s, 5).selected, list)
    assert isinstance(cluster_ideas(s), dict)
    assert isinstance(brainstorm_summary(s), dict)


def test_hostile_weights_with_evil_session_never_raises():
    assert isinstance(score_ideas(_Evil(), weights=_Evil()), BrainstormSession)
    assert isinstance(select_top(_Evil(), _Evil()).selected, list)


# --- persistence round-trip (uses the mkdtemp workdir) ----------------------

def test_session_roundtrip_through_json_file(workdir):
    s = brainstorm("Persist me", seed=22, count=9)
    path = Path(workdir) / "session.json"
    path.write_text(json.dumps(s.to_dict()), encoding="utf-8")
    back = BrainstormSession.from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert back.topic == s.topic
    assert len(back.ideas) == len(s.ideas)
    assert back.technique_counts == s.technique_counts
    assert [i.title for i in back.ideas] == [i.title for i in s.ideas]
    assert brainstorm_summary(back)["idea_count"] == 9


# --- the repo-shipped Forge skill pack --------------------------------------

def test_skill_files_exist():
    for name in _SKILL_NAMES:
        path = _SKILLS_DIR / name / "SKILL.md"
        assert path.is_file(), f"missing skill file: {path}"


@pytest.mark.parametrize("name", _SKILL_NAMES, ids=list(_SKILL_NAMES))
def test_skill_frontmatter_name_description(name):
    meta, _body = _parse_skill(_SKILLS_DIR / name / "SKILL.md")
    assert meta.get("name") == name
    description = meta.get("description", "")
    assert len(description) >= 60, "description must say when to use the skill"
    assert "not only coding" in description


@pytest.mark.parametrize("name", _SKILL_NAMES, ids=list(_SKILL_NAMES))
def test_skill_bodies_nontrivial(name):
    _meta, body = _parse_skill(_SKILLS_DIR / name / "SKILL.md")
    assert len(body) >= 2000, "body must be thorough, not a stub"
    assert body.count("\n## ") >= 3, "body needs real sections"
    assert body.count("\n### ") >= 1 or body.count("\n## ") >= 5


@pytest.mark.parametrize("name", _SKILL_NAMES, ids=list(_SKILL_NAMES))
def test_skill_bodies_universal_and_reference_artifacts(name):
    _meta, body = _parse_skill(_SKILLS_DIR / name / "SKILL.md")
    low = body.lower()
    assert "universal" in low, "skills must state universality explicitly"
    hits = sum(1 for word in _ARTIFACT_WORDS if word in low)
    assert hits >= 2, "skills must reference the Forge artifacts where relevant"


def test_skill_files_parse_from_temp_copy(workdir):
    target = Path(workdir) / "skills"
    shutil.copytree(_SKILLS_DIR, target)
    for name in _SKILL_NAMES:
        meta, body = _parse_skill(target / name / "SKILL.md")
        assert meta["name"] == name
        assert meta["description"]
        assert len(body) >= 2000
