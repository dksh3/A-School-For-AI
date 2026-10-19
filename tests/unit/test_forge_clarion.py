"""Unit tests for the Forge discovery-interview engine (core.forge.clarion)
and the 11-domain question banks (core.forge.domains).

OneDrive-safe: temporary directories come from ``tempfile.mkdtemp`` +
``shutil.rmtree`` — never ``tmp_path``. Every public function is verified to
be fail-open under hostile input (objects whose ``__str__``/``__bool__``/
``__hash__`` raise, unhashables, wrong types, None).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

import pytest

from core.forge import clarion
from core.forge.clarion import (
    DEFAULT_DIMENSION_SCORE,
    DONE_COVERAGE,
    auto_answer,
    batch_answer,
    import_answers,
    interview_summary,
    next_question,
    start_interview,
    submit_answer,
)
from core.forge.domains import ALL_DOMAINS, DOMAIN_QUESTIONBANKS, get_questionbank
from core.forge.models import (
    _DIMENSIONS,
    Domain,
    Interview,
    InterviewMode,
    Question,
    QuestionType,
)

# --- hostile objects --------------------------------------------------------

class _Evil:
    """Everything about this object blows up."""

    def __str__(self):
        raise RuntimeError("evil __str__")

    def __repr__(self):
        raise RuntimeError("evil __repr__")

    def __bool__(self):
        raise RuntimeError("evil __bool__")

    def __hash__(self):
        raise RuntimeError("evil __hash__")

    def __eq__(self, other):
        raise RuntimeError("evil __eq__")


class _EvilDict(dict):
    def items(self):
        raise RuntimeError("evil items")

    def get(self, *args, **kwargs):
        raise RuntimeError("evil get")


class _EvilList(list):
    def __iter__(self):
        raise RuntimeError("evil iter")


# --- fixtures ---------------------------------------------------------------

@pytest.fixture
def workdir():
    """OneDrive-safe temp directory (never pytest's tmp_path)."""
    path = tempfile.mkdtemp(prefix="forge_clarion_")
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _prompts(bank):
    return [q.prompt for q in bank]


# --- question-bank registry -------------------------------------------------

def test_registry_shape():
    assert isinstance(DOMAIN_QUESTIONBANKS, dict)
    assert len(DOMAIN_QUESTIONBANKS) == 11
    assert all(callable(fn) for fn in DOMAIN_QUESTIONBANKS.values())
    assert set(ALL_DOMAINS) == {d.value for d in Domain}
    assert list(ALL_DOMAINS) == [d.value for d in Domain]


@pytest.mark.parametrize("domain", ALL_DOMAINS)
def test_bank_builds_for_every_domain(domain):
    bank = get_questionbank(domain)
    assert isinstance(bank, list)
    assert 10 <= len(bank) <= 14
    assert all(isinstance(q, Question) for q in bank)


def test_get_questionbank_returns_independent_copies():
    first = get_questionbank("coding")
    original = first[0].prompt
    first[0].prompt = "MUTATED"
    first.pop()
    second = get_questionbank("coding")
    assert second[0].prompt == original
    assert second[0].prompt != "MUTATED"
    assert len(second) == 14


def test_get_questionbank_unknown_domain_falls_back_to_general():
    general = get_questionbank("general")
    fallback = get_questionbank("underwater basket weaving")
    assert _prompts(fallback) == _prompts(general)
    assert _prompts(get_questionbank(None)) == _prompts(general)
    assert _prompts(get_questionbank(42)) == _prompts(general)


def test_get_questionbank_alias_maps_to_domain():
    assert _prompts(get_questionbank("dev")) == _prompts(get_questionbank("coding"))
    assert _prompts(get_questionbank("teach")) == _prompts(get_questionbank("education"))
    assert _prompts(get_questionbank(Domain.LIFE)) == _prompts(get_questionbank("life"))


def test_get_questionbank_hostile_never_raises():
    hostile = [None, 0, 1.5, "nonsense", [], {}, [1, 2], b"raw", _Evil(), _EvilList()]
    for h in hostile:
        bank = get_questionbank(h)
        assert isinstance(bank, list)
        assert all(isinstance(q, Question) for q in bank)
    bad_loader = DOMAIN_QUESTIONBANKS["coding"]
    DOMAIN_QUESTIONBANKS["coding"] = lambda *_a, **_k: 1 / 0
    try:
        assert len(get_questionbank("coding")) == 14  # falls back to general
    finally:
        DOMAIN_QUESTIONBANKS["coding"] = bad_loader


# --- bank quality -----------------------------------------------------------

@pytest.mark.parametrize("domain", ALL_DOMAINS)
def test_bank_covers_all_twelve_dimensions(domain):
    dims = {q.dimension for q in get_questionbank(domain)}
    assert set(_DIMENSIONS) <= dims


@pytest.mark.parametrize("domain", ALL_DOMAINS)
def test_bank_varies_question_types(domain):
    types = {q.type for q in get_questionbank(domain)}
    assert types == {
        QuestionType.CHOICE, QuestionType.MULTI, QuestionType.SCALE,
        QuestionType.TEXT, QuestionType.CONFIRM,
    }


@pytest.mark.parametrize("domain", ALL_DOMAINS)
def test_bank_choice_multi_allow_custom(domain):
    for q in get_questionbank(domain):
        if q.type in (QuestionType.CHOICE, QuestionType.MULTI):
            assert q.allow_custom is True
            assert len(q.options) >= 2


@pytest.mark.parametrize("domain", ALL_DOMAINS)
def test_bank_required_and_ids(domain):
    bank = get_questionbank(domain)
    assert sum(1 for q in bank if q.required) >= 2
    ids = [q.id for q in bank]
    assert len(ids) == len(set(ids))
    assert all(q.prompt.strip() for q in bank)


@pytest.mark.parametrize("domain", ALL_DOMAINS)
def test_bank_followups_carry_triggers(domain):
    seen_followups = 0
    for q in get_questionbank(domain):
        for fu in q.followups:
            seen_followups += 1
            assert fu.domain_hint.startswith(clarion.WHEN_PREFIX)
            assert fu.prompt.strip()
    assert seen_followups >= 3


# --- start_interview --------------------------------------------------------

@pytest.mark.parametrize("domain", ALL_DOMAINS)
def test_start_interview_builds_bank_every_domain(domain):
    itv = start_interview(f"Work item for {domain}", domain)
    assert isinstance(itv, Interview)
    assert 10 <= len(itv.questions) <= 14
    assert itv.domain.value == domain or domain == "general"


def test_start_interview_ids_slug_and_scores():
    itv = start_interview("My Great Thing", "coding")
    assert itv.slug == "my-great-thing"
    assert [q.id for q in itv.questions] == [f"q{i}" for i in range(1, 15)]
    assert set(itv.dimension_scores) == set(_DIMENSIONS)
    assert all(abs(v - DEFAULT_DIMENSION_SCORE) < 1e-9
               for v in itv.dimension_scores.values())
    assert itv.domain == Domain.CODING
    assert itv.mode == InterviewMode.INTERVIEW
    assert itv.coverage() == 0.0


def test_start_interview_appends_seed_questions():
    seed = Question(id="seed1", dimension="intent", prompt="What is the secret goal?")
    itv = start_interview("Seeded", "general", seed_questions=[seed])
    assert len(itv.questions) == 15
    assert itv.questions[-1].prompt == "What is the secret goal?"
    assert itv.questions[-1].id == "q15"


def test_start_interview_accepts_dict_seeds_and_drops_junk():
    seeds = [
        {"id": "d1", "dimension": "scope", "prompt": "Dict seed prompt"},
        _Evil(),
        "junk",
        42,
    ]
    itv = start_interview("Seeded", "general", seed_questions=seeds)
    assert any(q.prompt == "Dict seed prompt" for q in itv.questions)


def test_start_interview_existing_doc_seeds_answers():
    seeds = [
        Question(id="s1", dimension="intent", prompt="What is the zizzerzazz goal?",
                 type=QuestionType.TEXT),
        Question(id="s2", dimension="constraints", prompt="Which zizzerzazz deadline?",
                 type=QuestionType.CHOICE, options=["March launch", "June launch"]),
    ]
    doc = (
        "zizzerzazz goal: launch wibblewobble by spring.\n"
        "zizzerzazz deadline: March launch is the plan.\n"
    )
    itv = start_interview("From a doc", "general", mode=InterviewMode.IMPORT,
                          seed_questions=seeds, existing_doc=doc)
    values = [a.value for a in itv.answers]
    assert "March launch" in values
    assert any("zizzerzazz goal" in str(v) for v in values)
    assert itv.coverage() > 0.0


def test_start_interview_mode_coercion():
    assert start_interview("t", "coding", mode="batch").mode == InterviewMode.BATCH
    assert start_interview("t", "coding", mode=InterviewMode.IMPORT).mode \
        == InterviewMode.IMPORT
    assert start_interview("t", "coding", mode=99).mode == InterviewMode.INTERVIEW
    assert start_interview("t", "coding", mode=None).mode == InterviewMode.INTERVIEW
    assert start_interview("t", "coding", mode=_Evil()).mode == InterviewMode.INTERVIEW


def test_start_interview_hostile_never_raises():
    itv = start_interview(_Evil(), _Evil(), _Evil(), _EvilList(), _Evil())
    assert isinstance(itv, Interview)
    assert len(itv.questions) >= 10  # general fallback bank
    itv2 = start_interview(["weird"], {"a": 1}, b"mode", [[_Evil()]], [1, 2])
    assert isinstance(itv2, Interview)


# --- next_question ----------------------------------------------------------

def test_next_question_starts_at_first_question():
    itv = start_interview("t", "general")
    nxt = next_question(itv)
    assert nxt is not None
    assert nxt.id == "q1"
    assert nxt.dimension == "intent"


def test_next_question_is_adaptive():
    itv = start_interview("t", "general")
    submit_answer(itv, "q1", "alpha")
    nxt = next_question(itv)
    assert nxt is not None
    assert nxt.id != "q1"
    assert nxt.dimension != "intent"  # intent is now the strongest dimension


def test_next_question_targets_weakest_dimension():
    itv = start_interview("t", "general")
    submit_answer(itv, "q1", "alpha")
    itv.dimension_scores["audience"] = 0.9
    nxt = next_question(itv)
    assert nxt is not None
    assert nxt.dimension == "scope"
    assert nxt.id == "q4"


def test_next_question_returns_none_when_all_answered():
    itv = start_interview("t", "general")
    for i, q in enumerate(itv.questions):
        submit_answer(itv, q.id, f"answer-{i}")
    assert next_question(itv) is None


def test_next_question_returns_none_at_high_coverage():
    itv = start_interview("t", "general")
    for qid in ("q1", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10", "q11",
                "q12", "q13"):
        submit_answer(itv, qid, "alpha")
    assert itv.coverage() >= DONE_COVERAGE
    assert next_question(itv) is None


def test_high_coverage_still_asks_required_questions():
    itv = start_interview("t", "general")
    for qid in ("q2", "q3", "q4", "q5", "q7", "q8", "q9", "q10", "q11", "q12", "q13"):
        submit_answer(itv, qid, "alpha")
    assert itv.coverage() >= DONE_COVERAGE
    assert interview_summary(itv)["required_outstanding"] == 2
    assert next_question(itv) is not None  # q1/q6 still required
    submit_answer(itv, "q14", "alpha")
    assert next_question(itv).id == "q1"
    submit_answer(itv, "q1", "alpha")
    assert next_question(itv).id == "q6"
    submit_answer(itv, "q6", "alpha")
    assert next_question(itv) is None


def test_next_question_surfaces_followups_first():
    itv = start_interview("t", "general")
    submit_answer(itv, "q2", "Fix a problem")
    nxt = next_question(itv)
    assert nxt is not None
    assert nxt.id == "q2.f0"
    assert nxt.dimension == "intent"


def test_next_question_hostile_never_raises():
    assert next_question(None) is None
    assert next_question(42) is None
    assert next_question("interview") is None
    assert next_question(_Evil()) is None
    assert next_question(_EvilDict()) is None
    itv = start_interview("t", "general")
    itv.questions = _EvilList()
    assert next_question(itv) is None


# --- submit_answer ----------------------------------------------------------

def test_submit_answer_updates_dimension_scores():
    itv = start_interview("t", "general")
    submit_answer(itv, "q1", "alpha")
    assert itv.dimension_scores["intent"] == pytest.approx(0.75)
    submit_answer(itv, "q2", "Build something new")
    assert 0.75 < itv.dimension_scores["intent"] <= 1.0
    assert itv.overall_confidence() == pytest.approx(1.0)


def test_submit_answer_clamps_confidence():
    itv = start_interview("t", "general")
    submit_answer(itv, "q1", "alpha", confidence=7.5)
    assert itv.answer_map()["q1"].confidence == 1.0
    submit_answer(itv, "q3", "bravo", confidence=-4)
    assert itv.answer_map()["q3"].confidence == 0.0
    assert itv.dimension_scores["audience"] > DEFAULT_DIMENSION_SCORE
    submit_answer(itv, "q4", "charlie", confidence=float("nan"))
    assert itv.answer_map()["q4"].confidence == 1.0


def test_submit_answer_replaces_existing_answer():
    itv = start_interview("t", "general")
    submit_answer(itv, "q1", "first")
    submit_answer(itv, "q1", "second")
    assert len(itv.answers) == 1
    assert itv.answer_map()["q1"].value == "second"


def test_submit_answer_triggers_followups():
    itv = start_interview("t", "general")
    submit_answer(itv, "q2", "Fix a problem")
    ids = [q.id for q in itv.questions]
    assert "q2.f0" in ids
    followup = next(q for q in itv.questions if q.id == "q2.f0")
    assert followup.dimension == "intent"
    assert "broken" in followup.prompt


def test_submit_answer_no_followup_when_trigger_unmatched():
    itv = start_interview("t", "general")
    submit_answer(itv, "q2", "Build something new")
    assert not any(q.id.startswith("q2.") for q in itv.questions)


def test_submit_answer_dedupes_followups():
    itv = start_interview("t", "general")
    submit_answer(itv, "q2", "Fix a problem")
    submit_answer(itv, "q2", "Fix a problem")
    assert sum(1 for q in itv.questions if q.id == "q2.f0") == 1


def test_submit_answer_records_unknown_ids_safely():
    itv = start_interview("t", "general")
    submit_answer(itv, "does-not-exist", "some value")
    assert "does-not-exist" in itv.answer_map()
    assert interview_summary(itv)["answered_count"] == 1


def test_submit_answer_hostile_never_raises():
    itv = start_interview("t", "general")
    out = submit_answer(itv, _Evil(), _EvilList(), _Evil(), _Evil())
    assert isinstance(out, Interview)
    out = submit_answer(itv, [["nested"]], {"a": [1, 2]}, is_custom=[1], confidence="nan")
    assert isinstance(out, Interview)
    assert len(out.answers) >= 1
    out = submit_answer(None, "q1", "x")
    assert isinstance(out, Interview)
    out = submit_answer(_Evil(), "q1", "x")
    assert isinstance(out, Interview)


# --- auto_answer ------------------------------------------------------------

def test_auto_answer_fills_gaps_and_marks_open_questions():
    itv = start_interview("Plan a mystery novel for young readers", "writing",
                          mode=InterviewMode.AUTO)
    auto_answer(itv)
    assert len(itv.answers) >= 3
    assert len(itv.open_questions) >= 3
    assert itv.coverage() > 0.0


def test_auto_answer_marks_answers_low_confidence():
    itv = start_interview("Build a homework tracker web app", "coding",
                          mode=InterviewMode.AUTO)
    auto_answer(itv)
    assert itv.answers
    assert all(a.confidence <= 0.5 for a in itv.answers)
    assert all(a.confidence > 0.0 for a in itv.answers)


def test_auto_answer_is_idempotent():
    itv = start_interview("Organize a community clean-up day", "planning",
                          mode=InterviewMode.AUTO)
    auto_answer(itv)
    answers_after_first = len(itv.answers)
    open_after_first = len(itv.open_questions)
    auto_answer(itv)
    assert len(itv.answers) == answers_after_first
    assert len(itv.open_questions) == open_after_first


def test_auto_answer_hostile_never_raises():
    assert isinstance(auto_answer(None), Interview)
    assert isinstance(auto_answer(_Evil()), Interview)
    itv = start_interview(_Evil(), "general", mode=InterviewMode.AUTO)
    itv.questions = _EvilList()
    assert isinstance(auto_answer(itv), Interview)


# --- import_answers ---------------------------------------------------------

def _seed_questions():
    return [
        Question(id="s1", dimension="intent", prompt="What is the zizzerzazz goal?",
                 type=QuestionType.TEXT),
        Question(id="s2", dimension="constraints", prompt="Which zizzerzazz deadline?",
                 type=QuestionType.CHOICE, options=["March launch", "June launch"]),
        Question(id="s3", dimension="risks", prompt="What flibbertigibbet risk is worst?",
                 type=QuestionType.TEXT),
    ]


DOC_TEXT = (
    "zizzerzazz goal: launch wibblewobble by spring.\n"
    "zizzerzazz deadline: March launch is the plan.\n"
)


def test_import_answers_extracts_from_doc():
    itv = start_interview("Import me", "general", mode=InterviewMode.IMPORT,
                          seed_questions=_seed_questions())
    import_answers(itv, DOC_TEXT)
    values = [str(a.value) for a in itv.answers]
    assert any("zizzerzazz goal" in v for v in values)
    assert "March launch" in values
    assert itv.coverage() > 0.0


def test_import_answers_prefers_option_text_for_choice():
    itv = start_interview("Import me", "general", mode=InterviewMode.IMPORT,
                          seed_questions=_seed_questions())
    import_answers(itv, DOC_TEXT)
    choice = [a for a in itv.answers if a.value == "March launch"]
    assert len(choice) == 1
    assert choice[0].is_custom is False
    assert choice[0].confidence == pytest.approx(0.6)


def test_import_answers_gaps_become_open_questions():
    itv = start_interview("Import me", "general", mode=InterviewMode.IMPORT,
                          seed_questions=_seed_questions())
    import_answers(itv, DOC_TEXT)
    assert "What flibbertigibbet risk is worst?" in itv.open_questions
    assert "In a sentence or two, what outcome should this produce?" in itv.open_questions


def test_import_answers_idempotent_and_hostile():
    itv = start_interview("Import me", "general", seed_questions=_seed_questions())
    import_answers(itv, DOC_TEXT)
    count = len(itv.answers)
    import_answers(itv, DOC_TEXT)
    assert len(itv.answers) == count  # already-answered questions are skipped
    assert isinstance(import_answers(itv, _Evil()), Interview)
    assert isinstance(import_answers(itv, _EvilList()), Interview)
    assert isinstance(import_answers(None, DOC_TEXT), Interview)
    assert isinstance(import_answers(_Evil(), DOC_TEXT), Interview)
    assert isinstance(import_answers(itv, ""), Interview)


# --- batch_answer -----------------------------------------------------------

def test_batch_answer_applies_whole_form():
    itv = start_interview("Batch form", "general")
    batch_answer(itv, {"q1": "Ship the widget", "q6": "Done means shipped",
                       "q4": "core only"})
    amap = itv.answer_map()
    assert amap["q1"].value == "Ship the widget"
    assert amap["q6"].value == "Done means shipped"
    assert amap["q4"].value == "core only"
    assert interview_summary(itv)["answered_count"] == 3
    assert itv.dimension_scores["intent"] > DEFAULT_DIMENSION_SCORE


def test_batch_answer_accepts_dict_values():
    itv = start_interview("Batch form", "general")
    batch_answer(itv, {"q7": {"value": "4", "confidence": 0.2, "is_custom": True}})
    ans = itv.answer_map()["q7"]
    assert ans.value == "4"
    assert ans.confidence == pytest.approx(0.2)
    assert ans.is_custom is True


def test_batch_answer_unknown_fields_become_open_questions():
    itv = start_interview("Batch form", "general")
    batch_answer(itv, {"nope": "x", "q1": "y"})
    assert any("Unmatched form field: nope" in o for o in itv.open_questions)
    assert "q1" in itv.answer_map()


def test_batch_answer_hostile_never_raises():
    itv = start_interview("t", "general")
    assert isinstance(batch_answer(itv, _Evil()), Interview)
    assert isinstance(batch_answer(itv, _EvilDict()), Interview)
    assert isinstance(batch_answer(itv, 42), Interview)
    assert isinstance(batch_answer(itv, ["q1", "x"]), Interview)
    assert isinstance(batch_answer(None, {"q1": "x"}), Interview)
    batch_answer(itv, {"q1": _Evil(), "q3": {"value": _Evil()}, "q4": [_Evil()]})
    assert isinstance(interview_summary(itv), dict)


# --- interview_summary ------------------------------------------------------

def test_interview_summary_shape():
    itv = start_interview("Summary shape", "business")
    summary = interview_summary(itv)
    expected_keys = {
        "title", "slug", "domain", "mode", "question_count", "answered_count",
        "coverage", "overall_confidence", "dimension_scores",
        "open_question_count", "open_questions", "required_outstanding",
    }
    assert expected_keys <= set(summary)
    assert isinstance(summary["dimension_scores"], dict)
    assert set(summary["dimension_scores"]) == set(_DIMENSIONS)
    assert isinstance(summary["coverage"], float)
    assert isinstance(summary["overall_confidence"], float)
    assert isinstance(summary["open_question_count"], int)


def test_interview_summary_counts():
    itv = start_interview("Summary counts", "general")
    submit_answer(itv, "q1", "alpha")
    submit_answer(itv, "q3", "bravo")
    itv.open_questions.append("wibble?")
    summary = interview_summary(itv)
    assert summary["title"] == "Summary counts"
    assert summary["question_count"] == len(itv.questions)
    assert summary["answered_count"] == 2
    assert 0.0 < summary["coverage"] <= 1.0
    assert summary["open_question_count"] == 1
    assert summary["dimension_scores"]["intent"] > DEFAULT_DIMENSION_SCORE
    assert summary["overall_confidence"] == pytest.approx(1.0)


def test_interview_summary_hostile_never_raises():
    zeroed = interview_summary(_Evil())
    assert isinstance(zeroed, dict)
    assert zeroed["coverage"] == 0.0
    assert zeroed["open_question_count"] == 0
    itv = start_interview("t", "general")
    itv.answers = [_Evil()]
    itv.dimension_scores = _EvilDict()
    itv.open_questions = _EvilList()
    summary = interview_summary(itv)
    assert isinstance(summary, dict)
    assert isinstance(summary["overall_confidence"], float)


# --- fail-open matrix -------------------------------------------------------

def test_fail_open_every_function_on_hostile_arguments():
    evil = _Evil()
    itv = start_interview("t", "general")
    hostile = [None, 0, 42, 3.14, "text", b"bytes", [], {}, [evil], {"k": evil},
               evil, _EvilDict(), _EvilList(), object()]
    for h in hostile:
        assert isinstance(start_interview(h, h, h, h, h), Interview)
        nxt = next_question(h)
        assert nxt is None or isinstance(nxt, Question)
        assert isinstance(submit_answer(h, h, h, h, h), Interview)
        assert isinstance(auto_answer(h), Interview)
        assert isinstance(import_answers(h, h), Interview)
        assert isinstance(batch_answer(h, h), Interview)
        summary = interview_summary(h)
        assert isinstance(summary, dict)
        assert isinstance(get_questionbank(h), list)
        assert isinstance(submit_answer(itv, h, h, h, h), Interview)
        assert isinstance(batch_answer(itv, h), Interview)
        assert isinstance(import_answers(itv, h), Interview)
        assert isinstance(auto_answer(itv), Interview)
        assert isinstance(interview_summary(itv), dict)
        nxt = next_question(itv)
        assert nxt is None or isinstance(nxt, Question)


def test_fail_open_hostile_interview_fields():
    itv = Interview(title="t")
    itv.questions = _EvilList()
    itv.answers = [_Evil()]
    itv.dimension_scores = _EvilDict()
    itv.open_questions = _EvilList()
    assert next_question(itv) is None
    assert isinstance(submit_answer(itv, _Evil(), _Evil(), _Evil(), _Evil()), Interview)
    assert isinstance(auto_answer(itv), Interview)
    assert isinstance(import_answers(itv, "doc text"), Interview)
    assert isinstance(batch_answer(itv, _EvilDict()), Interview)
    assert isinstance(interview_summary(itv), dict)


def test_fail_open_unhashable_and_nested_values():
    itv = start_interview("t", "general")
    out = submit_answer(itv, [["nested"]], {"deep": [[1], [2]]}, is_custom={"x": 1})
    assert isinstance(out, Interview)
    out = batch_answer(itv, {"q1": [["nested"]], "q2": {"value": {"a": [1]}}})
    assert isinstance(out, Interview)
    assert isinstance(interview_summary(itv), dict)


# --- integration & persistence ----------------------------------------------

def test_interview_reaches_termination():
    itv = start_interview("Finish the workshop", "planning", mode=InterviewMode.INTERVIEW)
    steps = 0
    while steps < 60:
        nxt = next_question(itv)
        if nxt is None:
            break
        submit_answer(itv, nxt.id, "alpha")
        steps += 1
    assert steps <= 20
    assert next_question(itv) is None
    assert itv.coverage() >= DONE_COVERAGE


def test_interview_roundtrips_through_json(workdir):
    itv = start_interview("Round Trip", "coding", mode=InterviewMode.BATCH)
    submit_answer(itv, "q1", "Build a zuzzer")
    path = os.path.join(workdir, "interview.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(itv.to_dict(), fh)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    restored = Interview.from_dict(data)
    assert restored.slug == itv.slug
    assert restored.mode == InterviewMode.BATCH
    assert len(restored.answers) == len(itv.answers)
    assert restored.coverage() == itv.coverage()
    summary = interview_summary(restored)
    assert summary["answered_count"] == 1
    assert summary["title"] == "Round Trip"
