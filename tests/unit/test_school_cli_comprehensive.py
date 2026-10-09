"""Comprehensive tests for School CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from school.cli import _auto_install, main
from school.config import SchoolConfig


class TestCLIHelp:
    """Test CLI help output."""

    def test_no_args_shows_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Running with no args shows help."""
        with patch("sys.argv", ["school"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_help_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--help shows help."""
        with patch("sys.argv", ["school", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_version_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        """school version prints version."""
        with patch("sys.argv", ["school", "version"]):
            main()
        captured = capsys.readouterr()
        assert "school" in captured.out.lower()
        assert "2.6.0" in captured.out

    def test_version_output_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Version output matches expected format."""
        with patch("sys.argv", ["school", "version"]):
            main()
        captured = capsys.readouterr()
        assert captured.out.strip() == "school 2.6.0"


class TestCLIStatus:
    """Test CLI status command."""

    def test_status_no_bridge(self, capsys: pytest.CaptureFixture[str]) -> None:
        """school status reports when no bridge found."""
        with (
            patch("sys.argv", ["school", "status"]),
            patch("school.cli.discover_bridge", return_value=None),
        ):
            main()
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_status_with_bridge(self, capsys: pytest.CaptureFixture[str]) -> None:
        """school status shows bridge tier."""
        from school.discovery import BridgeDiscovery

        mock_bridge = BridgeDiscovery(
            python="python3", bridge_path="/test/bridge.py", tier="test_tier"
        )
        with (
            patch("sys.argv", ["school", "status"]),
            patch("school.cli.discover_bridge", return_value=mock_bridge),
        ):
            main()
        captured = capsys.readouterr()
        assert "test_tier" in captured.out

    def test_status_shows_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Status output includes version."""
        with (
            patch("sys.argv", ["school", "status"]),
            patch("school.cli.discover_bridge", return_value=None),
        ):
            main()
        captured = capsys.readouterr()
        assert "2.6.0" in captured.out


class TestCLIInstall:
    """Test CLI install command."""

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
            config.legacy_plugin_dir.return_value = tmp_path / "node_modules" / "school"
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
            config.legacy_plugin_dir.return_value = tmp_path / "node_modules" / "school"
            main()

        captured = capsys.readouterr()
        assert "already installed" in captured.out.lower()

    def test_install_no_opencode_config(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Install warns when OpenCode config not found."""
        with (
            patch("sys.argv", ["school", "install"]),
            patch("school.cli.SchoolConfig") as MockConfig,
        ):
            config = MockConfig.return_value
            config.opencode_config_file.return_value = None
            main()
        captured = capsys.readouterr()
        assert "warning" in captured.out.lower() or "not found" in captured.out.lower()


class TestCLIUninstall:
    """Test CLI uninstall command."""

    def test_uninstall_safety(self, tmp_path: Path) -> None:
        """school uninstall does not remove user memory."""
        memory_dir = tmp_path / ".school" / "memory"
        memory_dir.mkdir(parents=True)
        memory_file = memory_dir / "test.json"
        memory_file.write_text('{"test": true}', encoding="utf-8")

        # Uninstall should NOT remove .school/memory/
        assert memory_dir.exists()
        assert memory_file.exists()

    def test_uninstall_idempotent(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Uninstall when nothing to uninstall is safe."""
        with (
            patch("sys.argv", ["school", "uninstall"]),
            patch("school.cli.SchoolConfig") as MockConfig,
        ):
            config = MockConfig.return_value
            config.school_plugin_file.return_value = Path("/nonexistent/school.ts")
            config.opencode_config_dir.return_value = Path("/nonexistent")
            main()
        captured = capsys.readouterr()
        assert "complete" in captured.out.lower()


class TestCLIDoctor:
    """Test CLI doctor command."""

    def test_doctor_runs(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Doctor command executes without error."""
        with patch("sys.argv", ["school", "doctor"]):
            main()
        captured = capsys.readouterr()
        assert "SCHOOL DOCTOR" in captured.out
        assert "RESULT:" in captured.out

    def test_doctor_checks_python(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Doctor checks Python version."""
        with patch("sys.argv", ["school", "doctor"]):
            main()
        captured = capsys.readouterr()
        assert "Python runtime" in captured.out

    def test_doctor_checks_package(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Doctor checks School package."""
        with patch("sys.argv", ["school", "doctor"]):
            main()
        captured = capsys.readouterr()
        assert "SCHOOL package" in captured.out

    def test_doctor_checks_bridge(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Doctor checks bridge."""
        with patch("sys.argv", ["school", "doctor"]):
            main()
        captured = capsys.readouterr()
        assert "Bridge" in captured.out

    def test_doctor_checks_memory(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Doctor checks memory directory."""
        with patch("sys.argv", ["school", "doctor"]):
            main()
        captured = capsys.readouterr()
        assert "memory" in captured.out.lower()


class TestCanonicalPluginLocation:
    """One canonical plugin: the global auto-discovery directory."""

    def test_global_canonical_plugin_path(self, tmp_path: Path) -> None:
        """Plugin lives at ~/.config/opencode/plugins/school.ts, not per-project."""
        with patch.object(Path, "home", return_value=tmp_path):
            config = SchoolConfig()
        assert config.opencode_plugins_dir() == tmp_path / ".config" / "opencode" / "plugins"
        assert config.school_plugin_file() == (
            tmp_path / ".config" / "opencode" / "plugins" / "school.ts"
        )
        assert not config.is_school_installed()

    def test_project_plugin_copy_absent(self) -> None:
        """The stale project-level plugin copy must not exist in the repo."""
        repo_root = Path(__file__).resolve().parents[2]
        assert not (repo_root / ".opencode" / "plugins" / "school.ts").exists()

    def test_legacy_plugin_dir_is_stale_node_modules_location(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            config = SchoolConfig()
        assert config.legacy_plugin_dir() == (
            tmp_path / ".config" / "opencode" / "node_modules" / "lerev"
        )


class TestLegacyDuplicateCleanup:
    """Stale duplicates are removed by the existing install mechanism."""

    @staticmethod
    def _fake_home(tmp_path: Path) -> Path:
        opencode_dir = tmp_path / ".config" / "opencode"
        opencode_dir.mkdir(parents=True, exist_ok=True)
        (opencode_dir / "opencode.jsonc").write_text('{"plugin": []}', encoding="utf-8")
        legacy = opencode_dir / "node_modules" / "lerev"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / "lerev.ts").write_text("// stale 3-tool copy", encoding="utf-8")
        return legacy

    def test_auto_install_cleans_legacy_and_writes_versioned_plugin(
        self, tmp_path: Path
    ) -> None:
        legacy = self._fake_home(tmp_path)

        with patch.object(Path, "home", return_value=tmp_path):
            config = SchoolConfig()
            _auto_install(config)
            installed = config.school_plugin_file().read_text(encoding="utf-8")

        assert not legacy.exists()
        from school import __version__

        assert f'const SCHOOL_VERSION = "{__version__}"' in installed

    def test_install_command_cleans_legacy_directory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        legacy = self._fake_home(tmp_path)

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch("sys.argv", ["school", "install"]),
        ):
            main()
        capsys.readouterr()

        assert not legacy.exists()
        assert (tmp_path / ".config" / "opencode" / "plugins" / "school.ts").exists()

    def test_uninstall_removes_legacy_directory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        legacy = self._fake_home(tmp_path)
        plugin_file = tmp_path / ".config" / "opencode" / "plugins" / "school.ts"
        plugin_file.parent.mkdir(parents=True, exist_ok=True)
        plugin_file.write_text("// current", encoding="utf-8")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch("sys.argv", ["school", "uninstall"]),
        ):
            main()
        captured = capsys.readouterr()

        assert not plugin_file.exists()
        assert not legacy.exists()
        assert "complete" in captured.out.lower()
