"""CLI `skills` subcommands: local list/search (offline) + fail-closed exits.

No network: these paths only touch the local registry under the cwd.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.skillgen.registry import registry_for
from core.skillgen.types import Skill, SkillScope, SkillState
from school.cli import main


def _seed(worktree: Path) -> Skill:
    registry = registry_for(str(worktree))
    skill = Skill(
        name="agent-markdown-skill",
        description="Agent markdown capability for tidy tables",
        purpose="Prove the local CLI search works",
        triggers=["markdown", "tables"],
        procedure=["Format the table"],
        state=SkillState.ACTIVE,
        scope=SkillScope.AGENT,
        agent_id="opencode",
    )
    registry.add(skill)
    registry.save()
    return skill


class TestSkillsList:
    def test_list_prints_seeded_skills(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _seed(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["school", "skills", "list"])
        main()
        report = json.loads(capsys.readouterr().out)
        assert report["ok"] is True
        assert report["count"] == 1
        assert report["skills"][0]["name"] == "agent-markdown-skill"
        assert report["skills"][0]["state"] == "active"
        assert report["skills"][0]["source"] == "local"

    def test_list_on_empty_registry_is_ok_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["school", "skills", "list"])
        main()
        report = json.loads(capsys.readouterr().out)
        assert report["ok"] is True
        assert report["count"] == 0
        assert report["skills"] == []


class TestSkillsSearch:
    def test_search_returns_scope_visible_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _seed(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["school", "skills", "search", "markdown tables"])
        main()
        report = json.loads(capsys.readouterr().out)
        assert report["ok"] is True
        assert [m["name"] for m in report["matches"]] == ["agent-markdown-skill"]
        assert report["matches"][0]["score"] > 0.0

    def test_search_miss_returns_empty_matches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _seed(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["school", "skills", "search", "quantum rocketry"])
        main()
        report = json.loads(capsys.readouterr().out)
        assert report["ok"] is True
        assert report["matches"] == []


class TestSkillsFailClosed:
    def test_missing_action_exits_nonzero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["school", "skills"])
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1
        assert "choose list, search, github-search" in capsys.readouterr().err

    def test_unknown_action_rejected_by_argparse(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["school", "skills", "frobnicate"])
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 2
        assert "invalid choice" in capsys.readouterr().err
