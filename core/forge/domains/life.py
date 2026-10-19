"""Forge question bank — life.

Personal goals of every kind: health, money, home, learning, habits,
relationships, careers. Discovery is about the life change wanted and the
smallest version that survives a bad week.
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
            "lif_intent", "intent",
            "What are you trying to change or create in your life - and why now?",
            required=True,
        ),
        _q(
            "lif_kind", "intent",
            "What part of life is this about?",
            QuestionType.CHOICE,
            ("Health or fitness", "Money or budgeting", "Home or a move",
             "Learning or a personal project", "Relationships or community",
             "Career or work life", "A habit or a fresh start"),
            followups=(
                _fu("lif_kind_health", "intent",
                    "What does better feel like day to day - and is a doctor in the loop?",
                    "Health or fitness"),
            ),
        ),
        _q(
            "lif_audience", "audience",
            "Who is involved or affected?",
            QuestionType.CHOICE,
            ("Just me", "My household or family", "Friends or a community",
             "A coach or professional", "My workplace", "People I am caring for"),
            followups=(
                _fu("lif_audience_household", "audience",
                    "Who else gets a vote in the plan?",
                    "My household or family"),
            ),
        ),
        _q(
            "lif_scope", "scope",
            "What should the plan cover?",
            QuestionType.MULTI,
            ("The goal itself", "A routine or schedule", "Tracking or journaling",
             "Buying or arranging things", "Learning what I need to know",
             "Asking for help", "Celebrating milestones"),
        ),
        _q(
            "lif_constraints", "constraints",
            "What limits this?",
            QuestionType.MULTI,
            ("My time and energy", "Money", "Health limits",
             "Family or work obligations", "Where I live", "Motivation and habits",
             "Tools or access"),
            followups=(
                _fu("lif_constraints_money", "constraints",
                    "What is a comfortable spend, and what is off-limits?",
                    "Money"),
            ),
        ),
        _q(
            "lif_success", "success",
            "How will future-you know this worked - what does a good week look like?",
            required=True,
        ),
        _q(
            "lif_size", "success",
            "How big a change is this?",
            QuestionType.SCALE,
            ("1 - a small tweak", "2", "3 - a steady shift", "4",
             "5 - a life overhaul"),
        ),
        _q(
            "lif_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("People who support me", "Time in my week", "Money to invest",
             "Apps, gear or tools", "Past attempts to learn from",
             "Professionals to lean on", "Nothing yet"),
        ),
        _q(
            "lif_risks", "risks",
            "What could throw this off?",
            QuestionType.MULTI,
            ("Losing motivation after week two", "Overcommitting and burning out",
             "Family or work pushes back", "Costs surprise me",
             "Comparing myself to others", "Hidden health issues", "Nothing major"),
            followups=(
                _fu("lif_risks_motivation", "risks",
                    "What is the smallest version I can keep on my worst week?",
                    "Losing motivation after week two"),
            ),
        ),
        _q(
            "lif_sequence", "sequence",
            "Is there a natural order - small steps first, or one big first move?",
            QuestionType.CONFIRM,
            followups=(
                _fu("lif_sequence_order", "sequence",
                    "What must come before what?",
                    "Yes"),
            ),
        ),
        _q(
            "lif_style", "style",
            "What kind of plan fits how you live?",
            QuestionType.CHOICE,
            ("Gentle and forgiving", "Structured with accountability",
             "Spontaneous with loose guardrails", "Data and habit tracking",
             "Social - done with others", "Match a routine I already have"),
            followups=(
                _fu("lif_style_match", "style",
                    "Which routine should it fit around?",
                    "Match a routine I already have"),
            ),
        ),
        _q("lif_edge", "edge_cases",
           "What could throw this off - travel, stress, illness, holidays?"),
        _q("lif_glossary", "glossary",
           "Names, words or shorthand that matter in how you talk about this?"),
        _q("lif_open", "open_questions",
           "What are you unsure about? What should an agent ask before advising?"),
    ]
