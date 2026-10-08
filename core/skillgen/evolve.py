"""Skill evolution: feedback -> confidence -> lifecycle transitions.

Reuses core.learner.confidence.bayesian_evidence_strength as the single
confidence primitive (no second confidence engine). States follow the
skill lifecycle: CANDIDATE -> VALIDATING -> ACTIVE -> PROVEN, with
SUPERSEDED/ARCHIVED demotions on repeated failure or replacement.
"""

from __future__ import annotations

from typing import Any

from core.learner.confidence import bayesian_evidence_strength
from core.skillgen.registry import SIMILARITY_MERGE, SkillRegistry, similarity
from core.skillgen.types import Skill, SkillState

PROVEN_MIN_SUCCESSES = 5
PROVEN_MIN_CONFIDENCE = 0.7
PROVEN_MAX_FAILURE_RATIO = 0.25
DEMOTE_AFTER_FAILURES = 3
ARCHIVE_AFTER_FAILURES = 5
_INITIAL_PRIOR = 2.0
_NEUTRAL_PRIOR = 0.5


def next_confidence(skill: Skill, success: bool) -> float:
    """Update confidence from evidence using the existing confidence engine.

    Neutral prior (0.5) with Bayesian smoothing; each success moves the
    score halfway toward the evidence strength (+small step), each failure
    applies a proportional penalty. Never decreases on success.
    """
    if success:
        strength = bayesian_evidence_strength(
            _NEUTRAL_PRIOR,
            skill.success_count,
            skill.failure_count,
            _INITIAL_PRIOR,
        )
        blended = (skill.confidence + strength) / 2.0 + 0.05
        return round(min(1.0, max(skill.confidence, blended)), 4)
    # Failure pulls down proportionally to failure weight.
    penalty = 0.15 + 0.1 * min(skill.failure_count, 5)
    return round(max(0.05, skill.confidence - penalty), 4)


def apply_feedback(
    skill: Skill,
    success: bool,
    note: str = "",
    experience_id: str = "",
) -> Skill:
    """Record a reuse outcome and advance/retreat the lifecycle."""
    if success:
        skill.success_count += 1
    else:
        skill.failure_count += 1
    skill.use_count += 1
    skill.confidence = next_confidence(skill, success)
    skill.record(
        "success" if success else "failure",
        note or ("reuse succeeded" if success else "reuse failed"),
        experience_id=experience_id,
    )
    evaluate_lifecycle(skill)
    return skill


def evaluate_lifecycle(skill: Skill) -> SkillState:
    """Recompute the state from counters. ARCHIVED/SUPERSEDED are sticky."""
    if skill.state in {SkillState.ARCHIVED, SkillState.SUPERSEDED}:
        return skill.state
    total = skill.success_count + skill.failure_count
    failures = skill.failure_count
    if skill.state == SkillState.CANDIDATE:
        # Validation/registering path promotes CANDIDATE externally; here we
        # only demote nothing below CANDIDATE.
        return skill.state
    if skill.state == SkillState.VALIDATING:
        return skill.state
    if failures >= ARCHIVE_AFTER_FAILURES and (
        total == 0 or failures / max(total, 1) >= 0.6
    ):
        skill.state = SkillState.ARCHIVED
        skill.record("archived", f"{failures} failures dominate history")
    elif failures >= DEMOTE_AFTER_FAILURES and skill.state in {
        SkillState.ACTIVE,
        SkillState.PROVEN,
    }:
        skill.state = SkillState.CANDIDATE
        skill.confidence = min(skill.confidence, 0.4)
        skill.record("demoted", f"{failures} failures - back to candidate")
    elif (
        skill.state == SkillState.ACTIVE
        and skill.success_count >= PROVEN_MIN_SUCCESSES
        and skill.confidence >= PROVEN_MIN_CONFIDENCE
        and (total == 0 or failures / max(total, 1) <= PROVEN_MAX_FAILURE_RATIO)
    ):
        skill.state = SkillState.PROVEN
        skill.record(
            "proven",
            f"{skill.success_count} successes at conf={skill.confidence:.2f}",
        )
    return skill.state


def consolidate(registry: SkillRegistry) -> list[dict[str, Any]]:
    """Merge near-duplicate skills (similarity >= SIMILARITY_MERGE).

    The newer/higher-confidence skill survives; older ones are superseded.
    """
    merged: list[dict[str, Any]] = []
    skills = sorted(
        registry.all(),
        key=lambda s: (s.confidence, s.created_at),
        reverse=True,
    )
    for i, a in enumerate(skills):
        if registry.get(a.name) is None:
            continue
        for b in skills[i + 1 :]:
            if registry.get(b.name) is None:
                continue
            if a.name == b.name:
                continue
            if similarity(a, b) >= SIMILARITY_MERGE:
                survivor, absorbed = (a, b) if a.created_at >= b.created_at else (b, a)
                absorbed.state = SkillState.SUPERSEDED
                absorbed.record("superseded", f"merged into {survivor.name}")
                registry.merge_into(
                    survivor.name, absorbed, "consolidate duplicate skills"
                )
                registry.log_event("consolidated", f"{absorbed.name} -> {survivor.name}")
                merged.append(
                    {"absorbed": absorbed.name, "survivor": survivor.name}
                )
    if merged:
        registry.save()
    return merged


def revise(
    skill: Skill,
    changes: dict[str, Any],
    actor: str,
) -> Skill:
    """Apply an explicit revision (version bump with provenance)."""
    text_fields = ("description", "purpose", "expected_output")
    list_fields = ("triggers", "inputs", "procedure", "constraints", "examples")
    applied: list[str] = []
    for key in text_fields:
        if key in changes and isinstance(changes[key], str):
            setattr(skill, key, changes[key][:4000])
            applied.append(key)
    for key in list_fields:
        if key in changes and isinstance(changes[key], list):
            setattr(skill, key, [str(v)[:400] for v in changes[key]][:40])
            applied.append(key)
    if applied:
        skill.bump_version("revised", f"updated: {', '.join(applied)}", actor=actor)
        skill.record("revised", f"revised by {actor}", actor=actor)
    return skill
