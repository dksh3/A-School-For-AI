"""Forge question bank — planning.

Events, projects, moves, schedules, roadmaps, contingency plans. Discovery is
about what must be true when the plan is done and who has to follow it.
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
            "pln_intent", "intent",
            "What are we planning, and what must be true when it is done?",
            required=True,
        ),
        _q(
            "pln_kind", "intent",
            "What kind of plan is this?",
            QuestionType.CHOICE,
            ("An event or occasion", "A project or initiative", "A move or relocation",
             "A personal roadmap", "A schedule or calendar", "Contingency planning",
             "A decision with steps"),
            followups=(
                _fu("pln_kind_event", "intent",
                    "What is the date, size and format of the event?",
                    "An event or occasion"),
            ),
        ),
        _q(
            "pln_audience", "audience",
            "Who has to follow this plan?",
            QuestionType.CHOICE,
            ("Just me", "My household or family", "A team or crew", "An organization",
             "Vendors or contractors", "Guests or participants"),
            followups=(
                _fu("pln_audience_team", "audience",
                    "Who decides when the plan changes mid-flight?",
                    "A team or crew"),
            ),
        ),
        _q(
            "pln_scope", "scope",
            "What should the plan cover?",
            QuestionType.MULTI,
            ("The plan itself only", "Budget tracking", "Vendor or venue selection",
             "Travel and logistics", "Communications or invitations", "Contingencies",
             "Follow-up afterwards"),
        ),
        _q(
            "pln_constraints", "constraints",
            "What limits the plan?",
            QuestionType.MULTI,
            ("A fixed date", "A budget", "People's availability",
             "Location or space limits", "Rules or permissions needed",
             "Weather or seasonality", "Energy or time I have"),
            followups=(
                _fu("pln_constraints_date", "constraints",
                    "Which date is fixed, and what is movable around it?",
                    "A fixed date"),
            ),
        ),
        _q(
            "pln_success", "success",
            "What does went well look like - and how will we know?",
            required=True,
        ),
        _q(
            "pln_detail", "success",
            "How detailed should the plan be?",
            QuestionType.SCALE,
            ("1 - a rough sketch", "2", "3 - milestones and owners", "4",
             "5 - hour by hour"),
        ),
        _q(
            "pln_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("Helpers or co-organizers", "Money", "Templates or past plans",
             "Vehicles or equipment", "Contacts or vendors", "Time to prepare",
             "Nothing yet"),
        ),
        _q(
            "pln_risks", "risks",
            "What could sink the plan?",
            QuestionType.MULTI,
            ("Key people cancel", "Over budget", "Timeline slips",
             "Logistics fail on the day", "Bad weather or bad luck",
             "Too much scope for the time", "Nothing major"),
            followups=(
                _fu("pln_risks_cancel", "risks",
                    "Who is the backup, and what is the minimum viable version?",
                    "Key people cancel"),
            ),
        ),
        _q(
            "pln_sequence", "sequence",
            "Does anything have to happen in a fixed order?",
            QuestionType.CONFIRM,
            followups=(
                _fu("pln_sequence_order", "sequence",
                    "What must happen before what?",
                    "Yes"),
            ),
        ),
        _q(
            "pln_style", "style",
            "How should the plan be presented and run?",
            QuestionType.CHOICE,
            ("A checklist and drill sergeant", "Flexible with options at each step",
             "A visual timeline", "A narrative walkthrough",
             "Minimal - just the essentials", "Match a template we already use"),
            followups=(
                _fu("pln_style_match", "style",
                    "Which template, and what must change?",
                    "Match a template we already use"),
            ),
        ),
        _q("pln_edge", "edge_cases",
           "What is the worst realistic day-of surprise?"),
        _q("pln_glossary", "glossary",
           "Any terms, names or shorthand to use consistently?"),
        _q("pln_open", "open_questions",
           "What is still unknown or assumed? What should an agent ask if stuck?"),
    ]
