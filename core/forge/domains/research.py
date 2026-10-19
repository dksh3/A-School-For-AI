"""Forge question bank — research.

Investigation of any kind: literature reviews, market research, diligence,
fact-checking, exploratory mapping. Discovery is about the question to answer
and how trustworthy the findings must be.
"""

from __future__ import annotations

from typing import Any

from core.forge.models import Question, QuestionType


def _q(
    qid: str,
    dim: str,
    prompt: str,
    qtype: QuestionType = QuestionType.TEXT,
    options: tuple[str, ...] = (),
    required: bool = False,
    followups: tuple[Question, ...] = (),
    hint: str = "",
) -> Question:
    return Question(
        id=qid,
        dimension=dim,
        prompt=prompt,
        type=qtype,
        options=list(options),
        allow_custom=True,
        followups=list(followups),
        required=required,
        domain_hint=hint,
    )


def _fu(
    qid: str,
    dim: str,
    prompt: str,
    trigger: str,
    qtype: QuestionType = QuestionType.TEXT,
    options: tuple[str, ...] = (),
) -> Question:
    return _q(qid, dim, prompt, qtype, options, hint=f"when:{trigger}")


def QUESTIONS(domain: Any = None) -> list[Question]:
    return [
        _q(
            "res_intent", "intent",
            "What question should this research answer?",
            required=True,
        ),
        _q(
            "res_kind", "intent",
            "What kind of research is it?",
            QuestionType.CHOICE,
            ("A literature review or survey", "Market or competitor research",
             "A scientific or technical investigation",
             "Due diligence on a person or organization", "Fact-checking or verification",
             "Exploratory - map an unknown area"),
            followups=(
                _fu("res_kind_explore", "intent",
                    "What do we already know, and where are the edges of the unknown?",
                    "Exploratory - map an unknown area"),
            ),
        ),
        _q(
            "res_audience", "audience",
            "Who reads the findings?",
            QuestionType.CHOICE,
            ("Me - to make a decision", "A team or lab", "Executives or funders",
             "Students or the public", "Peers who will challenge it", "A paying client"),
            followups=(
                _fu("res_audience_execs", "audience",
                    "How much detail do they want - one page or fifty?",
                    "Executives or funders"),
            ),
        ),
        _q(
            "res_scope", "scope",
            "What should the research cover?",
            QuestionType.MULTI,
            ("The core question only", "Background and definitions",
             "Methodology and its limits", "Key data and evidence",
             "Competing views or papers", "Recommendations or next steps",
             "Gaps left for later"),
        ),
        _q(
            "res_constraints", "constraints",
            "What limits the work?",
            QuestionType.MULTI,
            ("A deadline", "Access limits (paywalls, data, people)", "Budget for sources",
             "Ethics or privacy rules", "Required rigor or citation standard",
             "Language or region limits", "Time I can spend"),
            followups=(
                _fu("res_constraints_access", "constraints",
                    "What can we not reach, and who might help us reach it?",
                    "Access limits (paywalls, data, people)"),
            ),
        ),
        _q(
            "res_success", "success",
            "What would make the findings trustworthy and useful enough to act on?",
            required=True,
        ),
        _q(
            "res_depth", "success",
            "How deep should the evidence go?",
            QuestionType.SCALE,
            ("1 - a quick scan", "2", "3 - a solid, sourced survey", "4",
             "5 - exhaustive and reproducible"),
        ),
        _q(
            "res_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("Existing papers or reports", "Datasets", "Experts to interview",
             "Search tools or subscriptions", "Time each week", "Somewhere to keep notes",
             "Nothing yet"),
        ),
        _q(
            "res_risks", "risks",
            "What could sink the research?",
            QuestionType.MULTI,
            ("Outdated or biased sources", "Too much material to triage",
             "Conflicting evidence", "Weak methodology", "Jumping to conclusions",
             "Findings arrive too late", "Nothing major"),
            followups=(
                _fu("res_risks_conflict", "risks",
                    "How should contradictions be recorded - both sides or a judgment call?",
                    "Conflicting evidence"),
            ),
        ),
        _q(
            "res_sequence", "sequence",
            "Must the work unfold in a strict order (sources before synthesis, "
            "method before results)?",
            QuestionType.CONFIRM,
            followups=(
                _fu("res_sequence_order", "sequence",
                    "What must happen before what?",
                    "Yes"),
            ),
        ),
        _q(
            "res_style", "style",
            "How should the findings be presented?",
            QuestionType.CHOICE,
            ("Technical and precise", "Plain-language summary first",
             "Data and charts forward", "A narrative walkthrough",
             "Neutral and noncommittal", "Match a cited standard or format"),
            followups=(
                _fu("res_style_standard", "style",
                    "Which standard or format (for example APA, an internal template)?",
                    "Match a cited standard or format"),
            ),
        ),
        _q("res_edge", "edge_cases",
           "What would falsify the conclusion? What do we hope is not true?"),
        _q("res_glossary", "glossary",
           "Any terms, names or jargon to define or use consistently?"),
        _q("res_open", "open_questions",
           "What is still unknown or assumed? What should an agent ask if stuck?"),
    ]
