"""Skill discovery and matching (1A-2Z stage 9: retrieval for reuse).

Lexical ranking over triggers/description/tags with scope isolation and
state filtering (only ACTIVE/PROVEN skills are offered for use).
"""

from __future__ import annotations

from core.skillgen.registry import SkillRegistry, _tokens
from core.skillgen.types import RETRIEVABLE_STATES, Skill, scope_visible


def score_match(skill: Skill, query: str) -> float:
    """Rank how well a skill matches the task query in [0, 1]."""
    q = _tokens(query)
    if not q:
        return 0.0
    trigger_tokens: set[str] = set()
    for trig in skill.triggers:
        trigger_tokens |= _tokens(trig)
    name_tokens = _tokens(skill.name)
    desc_tokens = _tokens(skill.description)
    tag_tokens = _tokens(" ".join(skill.tags))
    hits = len(q & trigger_tokens) + len(q & name_tokens)
    soft = len(q & desc_tokens) + len(q & tag_tokens)
    score = (2.0 * hits + 0.6 * soft) / (2.0 * len(q) + 0.6 * len(q))
    return round(min(1.0, score), 4)


def match(
    registry: SkillRegistry,
    query: str,
    *,
    agent_id: str = "opencode",
    project_id: str = "",
    session_id: str = "",
    include_unusable: bool = False,
    limit: int = 5,
) -> list[dict[str, object]]:
    """Scored, scope-filtered skill matches for a task query."""
    scored: list[tuple[float, Skill]] = []
    for skill in registry.all():
        if not scope_visible(skill, agent_id, project_id, session_id):
            continue
        if not include_unusable and skill.state not in RETRIEVABLE_STATES:
            continue
        s = score_match(skill, query)
        if s > 0:
            scored.append((s, skill))
    scored.sort(key=lambda t: (t[0], t[1].confidence), reverse=True)
    return [
        {
            "name": s.name,
            "score": score,
            "state": s.state.value,
            "scope": s.scope.value,
            "confidence": s.confidence,
            "description": s.description,
            "triggers": list(s.triggers),
            "version": s.version,
        }
        for score, s in scored[: max(1, limit)]
    ]
