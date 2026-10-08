"""Local duplicate detection and improvement comparison (Phase 2).

Reuses Phase 1 similarity()/SIMILARITY_MERGE. An equivalent capability
becomes duplicate_of (no second skill). A better external candidate is only
REPORTED - actual local evolution always goes through Phase 1's evolve
mechanism with explicit user approval. Never silent replacement.
"""

from __future__ import annotations

from typing import Any

from core.skillgen.registry import SIMILARITY_MERGE, SkillRegistry, similarity
from core.skillgen.types import Skill, SkillState


def _probe_skill(capability: dict[str, Any], repo_full_name: str) -> Skill:
    """Lightweight Skill used only for similarity scoring (not persisted)."""
    return Skill(
        name="github-probe",
        description=str(capability.get("description", ""))[:4000],
        purpose=f"capability from {repo_full_name}"[:4000],
        triggers=[str(t)[:120] for t in capability.get("triggers", [])][:8],
        procedure=[str(s)[:300] for s in capability.get("procedure", [])][:40],
        state=SkillState.CANDIDATE,
    )


def find_local_duplicate(
    capability: dict[str, Any],
    registry: SkillRegistry,
    repo_full_name: str = "",
) -> tuple[str, float]:
    """Return (duplicate_of, similarity). duplicate_of empty = no duplicate."""
    probe = _probe_skill(capability, repo_full_name)
    best: tuple[str, float] | None = registry.best_match(probe)
    if best and best[1] >= SIMILARITY_MERGE:
        return best[0], round(best[1], 4)
    return "", round(best[1], 4) if best else 0.0


def _coverage(skill: Skill) -> dict[str, Any]:
    return {
        "procedure_steps": len(skill.procedure),
        "triggers": len(skill.triggers),
        "examples": len(skill.examples),
        "constraints": len(skill.constraints),
        "description_len": len(skill.description),
        "has_provenance": bool(skill.provenance),
        "success_count": skill.success_count,
        "confidence": round(skill.confidence, 3),
        "state": skill.state.value,
    }


def improvement_report(existing: Skill, candidate: Skill) -> dict[str, Any]:
    """Deterministic side-by-side comparison. Requires explicit approval to act on."""
    a, b = _coverage(existing), _coverage(candidate)
    existing_score = (
        a["procedure_steps"] * 2 + a["triggers"] + a["examples"] * 2 + a["constraints"]
    )
    candidate_score = (
        b["procedure_steps"] * 2 + b["triggers"] + b["examples"] * 2 + b["constraints"]
    )
    if candidate_score > existing_score * 1.3:
        verdict = "candidate_stronger"
    elif existing_score > candidate_score * 1.3:
        verdict = "existing_stronger"
    else:
        verdict = "comparable"
    return {
        "existing": {"name": existing.name, **a},
        "candidate": {"name": candidate.name, **b},
        "verdict": verdict,
        "similarity": round(similarity(existing, candidate), 4),
        "requires_approval": True,
        "note": (
            "Comparison only. Use school_skill_evolve (Phase 1) with explicit "
            "user approval to revise the local skill - never a silent replace."
        ),
    }


__all__ = ["find_local_duplicate", "improvement_report"]
