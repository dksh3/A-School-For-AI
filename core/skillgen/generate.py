"""Generalization and skill generation (1A-2Z stage 5-6).

Turns one specific experience plus a model judgment into a Skill record.
All fields the model supplies are validated against allowlists/limits; the
model never writes files - 1A-2Z stays in control of the artifact.
"""

from __future__ import annotations

import re
from typing import Any

from core.routing.v26.experience import Experience
from core.skillgen.judge import Judgment
from core.skillgen.types import (
    NAME_RE,
    Skill,
    SkillEvent,
    SkillScope,
    SkillState,
)

_SCOPE_BY_EXPERIENCE = {
    "session": SkillScope.SESSION,
    "project": SkillScope.PROJECT,
    "agent": SkillScope.AGENT,
    "global": SkillScope.GLOBAL,
}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:64].strip("-") or "skill"


def experience_scope(experience: Experience) -> SkillScope:
    """Narrowest scope implied by where the experience happened."""
    if experience.session is not None:
        return SkillScope.SESSION
    if experience.project is not None:
        return SkillScope.PROJECT
    return SkillScope.AGENT


def decide_scope(judgment: Judgment, experience: Experience) -> SkillScope:
    """Model proposes; the pipeline clamps.

    GLOBAL requires generalizable=true and model confidence >= 0.8.
    Otherwise the narrower of (proposal, experience scope) wins.
    """
    proposed = _SCOPE_BY_EXPERIENCE.get(judgment.proposed_scope, SkillScope.SESSION)
    if proposed == SkillScope.GLOBAL:
        if judgment.generalizable and judgment.confidence >= 0.8:
            return SkillScope.GLOBAL
        return experience_scope(experience)
    native = experience_scope(experience)
    order = [SkillScope.SESSION, SkillScope.PROJECT, SkillScope.AGENT, SkillScope.GLOBAL]
    # Narrower wins: a session/project experience may never leak wider than
    # where it happened (GLOBAL escalation is gated above). Narrowing is only
    # allowed when the experience actually carries that identity - a PROJECT
    # skill with an empty project id would be unreachable (caught by self-test).
    if proposed == SkillScope.SESSION and experience.session is None:
        return native
    if proposed == SkillScope.PROJECT and experience.project is None:
        return native
    return proposed if order.index(proposed) <= order.index(native) else native


def _generalize(text: str) -> str:
    """Strip project-specific phrasing from model-provided text."""
    out = text
    for pat in (
        r"\bthis project'?s?\b",
        r"\bthis repo(sitory)?\b",
        r"\bthis specific\b",
        r"\bour (current|local) (repo|project)\b",
    ):
        out = re.sub(pat, "", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip()


def generalize(
    experience: Experience,
    judgment: Judgment,
    model_id: str,
    merge_hint: str = "",
) -> Skill:
    """Build a Skill draft from experience + judgment (not yet validated)."""
    skill_type = judgment.skill_type or "workflow"
    name = _slug(judgment.proposed_name) if judgment.proposed_name else _slug(
        judgment.reason or experience.action or "learned-skill"
    )
    if not NAME_RE.match(name):
        name = f"{skill_type}-{name}"[:64].strip("-")
    scope = decide_scope(judgment, experience)

    procedure = [_generalize(s) for s in judgment.procedure_steps if s.strip()]
    if not procedure:
        procedure = [
            f"Recognize the situation: {_generalize(experience.observation)[:200]}",
            f"Apply the proven approach: {_generalize(experience.action)[:200]}",
            "Verify the outcome matches the expected result.",
        ]
    triggers = [_generalize(t) for t in judgment.triggers if t.strip()]
    if not triggers:
        triggers = [_generalize(experience.observation)[:160]]

    skill = Skill(
        name=name,
        description=_generalize(judgment.reason)[:400] or f"{skill_type} skill",
        purpose=_generalize(experience.observation)[:1000],
        triggers=triggers[:4],
        inputs=[],
        procedure=procedure[:8],
        expected_output=_generalize(experience.feedback)[:500]
        or "The situation described in triggers is resolved.",
        constraints=[
            "This is an instructional procedure, not executable code.",
            "Stay within the task's security and scope boundaries.",
        ],
        confidence=max(0.3, min(judgment.confidence, 0.7)),  # limited initial trust
        created_from=[experience.experience_id],
        state=SkillState.CANDIDATE,
        scope=scope,
        agent_id=experience.agent.agent_id,
        project_id=experience.project.project_id if experience.project else "",
        session_id=experience.session.session_id if experience.session else "",
        tags=[skill_type],
        provenance={
            "created_by": model_id,
            "judge": model_id,
            "skill_type": skill_type,
            "evidence": [experience.experience_id],
            "judgment": judgment.to_dict(),
            "generalized": True,
            "merge_hint": merge_hint or None,
        },
        history=[
            SkillEvent(
                version=1,
                event="generated",
                reason=f"judged worth_creating (conf={judgment.confidence:.2f})",
                timestamp=experience.timestamp or 0.0,
                confidence=max(0.3, min(judgment.confidence, 0.7)),
                experience_id=experience.experience_id,
                actor=model_id,
            )
        ],
    )
    return skill


def build_manual_skill(payload: dict[str, Any], agent_id: str, project: str,
                       session: str) -> Skill:
    """Explicit agent-created skill (skill_create) - starts as CANDIDATE."""
    now_str = 0.0
    scope = _SCOPE_BY_EXPERIENCE.get(str(payload.get("scope", "")))
    if scope is None:
        scope = SkillScope.PROJECT if project else SkillScope.AGENT
    return Skill(
        name=_slug(str(payload.get("name", ""))),
        description=str(payload.get("description", ""))[:4000],
        purpose=str(payload.get("purpose", ""))[:4000],
        triggers=[str(t) for t in payload.get("triggers", [])][:8],
        inputs=[str(i) for i in payload.get("inputs", [])][:8],
        procedure=[str(s) for s in payload.get("procedure", [])][:40],
        expected_output=str(payload.get("expected_output", ""))[:4000],
        constraints=[str(c) for c in payload.get("constraints", [])][:16],
        examples=[str(e) for e in payload.get("examples", [])][:8],
        confidence=max(0.0, min(float(payload.get("confidence", 0.5)), 1.0)),
        created_from=[str(c) for c in payload.get("created_from", [])][:8],
        provenance={"created_by": "manual", "judge": "manual", "evidence": []},
        state=SkillState.CANDIDATE,
        scope=scope,
        agent_id=str(payload.get("agent_id", "")) or agent_id,
        project_id=str(payload.get("project_id", "")) or project,
        session_id=str(payload.get("session_id", "")) or session,
        tags=[str(t) for t in payload.get("tags", [])][:8],
        history=[
            SkillEvent(
                version=1,
                event="created",
                reason="manual creation via skill_create",
                timestamp=now_str,
                confidence=max(0.0, min(float(payload.get("confidence", 0.5)), 1.0)),
                actor=agent_id,
            )
        ],
    )
