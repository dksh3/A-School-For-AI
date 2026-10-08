"""1A-2Z: skill registry persistence, similarity, and merge versioning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.skillgen.registry import (
    REGISTRY_FILE,
    SIMILARITY_MERGE,
    SkillRegistry,
    similarity,
)
from core.skillgen.types import Skill, SkillState


def _skill(
    name: str = "diagnose-build-failures",
    description: str = "Diagnose and fix flaky tests that fail intermittently",
    purpose: str = "Reusable build diagnosis",
    **kw,
) -> Skill:
    kw.setdefault("state", SkillState.ACTIVE)
    return Skill(name=name, description=description, purpose=purpose, **kw)


class TestPersistence:
    def test_restart_recovers_skills(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        skill = _skill(triggers=["build failure"], confidence=0.7)
        skill.success_count = 3
        reg.add(skill)
        reg.save()

        reloaded = SkillRegistry(tmp_path)  # fresh load == restart
        found = reloaded.get(skill.name)
        assert found is not None
        assert found.confidence == 0.7
        assert found.success_count == 3
        assert found.state == SkillState.ACTIVE
        assert found.triggers == ["build failure"]

    def test_saved_file_is_valid_json_document(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(_skill())
        reg.log_event("created", "test event")
        reg.save()

        data = json.loads((tmp_path / REGISTRY_FILE).read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert len(data["skills"]) == 1
        assert data["stats"]["events"][-1]["event"] == "created"

    def test_stats_persist_across_restart(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.stats["model_calls_total"] = 4
        reg.stats["model_calls_by_task"] = {"t1": 2}
        reg.log_event("created", "e")
        reg.save()

        reloaded = SkillRegistry(tmp_path)
        assert reloaded.stats["model_calls_total"] == 4
        assert reloaded.stats["model_calls_by_task"] == {"t1": 2}
        assert reloaded.stats["events"]

    def test_save_is_atomic_no_temp_leftovers(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(_skill())
        reg.save()
        leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
        assert leftovers == []
        assert (tmp_path / REGISTRY_FILE).exists()

    def test_corrupt_file_is_tolerated(self, tmp_path: Path) -> None:
        (tmp_path / REGISTRY_FILE).write_text("{not json", encoding="utf-8")
        reg = SkillRegistry(tmp_path)  # must not raise
        assert reg.count() == 0

    def test_duplicate_add_rejected(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        ok, _msg = reg.add(_skill())
        assert ok is True
        ok, msg = reg.add(_skill())
        assert ok is False
        assert "already exists" in msg


class TestSimilarity:
    def test_identical_names_are_duplicates(self) -> None:
        a = _skill()
        b = _skill(description="Totally different text")
        assert similarity(a, b) == 1.0

    def test_disjoint_skills_score_zero(self) -> None:
        a = _skill(name="zebra-antelope", description="quantum entanglement report")
        b = _skill(name="koala-panda", description="watering tropical plants")
        assert similarity(a, b) == 0.0

    def test_near_duplicates_exceed_merge_threshold(self) -> None:
        desc = "Diagnose and fix flaky tests that fail intermittently in suites"
        a = _skill(name="fix-flaky-tests", description=desc, triggers=[])
        b = _skill(name="fix-flaky-tests-v2", description=desc, triggers=[])
        assert similarity(a, b) >= SIMILARITY_MERGE

    def test_find_similar_and_best_match(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        desc = "Diagnose and fix flaky tests that fail intermittently in suites"
        reg.add(_skill(name="fix-flaky-tests", description=desc, triggers=[]))
        probe = _skill(name="fix-flaky-tests-v2", description=desc, triggers=[])
        similar = reg.find_similar(probe)
        assert similar and similar[0][0] == "fix-flaky-tests"
        best = reg.best_match(probe)
        assert best is not None
        assert best[0] == "fix-flaky-tests"
        assert best[1] >= SIMILARITY_MERGE


class TestMergeVersioning:
    def test_merge_into_absorbs_and_bumps_version(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        target = _skill(
            name="fix-flaky-tests",
            created_from=["exp1"],
            triggers=["flaky tests"],
            success_count=2,
            failure_count=1,
        )
        source = _skill(
            name="fix-flaky-tests-v2",
            description="Much longer description absorbed from the source skill",
            created_from=["exp2", "exp3"],
            triggers=["quarantine reruns"],
            success_count=4,
            failure_count=0,
            confidence=0.9,
        )
        reg.add(target)
        reg.add(source)

        merged = reg.merge_into(target.name, source, "test merge")
        assert merged.version == 2
        assert merged.success_count == 6
        assert merged.failure_count == 1
        assert "exp2" in merged.created_from and "exp1" in merged.created_from
        assert merged.description == source.description  # longer wins
        assert "quarantine reruns" in merged.triggers
        assert reg.get(source.name) is None  # source popped
        assert reg.count() == 1
        assert merged.provenance["merged_from"][0]["name"] == source.name

    def test_count_by_state(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(_skill(name="active-skill", state=SkillState.ACTIVE))
        reg.add(_skill(name="candidate-skill", state=SkillState.CANDIDATE))
        assert reg.count() == 2
        assert reg.count(SkillState.ACTIVE) == 1
        assert reg.count(SkillState.CANDIDATE) == 1
        assert reg.count(SkillState.ARCHIVED) == 0


class TestRegistryForCache:
    def test_relative_worktree_not_cached_across_directories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.skillgen.registry import registry_for

        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        monkeypatch.chdir(tmp_path / "alpha")
        reg_alpha = registry_for(".")
        monkeypatch.chdir(tmp_path / "beta")
        reg_beta = registry_for(".")
        assert reg_alpha is not reg_beta
        assert Path(reg_alpha.path).is_absolute()
        assert Path(reg_alpha.path).is_relative_to(tmp_path / "alpha")
        assert Path(reg_beta.path).is_relative_to(tmp_path / "beta")
