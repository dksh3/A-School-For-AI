"""Forge — the Universal Idea→Artifact suite.

Interview-driven design: a discovery interview (`clarion`) gathers intent via
adaptive, scored questions; then one pass emits five distinct artifacts:

- `blueprint`  — the design spec
- `edict`      — ordered commands + always/never directives
- `weave`      — formations (phases, roadmap, dependency graph, lanes)
- `compass`    — acceptance (Given/When/Then, checklist, success metrics)
- `prism`      — divergent→convergent brainstorming (standalone)

Domain-agnostic by construction: every artifact adapts to one of 11 domains
(coding, writing, research, business, planning, education, creative, ops,
data, life, general) — and to *any* domain via the universal fallback. This
suite is for every type of AI/agent and every type of work, not just coding.

Artifacts are stored at ``.school/forge/<slug>/`` and rendered to Markdown
plus School visuals (via ``core.context.visuals``). Every module is fail-open.
"""

from __future__ import annotations

from core.forge.models import (
    _DIMENSIONS,
    AcceptanceCriteria,
    Artifact,
    Blueprint,
    BrainstormSession,
    Command,
    Directive,
    Domain,
    Formation,
    FormationKind,
    Idea,
    Interview,
    InterviewMode,
    Question,
    QuestionType,
    RequirementAnswer,
)

__all__ = [
    "AcceptanceCriteria",
    "Artifact",
    "Blueprint",
    "BrainstormSession",
    "Command",
    "Directive",
    "Domain",
    "Formation",
    "FormationKind",
    "Idea",
    "Interview",
    "InterviewMode",
    "Question",
    "QuestionType",
    "RequirementAnswer",
    "_DIMENSIONS",
]
