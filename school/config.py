"""School configuration — paths and OpenCode config discovery."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


class SchoolConfig:
    """School configuration and path management."""

    package_name: str = "school"
    plugin_dir_name: str = "school"
    memory_dir: str = ".school"
    legacy_memory_dir: str = ".evo"
    # Legacy identity — pre-rename installs used .lerev/ (and .evo/ before that).
    legacy_memory_dirs: tuple[str, ...] = (".lerev", ".evo")
    legacy_plugin_file_name: str = "lerev.ts"
    legacy_plugin_dir_name: str = "lerev"

    def __init__(self) -> None:
        self._home = Path.home()

    def opencode_config_dir(self) -> Path:
        """Return the OpenCode global config directory."""
        return self._home / ".config" / "opencode"

    def opencode_config_file(self) -> Path:
        """Return the OpenCode global config file path."""
        return self.opencode_config_dir() / "opencode.jsonc"

    def opencode_plugins_dir(self) -> Path:
        """Return the OpenCode auto-discovery plugins directory."""
        return self.opencode_config_dir() / "plugins"

    def school_plugin_file(self) -> Path:
        """Return the path to the School TypeScript plugin file."""
        return self.opencode_plugins_dir() / f"{self.plugin_dir_name}.ts"

    # Legacy alias — pre-rename installs looked for lerev.ts.
    def lerev_plugin_file(self) -> Path:
        """Legacy alias for :meth:`school_plugin_file` (pre-rename installs)."""
        return self.opencode_plugins_dir() / self.legacy_plugin_file_name

    def legacy_plugin_dir(self) -> Path:
        """Return the stale node_modules plugin directory from older installs."""
        return self.opencode_config_dir() / "node_modules" / self.legacy_plugin_dir_name

    def read_opencode_config(self) -> dict[str, Any] | None:
        """Read the OpenCode global config file."""
        config_file = self.opencode_config_file()
        if not config_file.is_file():
            return None
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def write_opencode_config(self, config: dict[str, Any]) -> None:
        """Write the OpenCode global config file."""
        config_file = self.opencode_config_file()
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            json.dumps(config, indent=2) + "\n",
            encoding="utf-8",
        )

    def is_school_installed(self) -> bool:
        """Check if School plugin file exists in the auto-discovery directory."""
        return self.school_plugin_file().is_file()

    # Legacy alias — pre-rename installs checked lerev.ts.
    def is_lerev_installed(self) -> bool:
        """Legacy alias for :meth:`is_school_installed` (pre-rename installs)."""
        return self.lerev_plugin_file().is_file()


def get_opencode_config_path() -> Path | None:
    """Find the OpenCode global config file."""
    home = Path.home()
    candidates = [
        home / ".config" / "opencode" / "opencode.jsonc",
        home / ".config" / "opencode" / "opencode.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def get_opencode_node_modules() -> Path | None:
    """Find the OpenCode global node_modules directory."""
    nm_dir = Path.home() / ".config" / "opencode" / "node_modules"
    return nm_dir if nm_dir.is_dir() else None


# Legacy alias - pre-rename imports used LerevConfig.
LerevConfig = SchoolConfig


def resolve_memory_dir(worktree: str | Path) -> Path:
    """Return the memory directory for a worktree.

    Resolution takes the first existing of ``.school``, ``.teacher``,
    ``.lerev``, ``.evo`` (checked as ``<root>/memory``); if none exists,
    ``.school/memory`` is created. Existing roots are used in place —
    memory is never copied, moved, or deleted.
    """
    try:
        root = Path(worktree)
    except (TypeError, ValueError):
        root = Path(tempfile.mkdtemp(prefix="school-mem-"))
    try:
        for name in (".school", ".teacher", ".lerev", ".evo"):
            candidate = root / name / "memory"
            if candidate.exists():
                return candidate
        canonical = root / ".school" / "memory"
        canonical.mkdir(parents=True, exist_ok=True)
        return canonical
    except (OSError, ValueError, TypeError):
        # Hostile path (NUL bytes, traversal, invalid) -> isolated temp dir.
        return Path(tempfile.mkdtemp(prefix="school-mem-"))
