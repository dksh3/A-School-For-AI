"""Comprehensive tests for School bridge discovery."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from school.discovery import BridgeDiscovery, _find_python, discover_bridge


class TestFindPython:
    """Test Python interpreter discovery."""

    def test_find_python_returns_string(self) -> None:
        """_find_python returns a string or None."""
        result = _find_python()
        assert result is None or isinstance(result, str)

    def test_find_python_prefers_python3(self) -> None:
        """_find_python prefers python3 over python."""
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda cmd: "/usr/bin/python3" if cmd == "python3" else None
            result = _find_python()
            assert result == "python3"

    def test_find_python_falls_back_to_python(self) -> None:
        """_find_python falls back to python."""
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda cmd: "/usr/bin/python" if cmd == "python" else None
            result = _find_python()
            assert result == "python"

    def test_find_python_returns_none_when_no_python(self) -> None:
        """_find_python returns None when no Python found."""
        with patch("shutil.which", return_value=None):
            result = _find_python()
            assert result is None


class TestBridgeDiscoveryCascade:
    """Test the full bridge discovery cascade."""

    def test_tier1_school_home(self, tmp_path: Path) -> None:
        """Tier 1: SCHOOL_HOME env var."""
        bridge_dir = tmp_path / "school"
        bridge_dir.mkdir()
        bridge_file = bridge_dir / "bridge.py"
        bridge_file.write_text("# bridge", encoding="utf-8")

        with patch.dict(os.environ, {"SCHOOL_HOME": str(tmp_path)}):
            result = discover_bridge(str(tmp_path))

        assert result is not None
        assert result.tier == "SCHOOL_HOME"
        assert result.bridge_path == str(bridge_file)

    def test_tier1_legacy_home_envs_not_honoured(self, tmp_path: Path) -> None:
        """LEREV_HOME / EVO_HOME are no longer honoured (no compat fallbacks)."""
        home = tmp_path / "legacy_home"
        (home / "school").mkdir(parents=True)
        (home / "school" / "bridge.py").write_text("", encoding="utf-8")

        with patch.dict(os.environ, {"LEREV_HOME": str(home), "EVO_HOME": str(home)}, clear=True):
            result = discover_bridge(str(tmp_path))

        assert result is None or not result.bridge_path.startswith(str(home))

    def test_tier2_path_bridge(self, tmp_path: Path) -> None:
        """Tier 2: school-bridge on PATH."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which") as mock_which,
        ):
            mock_which.side_effect = (
                lambda cmd: "/usr/bin/school-bridge" if cmd == "school-bridge" else None
            )
            result = discover_bridge(str(tmp_path))

        assert result is not None
        assert result.tier == "PATH"
        assert result.bridge_path == "/usr/bin/school-bridge"

    def test_tier3_installed_module(self, tmp_path: Path) -> None:
        """Tier 3: python -m school.bridge."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which") as mock_which,
            patch("importlib.util.find_spec") as mock_find,
        ):
            mock_which.side_effect = lambda cmd: "/usr/bin/python3" if cmd == "python3" else None
            mock_find.return_value = type("Spec", (), {"origin": "/some/path/school/bridge.py"})()
            result = discover_bridge(str(tmp_path))

        assert result is not None
        assert result.tier == "installed_module"

    def test_tier4_dev_fallback(self, tmp_path: Path) -> None:
        """Tier 4: Development fallback."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        bridge_file = scripts_dir / "school_bridge.py"
        bridge_file.write_text("# bridge", encoding="utf-8")

        with patch.dict(os.environ, {}, clear=True):
            result = discover_bridge(str(tmp_path))

        assert result is not None
        assert result.tier == "dev_fallback"
        assert result.bridge_path == str(bridge_file)

    def test_no_bridge_found(self, tmp_path: Path) -> None:
        """Returns None when no bridge is found."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with patch.dict(os.environ, {}, clear=True):
            result = discover_bridge(str(empty_dir))
        assert result is None


class TestBridgeDiscoveryDataclass:
    """Test BridgeDiscovery dataclass."""

    def test_fields(self) -> None:
        """BridgeDiscovery has correct fields."""
        d = BridgeDiscovery(python="python3", bridge_path="/path/bridge.py", tier="test")
        assert d.python == "python3"
        assert d.bridge_path == "/path/bridge.py"
        assert d.tier == "test"

    def test_frozen(self) -> None:
        """BridgeDiscovery is frozen (immutable)."""
        d = BridgeDiscovery(python="python3", bridge_path="/path", tier="test")
        with pytest.raises(AttributeError):
            d.tier = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """BridgeDiscovery supports equality."""
        d1 = BridgeDiscovery(python="python3", bridge_path="/path", tier="test")
        d2 = BridgeDiscovery(python="python3", bridge_path="/path", tier="test")
        assert d1 == d2

    def test_inequality(self) -> None:
        """BridgeDiscovery supports inequality."""
        d1 = BridgeDiscovery(python="python3", bridge_path="/path", tier="test1")
        d2 = BridgeDiscovery(python="python3", bridge_path="/path", tier="test2")
        assert d1 != d2


class TestCrossPlatform:
    """Test cross-platform behavior."""

    def test_windows_python_discovery(self) -> None:
        """On Windows, python is found."""
        with (
            patch("sys.platform", "win32"),
            patch("shutil.which") as mock_which,
        ):
            mock_which.side_effect = (
                lambda cmd: "/Python314/python.exe" if cmd == "python" else None
            )
            result = _find_python()
            assert result == "python"

    def test_unix_python3_discovery(self) -> None:
        """On Unix, python3 is found."""
        with (
            patch("sys.platform", "linux"),
            patch("shutil.which") as mock_which,
        ):
            mock_which.side_effect = lambda cmd: "/usr/bin/python3" if cmd == "python3" else None
            result = _find_python()
            assert result == "python3"
