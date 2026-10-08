"""1A-2Z: end-to-end pipeline with a MOCKED model judge.

No external model in the suite: judgment outcomes are injected so the
budget, safety, duplicate, validation, and learning-loop stages are all
exercised deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.routing.v26.experience import Experience, ExperienceOutcome
from core.routing.v26.identity import AgentIdentity
from core.skillgen.pipeline import SkillPipeline, quick_observe
from core.skillgen.registry import SkillRegistry
from core.skillgen.types import SkillState

GOOD_JUDGMENT = {
    "worth_creating": True,
    "confidence": 0.9,
    "skill_type": "diagnostic",
    "reason": "Reusable diagnosis for module resolution failures",
    "generalizable": True,
    "safety_ok": True,
    "proposed_scope": "agent",
    "proposed_name": "diagnose-module-resolution",
    "procedure_steps": [
        "Reproduce the module resolution failure",
        "Inspect the module configuration",
        "Apply the configuration fix and verify",
    ],
    "triggers": ["module resolution error", "cannot find module"],
}


class MockJudge:
    """Injectable ModelJudge: returns canned text or raises."""

    def __init__(self, raw: str | None = None, error: Exception | None = None):
        self.raw = raw if raw is not None else json.dumps(GOOD_JUDGMENT)
        self.error = error
        self.calls = 0

    def __call__(self, prompt: str) -> tuple[str, str]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.raw, "mock-model"


def strong_exp(suffix: str = "") -> Experience:
    return Experience.create(
        agent=AgentIdentity(agent_id="a1"),
        observation=(
            "The build failed every time with module resolution errors "
            f"after a config change{suffix}"
        ),
        action=(
            "Diagnosed the root cause and fixed the module configuration "
            f"so builds pass reliably{suffix}"
        ),
        outcome=ExperienceOutcome.SUCCESS,
        feedback="works, exactly what I needed, great",
    )


def weak_exp() -> Experience:
    return Experience.create(
        agent=AgentIdentity(agent_id="a1"),
        observation="Attempted an alternate approach for unrelated reasons today",
        action="Tried it and it did not apply to this particular setup",
        outcome=ExperienceOutcome.FAILURE,
    )


def trivial_exp() -> Experience:
    return Experience.create(
        agent=AgentIdentity(agent_id="a1"),
        observation="Opened a file",
        action="",
        outcome=ExperienceOutcome.SUCCESS,
    )


class TestAutomaticCreation:
    def test_create_end_to_end(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        judge = MockJudge()
        pipeline = SkillPipeline(reg, judge=judge)

        report = pipeline.observe(strong_exp(), task="t-create")

        assert report["action"] == "created"
        assert report["state"] == "active"
        assert report["scope"] == "agent"
        assert report["version"] == 1
        assert 0.3 <= report["confidence"] <= 0.7  # limited initial trust
        assert judge.calls == 1
        assert report["judgment"]["worth_creating"] is True

        skill = reg.get(report["skill"])
        assert skill is not None
        assert skill.state == SkillState.ACTIVE
        assert skill.provenance["judge"] == "mock-model"
        assert skill.created_from == [report["experience_id"]]
        assert skill.to_skill_md().startswith("---")

    def test_trivial_never_reaches_judge(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        judge = MockJudge()
        report = SkillPipeline(reg, judge=judge).observe(trivial_exp())
        assert report["action"] == "rejected:not_candidate"
        assert judge.calls == 0

    def test_below_threshold_never_reaches_judge(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        judge = MockJudge()
        report = SkillPipeline(reg, judge=judge).observe(weak_exp(), task="t-thr")
        assert report["action"] == "rejected:below_threshold"
        assert judge.calls == 0

    def test_no_judge_configured_disables_creation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCHOOL_SKILLGEN_JUDGE_CMD", raising=False)
        reg = SkillRegistry(tmp_path)
        report = SkillPipeline(reg, judge=None).observe(strong_exp(), task="t-noj")
        assert report["action"] == "rejected:no_judge_configured"

    def test_observe_twice_merges_as_duplicate(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        judge = MockJudge()
        pipeline = SkillPipeline(reg, judge=judge)
        first = pipeline.observe(strong_exp(), task="t-dup")
        second = pipeline.observe(strong_exp(suffix=" again"), task="t-dup")
        assert first["action"] == "created"
        assert second["action"] == "merged_duplicate"
        assert second["skill"] == first["skill"]
        assert reg.count() == 1
        assert judge.calls == 2


class TestModelJudgmentHandling:
    def test_judge_error_is_contained(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        judge = MockJudge(error=RuntimeError("model exploded"))
        report = SkillPipeline(reg, judge=judge).observe(strong_exp(), task="t-err")
        assert report["action"] == "rejected:judge_error"
        assert "model exploded" in report["error"]
        assert judge.calls == 1
        assert any(e["event"] == "judge_error" for e in reg.stats["events"])
        assert reg.count() == 0

    def test_not_worth_creating_rejected(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        raw = json.dumps(dict(GOOD_JUDGMENT, worth_creating=False))
        report = SkillPipeline(reg, judge=MockJudge(raw)).observe(
            strong_exp(), task="t-nw"
        )
        assert report["action"] == "rejected:model_not_worth"
        assert reg.count() == 0

    def test_unsafe_verdict_rejected(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        raw = json.dumps(dict(GOOD_JUDGMENT, safety_ok=False))
        report = SkillPipeline(reg, judge=MockJudge(raw)).observe(
            strong_exp(), task="t-unsafe"
        )
        assert report["action"] == "rejected:model_safety"
        assert reg.count() == 0

    def test_invalid_model_output_fails_closed(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        report = SkillPipeline(reg, judge=MockJudge("garbage output")).observe(
            strong_exp(), task="t-bad"
        )
        assert report["action"] == "rejected:model_not_worth"
        assert reg.count() == 0

    def test_global_scope_clamped_without_confidence(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        raw = json.dumps(dict(GOOD_JUDGMENT, proposed_scope="global",
                              generalizable=False, confidence=0.5))
        report = SkillPipeline(reg, judge=MockJudge(raw)).observe(
            strong_exp(), task="t-scope"
        )
        assert report["action"] == "created"
        assert report["scope"] == "agent"  # fallback to experience scope


class TestBudget:
    def test_budget_exhaustion_stops_model_calls(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        judge = MockJudge()
        pipeline = SkillPipeline(reg, judge=judge, max_model_calls=1)
        first = pipeline.observe(strong_exp(), task="t-budget")
        second = pipeline.observe(strong_exp(suffix=" v2"), task="t-budget")
        assert first["action"] == "created"
        assert second["action"] == "rejected:budget_exhausted"
        assert second["budget"]["max"] == 1
        assert judge.calls == 1

    def test_budget_counters_persist_in_registry(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        judge = MockJudge()
        pipeline = SkillPipeline(reg, judge=judge, max_model_calls=2)
        pipeline.observe(strong_exp(), task="t-persist")
        assert reg.stats["model_calls_total"] == 1
        reg.save()
        reloaded = SkillRegistry(tmp_path)
        assert reloaded.stats["model_calls_total"] == 1


class TestExperienceDictEntry:
    def test_bad_experience_dict_rejected(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        report = SkillPipeline(reg, judge=MockJudge()).observe_experience_dict(
            {"foo": 1}, task="t-dict"
        )
        assert report["action"].startswith("rejected:")

    def test_good_experience_dict_runs(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        report = SkillPipeline(reg, judge=MockJudge()).observe_experience_dict(
            strong_exp().to_dict(), task="t-dict2"
        )
        assert report["action"] == "created"


class TestManualCreatePath:
    def _payload(self, **kw) -> dict:
        payload = {
            "name": "quarantine-flaky-tests",
            "description": "Quarantine and stabilize flaky tests",
            "purpose": "Stop flaky tests from blocking CI",
            "triggers": ["flaky test quarantine"],
            "procedure": [
                "Identify the flaky test reliably",
                "Quarantine it and rerun the suite",
            ],
        }
        payload.update(kw)
        return payload

    def test_manual_create_is_validated_and_activated(
        self, tmp_path: Path
    ) -> None:
        reg = SkillRegistry(tmp_path)
        pipeline = SkillPipeline(reg, judge=None)
        report = pipeline.create_manual(self._payload())
        assert report["ok"] is True
        assert report["action"] == "created"
        assert report["state"] == "active"
        skill = reg.get("quarantine-flaky-tests")
        assert skill is not None
        assert skill.state == SkillState.ACTIVE
        assert skill.provenance["created_by"] == "manual"

    def test_same_name_revises_with_version_bump(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        pipeline = SkillPipeline(reg, judge=None)
        pipeline.create_manual(self._payload())
        report = pipeline.create_manual(
            self._payload(description="Updated description")
        )
        assert report["ok"] is True
        assert report["action"] == "revised"
        assert report["version"] == 2
        assert reg.count() == 1

    def test_missing_purpose_rejected(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        report = SkillPipeline(reg, judge=None).create_manual(
            self._payload(purpose="")
        )
        assert report["ok"] is False
        assert report["action"] == "rejected:validation"

    def test_missing_procedure_rejected(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        report = SkillPipeline(reg, judge=None).create_manual(
            self._payload(procedure=[])
        )
        assert report["ok"] is False
        assert report["action"] == "rejected:validation"

    def test_duplicate_manual_create_merges(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        pipeline = SkillPipeline(reg, judge=None)
        pipeline.create_manual(self._payload())
        # identical content => similarity 1.0 => merge, not second skill
        report = pipeline.create_manual(
            self._payload(description="Quarantine and stabilize flaky tests")
        )
        assert report["ok"] is True
        assert report["action"] in {"revised", "merged_duplicate"}
        assert reg.count() == 1


class TestReuseLoop:
    def _created(self, tmp_path: Path) -> tuple[SkillPipeline, str]:
        reg = SkillRegistry(tmp_path)
        pipeline = SkillPipeline(reg, judge=None)
        report = pipeline.create_manual({
            "name": "quarantine-flaky-tests",
            "description": "Quarantine and stabilize flaky tests",
            "purpose": "Stop flaky tests from blocking CI",
            "triggers": ["flaky test quarantine"],
            "procedure": ["Identify the flaky test", "Quarantine and rerun"],
        })
        return pipeline, report["skill"]

    def test_use_records_reuse_and_returns_markdown(
        self, tmp_path: Path
    ) -> None:
        pipeline, name = self._created(tmp_path)
        result = pipeline.use(name=name)
        assert result["ok"] is True
        assert f"name: {name}" in result["markdown"]
        assert result["state"] == "active"

    def test_use_by_query_returns_matches(self, tmp_path: Path) -> None:
        pipeline, _name = self._created(tmp_path)
        result = pipeline.use(query="quarantine flaky test")
        assert result["ok"] is True
        assert result["matches"]
        assert result["matches"][0]["name"] == "quarantine-flaky-tests"

    def test_use_unknown_name_fails(self, tmp_path: Path) -> None:
        pipeline, _name = self._created(tmp_path)
        result = pipeline.use(name="does-not-exist")
        assert result["ok"] is False
        assert result["reason"] == "not_found"

    def test_feedback_success_raises_confidence(self, tmp_path: Path) -> None:
        pipeline, name = self._created(tmp_path)
        before = pipeline.registry.get(name).confidence
        result = pipeline.feedback(name, success=True, note="helped")
        assert result["ok"] is True
        assert result["confidence"] > before
        assert result["success_count"] == 1

    def test_feedback_failure_lowers_confidence(self, tmp_path: Path) -> None:
        pipeline, name = self._created(tmp_path)
        before = pipeline.registry.get(name).confidence
        result = pipeline.feedback(name, success=False)
        assert result["ok"] is True
        assert result["confidence"] < before
        assert result["failure_count"] == 1

    def test_feedback_unknown_skill_fails(self, tmp_path: Path) -> None:
        pipeline, _name = self._created(tmp_path)
        result = pipeline.feedback("nope", success=True)
        assert result["ok"] is False

    def test_evolve_revise_and_recompute(self, tmp_path: Path) -> None:
        pipeline, name = self._created(tmp_path)
        revised = pipeline.evolve(
            action="revise", name=name, changes={"description": "Better text"}
        )
        assert revised["ok"] is True
        assert revised["version"] == 2
        recomputed = pipeline.evolve(action="recompute")
        assert recomputed["ok"] is True
        assert name in recomputed["states"]
        unknown = pipeline.evolve(action="explode")
        assert unknown["ok"] is False

    def test_evolve_consolidate_runs(self, tmp_path: Path) -> None:
        pipeline, _name = self._created(tmp_path)
        result = pipeline.evolve(action="consolidate")
        assert result["ok"] is True
        assert result["count"] == 0  # no near-duplicates in fixture

    def test_status_reports_registry_health(self, tmp_path: Path) -> None:
        pipeline, _name = self._created(tmp_path)
        status = pipeline.status()
        assert status["ok"] is True
        assert status["skills"] == 1
        assert status["by_state"] == {"active": 1}
        assert isinstance(status["model_calls_total"], int)
        assert isinstance(status["judge_configured"], bool)
        assert status["storage"]


class TestQuickObserve:
    def test_quick_observe_uses_worktree_registry(self, tmp_path: Path) -> None:
        report = quick_observe(
            str(tmp_path), strong_exp(), task="t-quick", judge=MockJudge()
        )
        assert report["action"] == "created"
        registry_file = tmp_path / ".school" / "memory" / "skillgen_v1.json"
        assert registry_file.exists()
