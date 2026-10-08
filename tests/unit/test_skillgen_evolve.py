"""1A-2Z: confidence evolution, lifecycle transitions, consolidation."""

from __future__ import annotations

from pathlib import Path

from core.skillgen.evolve import (
    apply_feedback,
    consolidate,
    evaluate_lifecycle,
    next_confidence,
    revise,
)
from core.skillgen.registry import SkillRegistry
from core.skillgen.types import Skill, SkillScope, SkillState


def _skill(
    name: str = "diagnose-build-failures",
    state: SkillState = SkillState.ACTIVE,
    confidence: float = 0.7,
    created_at: float = 100.0,
    **kw,
) -> Skill:
    kw.setdefault(
        "description",
        "Diagnose and fix flaky tests that fail intermittently in suites",
    )
    return Skill(
        name=name,
        purpose="Reusable diagnosis procedure",
        triggers=["flaky tests", "intermittent failures"],
        state=state,
        confidence=confidence,
        created_at=created_at,
        scope=SkillScope.AGENT,
        **kw,
    )


class TestConfidenceEvolution:
    def test_success_lifts_confidence_monotonically(self) -> None:
        skill = _skill(confidence=0.7, state=SkillState.ACTIVE)
        seen = [skill.confidence]
        for _ in range(5):
            apply_feedback(skill, success=True)
            seen.append(skill.confidence)
        assert all(b >= a for a, b in zip(seen, seen[1:], strict=False))
        assert seen[-1] > 0.7

    def test_reaches_proven_at_five_successes(self) -> None:
        skill = _skill(confidence=0.7, state=SkillState.ACTIVE)
        for _ in range(5):
            apply_feedback(skill, success=True)
        assert skill.state == SkillState.PROVEN
        assert skill.success_count == 5
        assert skill.confidence >= 0.7
        assert skill.failure_count == 0

    def test_success_never_lowers_confidence(self) -> None:
        skill = _skill(confidence=0.95, state=SkillState.PROVEN)
        for _ in range(3):
            before = skill.confidence
            apply_feedback(skill, success=True)
            assert skill.confidence >= before

    def test_failure_penalizes_confidence(self) -> None:
        skill = _skill(confidence=0.8, state=SkillState.ACTIVE)
        apply_feedback(skill, success=False)
        assert skill.confidence < 0.8

    def test_three_failures_demote_active_to_candidate(self) -> None:
        skill = _skill(confidence=0.9, state=SkillState.ACTIVE)
        for _ in range(3):
            apply_feedback(skill, success=False)
        assert skill.state == SkillState.CANDIDATE
        assert skill.confidence <= 0.4
        assert skill.failure_count == 3

    def test_candidate_state_is_stable_under_feedback(self) -> None:
        skill = _skill(confidence=0.5, state=SkillState.CANDIDATE)
        for _ in range(5):
            apply_feedback(skill, success=True)
        assert skill.state == SkillState.CANDIDATE  # promotion is pipeline-only

    def test_next_confidence_bounds(self) -> None:
        skill = _skill(confidence=0.5, state=SkillState.ACTIVE)
        assert 0.0 <= next_confidence(skill, success=True) <= 1.0
        assert 0.0 <= next_confidence(skill, success=False) >= 0.05


class TestLifecycle:
    def test_archive_when_failures_dominate(self) -> None:
        skill = _skill(state=SkillState.ACTIVE, confidence=0.6)
        skill.success_count = 1
        skill.failure_count = 5
        assert evaluate_lifecycle(skill) == SkillState.ARCHIVED

    def test_archive_requires_failure_ratio(self) -> None:
        skill = _skill(state=SkillState.ACTIVE, confidence=0.6)
        skill.success_count = 10
        skill.failure_count = 5  # 5/15 = 0.33 < 0.6
        # not archived; the >=3-failure demotion applies instead
        assert evaluate_lifecycle(skill) == SkillState.CANDIDATE
        assert skill.state != SkillState.ARCHIVED

    def test_archived_is_sticky(self) -> None:
        skill = _skill(state=SkillState.ARCHIVED)
        skill.failure_count = 10
        assert evaluate_lifecycle(skill) == SkillState.ARCHIVED

    def test_superseded_is_sticky(self) -> None:
        skill = _skill(state=SkillState.SUPERSEDED)
        skill.success_count = 10
        assert evaluate_lifecycle(skill) == SkillState.SUPERSEDED

    def test_validating_is_not_promoted_by_feedback(self) -> None:
        skill = _skill(state=SkillState.VALIDATING, confidence=0.5)
        skill.success_count = 10
        assert evaluate_lifecycle(skill) == SkillState.VALIDATING

    def test_proven_needs_confidence_floor(self) -> None:
        skill = _skill(state=SkillState.ACTIVE, confidence=0.5)
        skill.success_count = 5
        assert evaluate_lifecycle(skill) == SkillState.ACTIVE  # conf < 0.7


class TestConsolidation:
    def _pair(self, reg: SkillRegistry) -> tuple[str, str]:
        older = _skill(
            name="fix-flaky-tests",
            confidence=0.5,
            created_at=100.0,
            success_count=2,
        )
        newer = _skill(
            name="fix-flaky-tests-v2",
            confidence=0.9,
            created_at=200.0,
            success_count=6,
        )
        reg.add(older)
        reg.add(newer)
        return older.name, newer.name

    def test_consolidate_supersedes_and_merges(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        older, newer = self._pair(reg)
        merged = consolidate(reg)
        assert merged == [{"absorbed": older, "survivor": newer}]
        survivor = reg.get(newer)
        assert survivor is not None
        assert survivor.success_count == 8  # 6 + 2 absorbed
        assert survivor.version == 2
        assert reg.get(older) is None
        assert reg.count() == 1

    def test_consolidate_noop_without_duplicates(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(_skill(name="alpha-unique", description="whale migration patterns"))
        reg.add(_skill(name="beta-other", description="carburetor tuning guide"))
        assert consolidate(reg) == []


class TestRevision:
    def test_revise_bumps_version_and_applies_fields(self) -> None:
        skill = _skill()
        assert skill.version == 1
        skill = revise(
            skill,
            {"description": "Updated description", "triggers": ["new trigger"]},
            actor="tester",
        )
        assert skill.version == 2
        assert skill.description == "Updated description"
        assert skill.triggers == ["new trigger"]
        assert skill.history[-1].event == "revised"

    def test_revise_with_unknown_fields_is_noop(self) -> None:
        skill = _skill()
        skill = revise(skill, {"nope": 1}, actor="tester")
        assert skill.version == 1
