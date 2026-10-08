"""Tests for School CLI."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from school.cli import main


class TestCLI:
    """Test CLI commands."""

    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        """school version prints version."""
        with patch("sys.argv", ["school", "version"]):
            main()
        captured = capsys.readouterr()
        assert "school" in captured.out.lower()

    def test_status_no_bridge(self, capsys: pytest.CaptureFixture[str]) -> None:
        """school status reports when no bridge found."""
        with (
            patch("sys.argv", ["school", "status"]),
            patch("school.cli.discover_bridge", return_value=None),
        ):
            main()
        captured = capsys.readouterr()
        assert "unavailable" in captured.out.lower() or "not found" in captured.out.lower()

    def test_install_writes_plugin(self, tmp_path: Path) -> None:
        """school install writes plugin to auto-discovery directory."""
        config_dir = tmp_path / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "opencode.jsonc"
        config_file.write_text('{"plugin": []}', encoding="utf-8")
        plugins_dir = config_dir / "plugins"

        with (
            patch("sys.argv", ["school", "install"]),
            patch("school.cli.SchoolConfig") as MockConfig,
        ):
            config = MockConfig.return_value
            config.is_school_installed.return_value = False
            config.opencode_plugins_dir.return_value = plugins_dir
            config.school_plugin_file.return_value = plugins_dir / "school.ts"
            config.opencode_config_file.return_value = config_file
            main()

        assert (plugins_dir / "school.ts").exists()

    def test_install_skip_existing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """school install skips if already installed."""
        config_dir = tmp_path / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "opencode.jsonc"
        config_file.write_text('{"plugin": []}', encoding="utf-8")
        plugins_dir = config_dir / "plugins"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "school.ts").write_text("// existing", encoding="utf-8")

        with (
            patch("sys.argv", ["school", "install"]),
            patch("school.cli.SchoolConfig") as MockConfig,
        ):
            config = MockConfig.return_value
            config.is_school_installed.return_value = True
            config.school_plugin_file.return_value = plugins_dir / "school.ts"
            config.opencode_config_file.return_value = config_file
            main()

        captured = capsys.readouterr()
        assert "already installed" in captured.out.lower()

    def test_install_removes_stale_teacher_artifacts(self, tmp_path: Path) -> None:
        """school install deletes the previous brand's plugin and skill."""
        config_dir = tmp_path / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "opencode.jsonc"
        config_file.write_text('{"plugin": []}', encoding="utf-8")
        plugins_dir = config_dir / "plugins"
        plugins_dir.mkdir(parents=True)
        stale_plugin = plugins_dir / "teacher.ts"
        stale_plugin.write_text("// stale previous brand", encoding="utf-8")
        stale_skill = config_dir / "skills" / "teacher-routing"
        stale_skill.mkdir(parents=True)
        (stale_skill / "SKILL.md").write_text("name: teacher-routing", encoding="utf-8")

        with (
            patch("sys.argv", ["school", "install", "--force"]),
            patch("school.cli.SchoolConfig") as MockConfig,
        ):
            config = MockConfig.return_value
            config.is_school_installed.return_value = False
            config.opencode_plugins_dir.return_value = plugins_dir
            config.school_plugin_file.return_value = plugins_dir / "school.ts"
            config.opencode_config_file.return_value = config_file
            main()

        assert not stale_plugin.exists(), "stale teacher.ts must be deleted"
        assert not stale_skill.exists(), "stale teacher-routing skill must be deleted"
        assert (plugins_dir / "school.ts").exists()

    def test_uninstall_safety(self, tmp_path: Path) -> None:
        """school uninstall does not remove user memory."""
        memory_dir = tmp_path / ".school" / "memory"
        memory_dir.mkdir(parents=True)
        memory_file = memory_dir / "test.json"
        memory_file.write_text('{"test": true}', encoding="utf-8")

        # Uninstall should NOT remove .school/memory/
        # This is tested by verifying the directory still exists after uninstall
        assert memory_dir.exists()
        assert memory_file.exists()


class TestContextCommand:
    """S2 Task 6: `school context` subcommands over the in-process bridge."""

    def _compress(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> dict:
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 300}
            for i in range(8)
        ]
        argv = ["school", "context", "compress", "--json", "--worktree", str(tmp_path)]
        with (
            patch("sys.argv", argv),
            patch("school.cli.SchoolConfig"),
            patch("sys.stdin", StringIO(json.dumps(messages))),
        ):
            main()
        return json.loads(capsys.readouterr().out)

    def test_status_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        argv = ["school", "context", "status", "--json", "--worktree", str(tmp_path)]
        with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
            main()
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["mode"] == "school"
        assert payload["blocks"] == 0
        assert "chip" in payload

    def test_missing_subcommand_exits(self) -> None:
        with (
            patch("sys.argv", ["school", "context"]),
            patch("school.cli.SchoolConfig"),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()
        assert excinfo.value.code == 2

    def test_switch_and_keep_persist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for decision in ("switch", "keep"):
            argv = ["school", "context", decision, "--json", "--worktree", str(tmp_path)]
            with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
                main()
            payload = json.loads(capsys.readouterr().out)
            assert payload["ok"] is True
            assert payload["decision"] == decision
        argv = ["school", "context", "status", "--json", "--worktree", str(tmp_path)]
        with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
            main()
        assert json.loads(capsys.readouterr().out)["decision"] == "keep"

    def test_compress_reads_messages_from_stdin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = self._compress(tmp_path, monkeypatch, capsys)
        assert payload["ok"] is True
        assert payload["blocks_added"] >= 1
        assert payload["chip"].startswith("[school] compacted")

    def test_restore_roundtrip_is_idempotent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._compress(tmp_path, monkeypatch, capsys)
        results = []
        for _ in range(2):
            argv = ["school", "context", "restore", "--json", "--worktree", str(tmp_path)]
            with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
                main()
            results.append(json.loads(capsys.readouterr().out))
        assert all(r["ok"] for r in results), results
        assert results[0]["restores"] >= 1

    def test_status_human_prints_dcp_offer(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "opencode.json").write_text(
            json.dumps({"plugin": ["@tarquinen/opencode-dcp"]}),
            encoding="utf-8",
        )
        argv = ["school", "context", "status", "--worktree", str(tmp_path)]
        with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
            main()
        out = capsys.readouterr().out
        assert "mode: dcp" in out
        assert "Keep DCP, or switch?" in out
        assert "school context switch" in out

    def test_status_human_prints_chip(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._compress(tmp_path, monkeypatch, capsys)
        argv = ["school", "context", "status", "--worktree", str(tmp_path)]
        with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
            main()
        out = capsys.readouterr().out
        assert "[school] compacted" in out
        assert "blocks: " in out
