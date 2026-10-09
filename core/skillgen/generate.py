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
    safe_float,
    safe_list_str,
    safe_str,
)

_SCOPE_BY_EXPERIENCE = {
    "session": SkillScope.SESSION,
    "project": SkillScope.PROJECT,
    "agent": SkillScope.AGENT,
    "global": SkillScope.GLOBAL,
}


def _slug(text: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", safe_str(text, 200).lower()).strip("-")
    return slug[:64].strip("-") or "skill"


def experience_scope(experience: Experience) -> SkillScope:
    """Narrowest scope implied by where the experience happened."""
    try:
        if experience.session is not None:
            return SkillScope.SESSION
        if experience.project is not None:
            return SkillScope.PROJECT
        return SkillScope.AGENT
    except Exception:  # noqa: BLE001 - hostile experience
        return SkillScope.AGENT


def decide_scope(judgment: Judgment, experience: Experience) -> SkillScope:
    """Model proposes; the pipeline clamps.

    GLOBAL requires generalizable=true and model confidence >= 0.8.
    Otherwise the narrower of (proposal, experience scope) wins.
    """
    try:
        proposed = _SCOPE_BY_EXPERIENCE.get(
            safe_str(judgment.proposed_scope, 32), SkillScope.SESSION
        )
        if proposed == SkillScope.GLOBAL:
            if judgment.generalizable and safe_float(judgment.confidence) >= 0.8:
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
    except Exception:  # noqa: BLE001 - hostile judgment/experience
        return SkillScope.SESSION


def _generalize(text: Any) -> str:
    """Strip project-specific phrasing from model-provided text."""
    out = safe_str(text, 20_000)
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
    skill_type = safe_str(judgment.skill_type, 32) or "workflow"
    proposed = safe_str(judgment.proposed_name, 200)
    name = _slug(proposed) if proposed else _slug(
        safe_str(judgment.reason, 200)
        or safe_str(experience.action, 200)
        or "learned-skill"
    )
    if not NAME_RE.match(name):
        name = f"{skill_type}-{name}"[:64].strip("-")
    scope = decide_scope(judgment, experience)

    procedure = [
        _generalize(s) for s in safe_list_str(judgment.procedure_steps, 6, 400)
        if _generalize(s)
    ]
    if not procedure:
        procedure = [
            f"Recognize the situation: {_generalize(experience.observation)[:200]}",
            f"Apply the proven approach: {_generalize(experience.action)[:200]}",
            "Verify the outcome matches the expected result.",
        ]
    triggers = [
        _generalize(t) for t in safe_list_str(judgment.triggers, 4, 200)
        if _generalize(t)
    ]
    if not triggers:
        triggers = [_generalize(experience.observation)[:160]]
    confidence = max(0.3, min(safe_float(judgment.confidence, 0.5), 0.7))

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
        confidence=confidence,  # limited initial trust
        created_from=[safe_str(experience.experience_id, 200)],
        state=SkillState.CANDIDATE,
        scope=scope,
        agent_id=safe_str(experience.agent.agent_id, 200),
        project_id=safe_str(experience.project.project_id, 200)
        if experience.project
        else "",
        session_id=safe_str(experience.session.session_id, 200)
        if experience.session
        else "",
        tags=[skill_type],
        provenance={
            "created_by": safe_str(model_id, 100),
            "judge": safe_str(model_id, 100),
            "skill_type": skill_type,
            "evidence": [safe_str(experience.experience_id, 200)],
            "judgment": judgment.to_dict(),
            "generalized": True,
            "merge_hint": safe_str(merge_hint, 100) or None,
        },
        history=[
            SkillEvent(
                version=1,
                event="generated",
                reason=f"judged worth_creating (conf={confidence:.2f})",
                timestamp=safe_float(experience.timestamp),
                confidence=confidence,
                experience_id=safe_str(experience.experience_id, 200),
                actor=safe_str(model_id, 100),
            )
        ],
    )
    return skill


def build_manual_skill(payload: Any, agent_id: Any, project: Any,
                       session: Any) -> Skill:
    """Explicit agent-created skill (skill_create) - starts as CANDIDATE.

    Never raises: hostile payloads are coerced to safe bounded fields.
    """
    if not isinstance(payload, dict):
        payload = {}

    def _get(key: str, default: Any = None) -> Any:
        try:
            return payload.get(key, default)
        except Exception:  # noqa: BLE001 - hostile mapping
            return default

    confidence = max(0.0, min(safe_float(_get("confidence", 0.5), 0.5), 1.0))
    scope = _SCOPE_BY_EXPERIENCE.get(safe_str(_get("scope", ""), 32))
    if scope is None:
        scope = SkillScope.PROJECT if safe_str(project, 200) else SkillScope.AGENT
    agent_str = safe_str(agent_id, 200) or "opencode"
    return Skill(
        name=_slug(_get("name", "")),
        description=safe_str(_get("description", ""), 4000),
        purpose=safe_str(_get("purpose", ""), 4000),
        triggers=safe_list_str(_get("triggers", []), 8, 400),
        inputs=safe_list_str(_get("inputs", []), 8, 400),
        procedure=safe_list_str(_get("procedure", []), 40, 4000),
        expected_output=safe_str(_get("expected_output", ""), 4000),
        constraints=safe_list_str(_get("constraints", []), 16, 400),
        examples=safe_list_str(_get("examples", []), 8, 400),
        confidence=confidence,
        created_from=safe_list_str(_get("created_from", []), 8, 200),
        provenance={"created_by": "manual", "judge": "manual", "evidence": []},
        state=SkillState.CANDIDATE,
        scope=scope,
        agent_id=safe_str(_get("agent_id", ""), 200) or agent_str,
        project_id=safe_str(_get("project_id", ""), 200) or safe_str(project, 200),
        session_id=safe_str(_get("session_id", ""), 200) or safe_str(session, 200),
        tags=safe_list_str(_get("tags", []), 8, 100),
        history=[
            SkillEvent(
                version=1,
                event="created",
                reason="manual creation via skill_create",
                timestamp=0.0,
                confidence=confidence,
                actor=agent_str,
            )
        ],
    )
