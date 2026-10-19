"""Forge question bank — creative.

Art, design, music, film, games, handmade work, performances. Discovery is
about what the piece must make people feel or do, and the aesthetic to chase.
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
            "cre_intent", "intent",
            "What are we making, and what should it make people feel or do?",
            required=True,
        ),
        _q(
            "cre_kind", "intent",
            "What kind of work is it?",
            QuestionType.CHOICE,
            ("A visual design (brand, art, UI)", "Writing (story, script, lyrics)",
             "Music or audio", "Video or animation", "A game or interactive piece",
             "A physical or handmade object", "A performance or show"),
            followups=(
                _fu("cre_kind_game", "intent",
                    "What is the core interaction or feeling of play?",
                    "A game or interactive piece"),
            ),
        ),
        _q(
            "cre_audience", "audience",
            "Who experiences it?",
            QuestionType.CHOICE,
            ("Just me", "A specific client or patron", "A niche community",
             "A broad public audience", "Kids or families", "Peers and critics"),
            followups=(
                _fu("cre_audience_client", "audience",
                    "What have they loved (and hated) before?",
                    "A specific client or patron"),
            ),
        ),
        _q(
            "cre_scope", "scope",
            "What should the work include?",
            QuestionType.MULTI,
            ("One finished piece", "A set or series", "Sketches or concepts first",
             "Variations to choose from", "Final production files",
             "A presentation of the work", "Rights or licensing"),
        ),
        _q(
            "cre_constraints", "constraints",
            "What limits the work?",
            QuestionType.MULTI,
            ("A deadline (show, launch, gift)", "A budget for materials",
             "Technical specs (size, format, duration)", "A brand or theme to fit",
             "Tools or software limits", "Collaborator input", "Personal energy"),
            followups=(
                _fu("cre_constraints_specs", "constraints",
                    "Which specs are hard requirements?",
                    "Technical specs (size, format, duration)"),
            ),
        ),
        _q(
            "cre_success", "success",
            "What does finished and good feel like - to whom?",
            required=True,
        ),
        _q(
            "cre_originality", "success",
            "How original versus familiar should it be?",
            QuestionType.SCALE,
            ("1 - comfortably familiar", "2", "3 - fresh but legible", "4",
             "5 - never seen before"),
        ),
        _q(
            "cre_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("References or inspiration", "Materials or instruments",
             "Time in the studio or at the desk", "Collaborators or a critic",
             "Tools or software", "An audience to test on", "Nothing yet"),
        ),
        _q(
            "cre_risks", "risks",
            "What could sink the work?",
            QuestionType.MULTI,
            ("The concept does not land", "Perfectionism stalls finishing",
             "Execution limits the vision", "Audience confusion",
             "Rights or credit disputes", "Burnout before the deadline",
             "Nothing major"),
            followups=(
                _fu("cre_risks_concept", "risks",
                    "What is the fastest sketch we can put in front of someone?",
                    "The concept does not land"),
            ),
        ),
        _q(
            "cre_sequence", "sequence",
            "Is there a fixed process - concept, sketch, draft, final?",
            QuestionType.CONFIRM,
            followups=(
                _fu("cre_sequence_order", "sequence",
                    "What must happen before what?",
                    "Yes"),
            ),
        ),
        _q(
            "cre_style", "style",
            "What aesthetic are we reaching for?",
            QuestionType.CHOICE,
            ("Bold and maximal", "Quiet and minimal", "Retro or nostalgic",
             "Raw and handmade", "Sleek and modern", "Match an existing reference"),
            followups=(
                _fu("cre_style_match", "style",
                    "Which reference - share the look, sound or feel to match?",
                    "Match an existing reference"),
            ),
        ),
        _q("cre_edge", "edge_cases",
           "Where could the piece go wrong, get misread, or feel off?"),
        _q("cre_glossary", "glossary",
           "Names, terms or references the work must use consistently?"),
        _q("cre_open", "open_questions",
           "What is still unknown or assumed? What should an agent ask if stuck?"),
    ]
