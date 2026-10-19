"""Forge question bank — ops.

Running systems and operations of any kind: standing up services, migrations,
incidents, runbooks, facilities, logistics. Discovery is about what must run
stably and who carries the pager.
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
            "ops_intent", "intent",
            "What needs to run, change, or stop breaking?",
            required=True,
        ),
        _q(
            "ops_kind", "intent",
            "What kind of ops work is this?",
            QuestionType.CHOICE,
            ("Standing up a new service or system", "A migration or cutover",
             "Incident response or postmortem", "A routine operations runbook",
             "Cost or performance optimization", "Audit or compliance work",
             "Decommissioning something"),
            followups=(
                _fu("ops_kind_migration", "intent",
                    "What moves, from where to where, and how long can it be down?",
                    "A migration or cutover"),
            ),
        ),
        _q(
            "ops_audience", "audience",
            "Who operates this day to day?",
            QuestionType.CHOICE,
            ("A dedicated ops or SRE team", "Developers on rotation",
             "Non-technical staff", "A single owner (me)",
             "External vendors or a managed service",
             "Automated systems plus alerts"),
            followups=(
                _fu("ops_audience_owner", "audience",
                    "What happens when you are unavailable?",
                    "A single owner (me)"),
            ),
        ),
        _q(
            "ops_scope", "scope",
            "What should the work cover?",
            QuestionType.MULTI,
            ("The runbook or procedure", "Monitoring and alerting",
             "A rollback or backout plan", "Access and permissions",
             "Capacity or scaling work", "Documentation and training",
             "Handover to another team"),
        ),
        _q(
            "ops_constraints", "constraints",
            "What limits the work?",
            QuestionType.MULTI,
            ("Uptime or SLA commitments", "Change windows or freeze periods",
             "A budget", "Security or compliance rules",
             "Legacy systems that cannot change", "Staffing or on-call load",
             "Maintenance timing"),
            followups=(
                _fu("ops_constraints_sla", "constraints",
                    "What is the exact commitment, and what is the blast radius if missed?",
                    "Uptime or SLA commitments"),
            ),
        ),
        _q(
            "ops_success", "success",
            "What does stable and boring look like - which signals prove it?",
            required=True,
        ),
        _q(
            "ops_disruption", "success",
            "How much disruption is tolerable?",
            QuestionType.SCALE,
            ("1 - none, ever", "2", "3 - brief and announced", "4",
             "5 - a full maintenance window"),
        ),
        _q(
            "ops_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("On-call staff", "Monitoring tooling", "Runbooks or docs that exist",
             "Staging or test environments", "Vendor support contracts",
             "Time for drills or practice", "Nothing yet"),
        ),
        _q(
            "ops_risks", "risks",
            "What could sink operations?",
            QuestionType.MULTI,
            ("Change breaks production", "Data loss or corruption",
             "Alert fatigue and missed incidents", "Single points of failure",
             "Knowledge stuck in one head", "Costs creep", "Nothing major"),
            followups=(
                _fu("ops_risks_change", "risks",
                    "What is the staged rollout or canary plan?",
                    "Change breaks production"),
            ),
        ),
        _q(
            "ops_sequence", "sequence",
            "Must steps happen in a strict order (checks, then change, then verify)?",
            QuestionType.CONFIRM,
            followups=(
                _fu("ops_sequence_order", "sequence",
                    "What must happen before what?",
                    "Yes"),
            ),
        ),
        _q(
            "ops_style", "style",
            "How should procedures be written and run?",
            QuestionType.CHOICE,
            ("A checklist, no prose", "A narrative runbook with rationale",
             "Automation first, docs as backup", "Blameless and calm",
             "Strict and compliance heavy", "Match our existing runbooks"),
            followups=(
                _fu("ops_style_match", "style",
                    "Which runbook format should it match?",
                    "Match our existing runbooks"),
            ),
        ),
        _q("ops_edge", "edge_cases",
           "What happens at 3 a.m. when half the inputs are wrong?"),
        _q("ops_glossary", "glossary",
           "System names, acronyms and jargon that must be used precisely?"),
        _q("ops_open", "open_questions",
           "What is still unknown or assumed? What should an agent ask if stuck?"),
    ]
