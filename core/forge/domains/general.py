"""Forge question bank — general (the universal fallback).

Handles *any* work item whatever its domain. Every question is domain-neutral
so an agent can discover intent, scope, constraints and success for anything
from a party to a policy to a program.
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
            "gen_intent", "intent",
            "In a sentence or two, what outcome should this produce?",
            required=True,
        ),
        _q(
            "gen_kind", "intent",
            "What kind of work item is this?",
            QuestionType.CHOICE,
            ("Build something new", "Improve something existing", "Make a decision",
             "Produce a document or message", "Plan or organize something",
             "Learn or teach something", "Fix a problem", "Something else entirely"),
            followups=(
                _fu("gen_kind_fix", "intent",
                    "What is broken, how do you know, and since when?",
                    "Fix a problem"),
            ),
        ),
        _q(
            "gen_audience", "audience",
            "Who is it for?",
            QuestionType.CHOICE,
            ("Just me", "A small group or team", "My whole organization",
             "Customers or clients", "A specific person or community", "The public"),
            followups=(
                _fu("gen_audience_team", "audience",
                    "How many people, and what do they already know?",
                    "A small group or team"),
            ),
        ),
        _q(
            "gen_scope", "scope",
            "What should be in scope?",
            QuestionType.MULTI,
            ("The core outcome only", "Docs or explanation", "Training or handover",
             "Ongoing upkeep", "Testing or checking it works", "Nice-to-have extras"),
        ),
        _q(
            "gen_constraints", "constraints",
            "What limits this?",
            QuestionType.MULTI,
            ("A deadline", "A budget", "Tools or platforms",
             "Rules, policies or laws", "People's availability", "A quality bar",
             "Limited time or energy"),
            followups=(
                _fu("gen_constraints_deadline", "constraints",
                    "When is it due, and what happens if it slips?",
                    "A deadline"),
            ),
        ),
        _q(
            "gen_success", "success",
            "What does done and successful look like - how would someone check?",
            required=True,
        ),
        _q(
            "gen_bar", "success",
            "How high is the bar?",
            QuestionType.SCALE,
            ("1 - good enough", "2", "3 - solid and dependable", "4",
             "5 - exceptional"),
        ),
        _q(
            "gen_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("Time", "Money", "People who can help", "Existing material to build on",
             "Tools I have", "Access or permissions", "Nothing yet"),
        ),
        _q(
            "gen_risks", "risks",
            "What could go wrong?",
            QuestionType.MULTI,
            ("Not enough time", "Wrong direction and rework", "Costs grow",
             "Quality problems", "People or coordination failures",
             "Outside dependencies", "Nothing major"),
            followups=(
                _fu("gen_risks_direction", "risks",
                    "What is the cheapest early check of the direction?",
                    "Wrong direction and rework"),
            ),
        ),
        _q(
            "gen_sequence", "sequence",
            "Is there a hard order things must happen in?",
            QuestionType.CONFIRM,
            followups=(
                _fu("gen_sequence_order", "sequence",
                    "What must happen before what?",
                    "Yes"),
            ),
        ),
        _q(
            "gen_style", "style",
            "What style should the result have?",
            QuestionType.CHOICE,
            ("Formal", "Conversational", "Minimal", "Detailed and thorough",
             "Visual or diagram first", "Match an existing example"),
            followups=(
                _fu("gen_style_match", "style",
                    "Which example should it match?",
                    "Match an existing example"),
            ),
        ),
        _q("gen_edge", "edge_cases",
           "What could surprise us or go wrong at the edges?"),
        _q("gen_glossary", "glossary",
           "Any terms, names or jargon to define or use consistently?"),
        _q("gen_open", "open_questions",
           "What is assumed but unconfirmed? What should an agent ask if stuck?"),
    ]
