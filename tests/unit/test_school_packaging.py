"""Tests for School packaging and distribution."""

from __future__ import annotations

import tomllib
from pathlib import Path


class TestPyprojectToml:
    """Test pyproject.toml configuration."""

    def test_package_name(self) -> None:
        """Package name is school."""
        with open("pyproject.toml", "rb") as f:
            config = tomllib.load(f)
        assert config["project"]["name"] == "school"

    def test_version(self) -> None:
        """Version is 2.6.0."""
        with open("pyproject.toml", "rb") as f:
            config = tomllib.load(f)
        assert config["project"]["version"] == "2.6.0"

    def test_cli_entry_point(self) -> None:
        """CLI entry point is defined."""
        with open("pyproject.toml", "rb") as f:
            config = tomllib.load(f)
        assert "school" in config["project"]["scripts"]
        assert config["project"]["scripts"]["school"] == "school.cli:main"

    def test_python_requires(self) -> None:
        """Requires Python 3.11+."""
        with open("pyproject.toml", "rb") as f:
            config = tomllib.load(f)
        assert ">=3.11" in config["project"]["requires-python"]

    def test_wheel_includes_core(self) -> None:
        """Wheel package includes core/ for bridge."""
        with open("pyproject.toml", "rb") as f:
            config = tomllib.load(f)
        packages = config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
        assert "core" in packages
        assert "school" in packages

    def test_license(self) -> None:
        """Package is MIT licensed."""
        with open("pyproject.toml", "rb") as f:
            config = tomllib.load(f)
        assert config["project"]["license"] == "MIT"

    def test_description(self) -> None:
        """Package has a description."""
        with open("pyproject.toml", "rb") as f:
            config = tomllib.load(f)
        assert len(config["project"]["description"]) > 0


class TestPackageInit:
    """Test school package initialization."""

    def test_version_importable(self) -> None:
        """Version is importable from school."""
        from school import __version__
        assert __version__ == "2.6.0"

    def test_version_all(self) -> None:
        """__all__ includes __version__."""
        from school import __all__
        assert "__version__" in __all__


class TestChocolateyPackage:
    """Test Chocolatey package configuration."""

    def test_nuspec_exists(self) -> None:
        """nuspec file exists."""
        assert Path("packaging/chocolatey/school.nuspec").exists()

    def test_nuspec_package_id(self) -> None:
        """nuspec package ID is school."""
        import xml.etree.ElementTree as ET
        tree = ET.parse("packaging/chocolatey/school.nuspec")
        ns = {"ns": "http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd"}
        pkg_id = tree.find(".//ns:id", ns)
        assert pkg_id is not None
        assert pkg_id.text == "school"

    def test_nuspec_version(self) -> None:
        """nuspec version matches."""
        import xml.etree.ElementTree as ET
        tree = ET.parse("packaging/chocolatey/school.nuspec")
        ns = {"ns": "http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd"}
        version = tree.find(".//ns:version", ns)
        assert version is not None
        assert version.text == "2.6.0"

    def test_install_script_exists(self) -> None:
        """Install script exists."""
        assert Path("packaging/chocolatey/tools/chocolateyinstall.ps1").exists()

    def test_uninstall_script_exists(self) -> None:
        """Uninstall script exists."""
        assert Path("packaging/chocolatey/tools/chocolateyuninstall.ps1").exists()

    def test_install_script_no_empty_url(self) -> None:
        """Install script does not have empty URL."""
        content = Path("packaging/chocolatey/tools/chocolateyinstall.ps1").read_text()
        assert "$url = ''" not in content


class TestHomebrewFormula:
    """Test Homebrew formula."""

    def test_formula_exists(self) -> None:
        """Formula file exists."""
        assert Path("packaging/homebrew/school.rb").exists()

    def test_formula_has_sha256(self) -> None:
        """Formula does not have PLACEHOLDER_SHA256."""
        content = Path("packaging/homebrew/school.rb").read_text()
        assert "PLACEHOLDER_SHA256" not in content

    def test_formula_class_name(self) -> None:
        """Formula class is School."""
        content = Path("packaging/homebrew/school.rb").read_text()
        assert "class School < Formula" in content


class TestNSISInstaller:
    """Test Windows NSIS installer."""

    def test_installer_exists(self) -> None:
        """Installer script exists."""
        assert Path("packaging/windows/school-installer.nsi").exists()

    def test_installer_name(self) -> None:
        """Installer name is School."""
        content = Path("packaging/windows/school-installer.nsi").read_text()
        assert 'Name "School"' in content

    def test_installer_adds_to_path(self) -> None:
        """Installer adds school to PATH for standalone exe."""
        content = Path("packaging/windows/school-installer.nsi").read_text()
        assert "EnVar::AddValue" in content


class TestLinuxInstaller:
    """Test Linux installation script."""

    def test_installer_exists(self) -> None:
        """Installer script exists."""
        assert Path("packaging/linux/install.sh").exists()

    def test_installer_uses_posix_sh(self) -> None:
        """Installer uses POSIX sh, not bash."""
        content = Path("packaging/linux/install.sh").read_text()
        assert content.startswith("#!/bin/sh")

    def test_installer_no_bashisms(self) -> None:
        """Installer does not use bash-specific syntax."""
        content = Path("packaging/linux/install.sh").read_text()
        assert "[[ " not in content  # Bash-specific double bracket

    def test_installer_is_idempotent(self) -> None:
        """Installer is idempotent (uses pip install, not pip install --force)."""
        content = Path("packaging/linux/install.sh").read_text()
        assert "pip3 install --user school" in content
