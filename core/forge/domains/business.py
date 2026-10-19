"""Forge question bank — business.

Products, strategy, growth, operations of a company, deals, forecasts.
Discovery is about the outcome that moves the business and who must buy in.
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
            "biz_intent", "intent",
            "What business outcome are we aiming for?",
            required=True,
        ),
        _q(
            "biz_kind", "intent",
            "What kind of work is this?",
            QuestionType.CHOICE,
            ("A new product or offer", "A growth or marketing plan",
             "A strategy or positioning decision", "A process or org change",
             "A financial case or forecast", "A partnership or deal",
             "A turnaround or fix"),
            followups=(
                _fu("biz_kind_finance", "intent",
                    "What decision does the number have to support?",
                    "A financial case or forecast"),
            ),
        ),
        _q(
            "biz_audience", "audience",
            "Who has to buy in - or buy?",
            QuestionType.CHOICE,
            ("Customers or users", "An internal team", "Executives or a board",
             "Investors or lenders", "Partners or vendors", "Regulators or the public"),
            followups=(
                _fu("biz_audience_investors", "audience",
                    "What proof will they demand before saying yes?",
                    "Investors or lenders"),
            ),
        ),
        _q(
            "biz_scope", "scope",
            "What should the deliverable cover?",
            QuestionType.MULTI,
            ("The core deliverable only", "Market analysis", "Pricing or unit economics",
             "Go-to-market actions", "Metrics and dashboards", "Risks and contingencies",
             "Handover or training"),
        ),
        _q(
            "biz_constraints", "constraints",
            "What limits the plan?",
            QuestionType.MULTI,
            ("A budget", "A deadline or launch date", "Team capacity",
             "Legal or compliance rules", "Brand or quality standards",
             "Existing commitments", "Cash-flow limits"),
            followups=(
                _fu("biz_constraints_budget", "constraints",
                    "What is the budget ceiling, and what is flexible?",
                    "A budget"),
            ),
        ),
        _q(
            "biz_success", "success",
            "What does success look like - which numbers or outcomes prove it?",
            required=True,
        ),
        _q(
            "biz_bar", "success",
            "How aggressive is the target?",
            QuestionType.SCALE,
            ("1 - keep the lights on", "2", "3 - solid, expected growth", "4",
             "5 - change the game"),
        ),
        _q(
            "biz_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("Team members", "Marketing channels", "Existing customers to ask",
             "Data or analytics", "Tools or vendors", "Advisors or mentors",
             "Nothing yet"),
        ),
        _q(
            "biz_risks", "risks",
            "What could sink this?",
            QuestionType.MULTI,
            ("Customers do not want it", "Competitors move first",
             "Costs outrun revenue", "Execution by the team slips",
             "Regulatory or legal trouble", "A key person leaves", "Nothing major"),
            followups=(
                _fu("biz_risks_demand", "risks",
                    "What is the cheapest way to test demand before committing?",
                    "Customers do not want it"),
            ),
        ),
        _q(
            "biz_sequence", "sequence",
            "Are there dependencies that force an order (budget approval, hiring, legal)?",
            QuestionType.CONFIRM,
            followups=(
                _fu("biz_sequence_order", "sequence",
                    "What must happen before what?",
                    "Yes"),
            ),
        ),
        _q(
            "biz_style", "style",
            "How should the output feel to its audience?",
            QuestionType.CHOICE,
            ("Bold and visionary", "Conservative and evidence led",
             "Data first, narrative second", "Warm and customer centric",
             "Internal and candid", "Match the company's existing materials"),
            followups=(
                _fu("biz_style_match", "style",
                    "Which materials should it match?",
                    "Match the company's existing materials"),
            ),
        ),
        _q("biz_edge", "edge_cases",
           "What market, team or cash surprises could break the plan?"),
        _q("biz_glossary", "glossary",
           "Any terms, names or jargon to define or use consistently?"),
        _q("biz_open", "open_questions",
           "What is still unknown or assumed? What should an agent ask if stuck?"),
    ]
