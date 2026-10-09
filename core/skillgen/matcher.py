"""Skill discovery and matching (1A-2Z stage 9: retrieval for reuse).

Lexical ranking over triggers/description/tags with scope isolation and
state filtering (only ACTIVE/PROVEN skills are offered for use). All entry
points are fail-open: hostile queries/limits/registries yield empty results
instead of raising.
"""

from __future__ import annotations

from typing import Any

from core.skillgen.registry import SkillRegistry, _tokens
from core.skillgen.types import (
    RETRIEVABLE_STATES,
    Skill,
    safe_float,
    safe_int,
    scope_visible,
)


def score_match(skill: Skill, query: Any) -> float:
    """Rank how well a skill matches the task query in [0, 1]. Never raises."""
    try:
        q = _tokens(query)
        if not q:
            return 0.0
        trigger_tokens: set[str] = set()
        for trig in skill.triggers or []:
            trigger_tokens |= _tokens(trig)
        name_tokens = _tokens(skill.name)
        desc_tokens = _tokens(skill.description)
        tag_tokens = _tokens(" ".join(str(t) for t in (skill.tags or [])))
        hits = len(q & trigger_tokens) + len(q & name_tokens)
        soft = len(q & desc_tokens) + len(q & tag_tokens)
        score = (2.0 * hits + 0.6 * soft) / (2.0 * len(q) + 0.6 * len(q))
        return round(min(1.0, max(0.0, score)), 4)
    except Exception:  # noqa: BLE001 - hostile skill/query
        return 0.0


def match(
    registry: SkillRegistry,
    query: Any,
    *,
    agent_id: Any = "opencode",
    project_id: Any = "",
    session_id: Any = "",
    include_unusable: Any = False,
    limit: Any = 5,
) -> list[dict[str, object]]:
    """Scored, scope-filtered skill matches for a task query. Never raises."""
    scored: list[tuple[float, Skill]] = []
    try:
        try:
            usable_only = not bool(include_unusable)
        except Exception:  # noqa: BLE001 - hostile __bool__
            usable_only = True
        max_results = max(1, min(safe_int(limit, 5), 100))
        for skill in registry.all():
            if not scope_visible(skill, agent_id, project_id, session_id):
                continue
            if usable_only and skill.state not in RETRIEVABLE_STATES:
                continue
            s = score_match(skill, query)
            if s > 0:
                scored.append((s, skill))
        scored.sort(
            key=lambda t: (t[0], safe_float(t[1].confidence, 0.5)), reverse=True
        )
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
            for score, s in scored[:max_results]
        ]
    except Exception:  # noqa: BLE001 - hostile registry/fields
        return []


__all__ = ["match", "score_match"]
