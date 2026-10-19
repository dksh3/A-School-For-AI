"""Forge question bank — coding.

Building software of any kind: apps, scripts, sites, bots, libraries, fixes.
Discovery is about the *outcome* and its users, never the stack — this bank is
for every agent and every kind of software work.
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
            "cod_intent", "intent",
            "What should the software do when it is done? Describe the outcome.",
            required=True,
        ),
        _q(
            "cod_kind", "intent",
            "What are we building?",
            QuestionType.CHOICE,
            ("A new app or service", "A script or automation", "A website or landing page",
             "A library or tool for others", "A fix or refactor of existing code",
             "A prototype to test an idea"),
            followups=(
                _fu("cod_kind_fix", "intent",
                    "What is broken today, how do you know, and since when?",
                    "A fix or refactor of existing code"),
            ),
        ),
        _q(
            "cod_audience", "audience",
            "Who uses it?",
            QuestionType.CHOICE,
            ("Just me", "My team", "Other developers", "Customers or end users",
             "A paying client", "The public"),
            followups=(
                _fu("cod_audience_users", "audience",
                    "Roughly how many users, what do they expect, and how technical are they?",
                    "Customers or end users"),
            ),
        ),
        _q(
            "cod_scope", "scope",
            "What must be in the first working version?",
            QuestionType.MULTI,
            ("Core feature only (an MVP)", "User interface or screens", "Data storage",
             "Accounts or sign-in", "Integrations with other systems",
             "Tests and documentation", "Deployed to a real environment"),
        ),
        _q(
            "cod_constraints", "constraints",
            "What limits the build?",
            QuestionType.MULTI,
            ("A deadline", "A budget", "A required language or platform",
             "Systems it must fit into", "A performance or reliability bar",
             "Security or privacy rules", "Solo effort only"),
            followups=(
                _fu("cod_constraints_deadline", "constraints",
                    "When is it due, and what happens if it slips?",
                    "A deadline"),
            ),
        ),
        _q(
            "cod_success", "success",
            "What does working and done look like? How will someone check it?",
            required=True,
        ),
        _q(
            "cod_bar", "success",
            "How high is the quality bar?",
            QuestionType.SCALE,
            ("1 - works on my machine", "2", "3 - solid for daily use", "4",
             "5 - production grade"),
        ),
        _q(
            "cod_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("Time each week", "Budget for tools or hosting", "People who can help",
             "Existing code to build on", "Devices or test environments",
             "APIs, data or services", "Nothing yet"),
        ),
        _q(
            "cod_risks", "risks",
            "What could sink this?",
            QuestionType.MULTI,
            ("Unclear requirements", "The chosen approach is wrong", "Scope keeps growing",
             "Bugs or quality problems", "Integrations fail", "Not enough time",
             "Nothing major"),
            followups=(
                _fu("cod_risks_approach", "risks",
                    "What is the cheapest spike or experiment to test the approach first?",
                    "The chosen approach is wrong"),
            ),
        ),
        _q(
            "cod_sequence", "sequence",
            "Must it come together in a hard order (for example data model before UI)?",
            QuestionType.CONFIRM,
            followups=(
                _fu("cod_sequence_order", "sequence",
                    "What must happen before what?",
                    "Yes"),
            ),
        ),
        _q(
            "cod_style", "style",
            "What should the code and its output feel like?",
            QuestionType.CHOICE,
            ("Simple and minimal", "Well documented and beginner friendly", "Fast and lean",
             "Heavily tested and robust", "Match the existing codebase",
             "Whatever gets it done"),
            followups=(
                _fu("cod_style_match", "style",
                    "Which parts should it match - naming, structure, tooling?",
                    "Match the existing codebase"),
            ),
        ),
        _q("cod_edge", "edge_cases",
           "What weird inputs, failures or environments should it survive?"),
        _q("cod_glossary", "glossary",
           "Any terms, names, acronyms or conventions that must be used consistently?"),
        _q("cod_open", "open_questions",
           "What is still unknown or assumed? What should an agent ask you if stuck?"),
    ]
