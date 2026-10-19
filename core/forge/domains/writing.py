"""Forge question bank — writing.

Essays, books, articles, documentation, copy, speeches. Discovery is about the
reader and the effect the words must have, whatever the genre.
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
            "wri_intent", "intent",
            "What are you writing, and what should it achieve for its reader?",
            required=True,
        ),
        _q(
            "wri_kind", "intent",
            "What kind of piece is it?",
            QuestionType.CHOICE,
            ("An essay or article", "A book or long-form work", "A blog post or newsletter",
             "A report or whitepaper", "Documentation or a guide",
             "Marketing copy or a pitch", "A speech or script"),
            followups=(
                _fu("wri_kind_book", "intent",
                    "Roughly how long is it, and who is it published for?",
                    "A book or long-form work"),
            ),
        ),
        _q(
            "wri_audience", "audience",
            "Who reads it?",
            QuestionType.CHOICE,
            ("Experts in the field", "Curious beginners", "Colleagues or classmates",
             "Customers or buyers", "A specific client or editor", "A general audience"),
            followups=(
                _fu("wri_audience_experts", "audience",
                    "How expert exactly - and what would bore them?",
                    "Experts in the field"),
            ),
        ),
        _q(
            "wri_scope", "scope",
            "What should it cover?",
            QuestionType.MULTI,
            ("A single core argument or story", "Background and context",
             "Examples and case studies", "Data, quotes or citations",
             "Practical how-to steps", "Counterarguments", "A call to action"),
        ),
        _q(
            "wri_constraints", "constraints",
            "What limits the piece?",
            QuestionType.MULTI,
            ("A word or page count", "A deadline", "A house style or style guide",
             "Required sources or evidence", "Sensitivity or legal limits",
             "A fixed format or template", "An editor's tone"),
            followups=(
                _fu("wri_constraints_length", "constraints",
                    "What is the target length, and how firm is it?",
                    "A word or page count"),
            ),
        ),
        _q(
            "wri_success", "success",
            "What does finished and successful look like - who says so?",
            required=True,
        ),
        _q(
            "wri_bar", "success",
            "How polished must the prose be?",
            QuestionType.SCALE,
            ("1 - rough draft", "2", "3 - clean and readable", "4",
             "5 - publication ready"),
        ),
        _q(
            "wri_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("Time to write", "Source material or notes", "People to interview or ask",
             "A model piece to imitate", "An editor or reviewer",
             "Research access (library, databases)", "Nothing yet"),
        ),
        _q(
            "wri_risks", "risks",
            "What could sink the piece?",
            QuestionType.MULTI,
            ("Wrong angle for the audience", "Not enough material to say",
             "Scope sprawl past the deadline", "Flat or boring writing",
             "Factual errors", "Tone misfires", "Nothing major"),
            followups=(
                _fu("wri_risks_angle", "risks",
                    "What is the one-paragraph version we could test on a reader first?",
                    "Wrong angle for the audience"),
            ),
        ),
        _q(
            "wri_sequence", "sequence",
            "Is there a hard order - outline before drafts, chapters in sequence?",
            QuestionType.CONFIRM,
            followups=(
                _fu("wri_sequence_order", "sequence",
                    "What must come before what?",
                    "Yes"),
            ),
        ),
        _q(
            "wri_style", "style",
            "What voice fits?",
            QuestionType.CHOICE,
            ("Formal and authoritative", "Warm and conversational", "Wry or playful",
             "Spare and direct", "Academic and careful",
             "Match an existing author or example"),
            followups=(
                _fu("wri_style_match", "style",
                    "Whose voice, or which piece, should it match?",
                    "Match an existing author or example"),
            ),
        ),
        _q("wri_edge", "edge_cases",
           "What topics, readers or sensitivities could go wrong?"),
        _q("wri_glossary", "glossary",
           "Any terms, names or jargon to define or use consistently?"),
        _q("wri_open", "open_questions",
           "What is still assumed? What should an agent ask if unsure?"),
    ]
