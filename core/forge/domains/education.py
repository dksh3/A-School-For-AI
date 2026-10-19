"""Forge question bank — education.

Courses, lessons, tutoring, curricula, study plans, assessments. Discovery is
about what the learner must be able to do and how learning will be proven.
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
            "edu_intent", "intent",
            "What should the learner know or be able to do at the end?",
            required=True,
        ),
        _q(
            "edu_kind", "intent",
            "What are we making?",
            QuestionType.CHOICE,
            ("A course or curriculum", "A single lesson or session", "A study plan",
             "Assessments or quizzes", "Learning materials or handouts",
             "Tutoring or coaching", "An exam or certification push"),
            followups=(
                _fu("edu_kind_course", "intent",
                    "How many sessions, at what pace, over how long?",
                    "A course or curriculum"),
            ),
        ),
        _q(
            "edu_audience", "audience",
            "Who is learning?",
            QuestionType.CHOICE,
            ("Complete beginners", "Learners with some background",
             "Advanced or professional learners", "Children or teens",
             "Adult learners returning to study", "A mixed group"),
            followups=(
                _fu("edu_audience_beginners", "audience",
                    "What do they already know, and what will scare them?",
                    "Complete beginners"),
            ),
        ),
        _q(
            "edu_scope", "scope",
            "What should the learning cover?",
            QuestionType.MULTI,
            ("Core learning goals only", "Practice exercises",
             "Assessments or grading", "Reading or media lists",
             "Real-world projects", "Remedial or stretch material",
             "Progress tracking"),
        ),
        _q(
            "edu_constraints", "constraints",
            "What limits the learning?",
            QuestionType.MULTI,
            ("Class time or deadlines", "A syllabus or standard to follow",
             "Learner time outside class", "Materials or tech available",
             "Accessibility needs", "Language of instruction",
             "Budget for resources"),
            followups=(
                _fu("edu_constraints_syllabus", "constraints",
                    "Which syllabus or standard must it map to?",
                    "A syllabus or standard to follow"),
            ),
        ),
        _q(
            "edu_success", "success",
            "How will we know learning happened - what can the learner do then?",
            required=True,
        ),
        _q(
            "edu_rigor", "success",
            "How rigorous should the assessment be?",
            QuestionType.SCALE,
            ("1 - self-check only", "2", "3 - quizzes and feedback", "4",
             "5 - a formal exam"),
        ),
        _q(
            "edu_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("Existing materials to reuse", "Time to prepare",
             "Devices or teaching tech", "Guests or co-teachers",
             "Practice data or problems", "Feedback from past learners",
             "Nothing yet"),
        ),
        _q(
            "edu_risks", "risks",
            "What could sink the learning?",
            QuestionType.MULTI,
            ("Learners disengage", "Wrong difficulty level",
             "Too much material for the time",
             "Assessment does not measure learning", "Accessibility barriers",
             "Learners take shortcuts", "Nothing major"),
            followups=(
                _fu("edu_risks_level", "risks",
                    "How should we calibrate - a diagnostic, a pilot, or both?",
                    "Wrong difficulty level"),
            ),
        ),
        _q(
            "edu_sequence", "sequence",
            "Must topics be learned in a fixed order?",
            QuestionType.CONFIRM,
            followups=(
                _fu("edu_sequence_order", "sequence",
                    "What must come before what?",
                    "Yes"),
            ),
        ),
        _q(
            "edu_style", "style",
            "What teaching style fits?",
            QuestionType.CHOICE,
            ("Guided and scaffolded", "Discovery and problem first",
             "Lecture plus practice", "Peer discussion and collaboration",
             "Gamified and playful", "Match a curriculum or textbook"),
            followups=(
                _fu("edu_style_match", "style",
                    "Which curriculum or textbook should it follow?",
                    "Match a curriculum or textbook"),
            ),
        ),
        _q("edu_edge", "edge_cases",
           "What happens when a learner is far ahead, far behind, or unmotivated?"),
        _q("edu_glossary", "glossary",
           "Which terms must be defined carefully before they are used?"),
        _q("edu_open", "open_questions",
           "What is still unknown or assumed? What should an agent ask if stuck?"),
    ]
