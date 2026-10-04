"""School CLI - command-line interface for School."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from school import __version__
from school.config import SchoolConfig
from school.discovery import discover_bridge
from school.plugin_source import TS_PLUGIN_SOURCE


def _cmd_version(args: argparse.Namespace) -> None:
    """Print School version."""
    print(f"school {__version__}")


def _cmd_status(args: argparse.Namespace) -> None:
    """Print School status."""
    config = SchoolConfig()
    bridge = discover_bridge(".")

    print("School")
    print("----------------")
    print(f"Version: {__version__}")

    # Plugin status
    if config.is_school_installed():
        print("Plugin: installed")
    else:
        print("Plugin: not installed")

    # OpenCode status
    config_path = config.opencode_config_file()
    if config_path and config_path.exists():
        print("OpenCode: detected")
    else:
        print("OpenCode: not found")

    # Bridge status
    if bridge:
        print(f"Bridge: healthy (tier: {bridge.tier})")
    else:
        print("Bridge: not found")

    # Memory status (canonical dir plus legacy pre-rename locations)
    memory_candidates = (
        Path(".school") / "memory",
        Path(".teacher") / "memory",
        Path(".lerev") / "memory",
        Path(".evo") / "memory",
    )
    if any(candidate.exists() for candidate in memory_candidates):
        print("Memory: available")
    else:
        print("Memory: no data")


def _clean_legacy_plugin(config: SchoolConfig, verbose: bool = True) -> bool:
    """Remove stale plugin artefacts left by pre-rename installs.

    Removes the old ``node_modules/lerev`` directory and the stale
    ``plugins/lerev.ts`` file (legacy identity) if present. Never touches
    the canonical ``plugins/school.ts``.
    """
    removed = False

    legacy_dir = config.legacy_plugin_dir()
    if legacy_dir.is_dir():
        try:
            shutil.rmtree(legacy_dir)
            removed = True
            if verbose:
                print(f"Removed stale legacy plugin directory: {legacy_dir}")
        except OSError:
            pass

    legacy_file = config.lerev_plugin_file()
    if legacy_file.is_file():
        try:
            legacy_file.unlink()
            removed = True
            if verbose:
                print(f"Removed stale legacy plugin file: {legacy_file}")
        except OSError:
            pass

    return removed


# Legacy alias (pre-rename helper name).
_clean_legacy_plugin_dir = _clean_legacy_plugin


def _clean_stale_brand(config: SchoolConfig, verbose: bool = True) -> bool:
    """Remove previous-brand artefacts so OpenCode never loads duplicates.

    Deletes ``plugins/teacher.ts`` and ``skills/teacher-routing/`` written
    by pre-rebrand installs of this product.
    """
    removed = False

    stale_plugin = config.opencode_plugins_dir() / "teacher.ts"
    if stale_plugin.is_file():
        try:
            stale_plugin.unlink()
            removed = True
            if verbose:
                print(f"Removed stale previous-brand plugin: {stale_plugin}")
        except OSError:
            pass

    stale_skill = config.opencode_plugins_dir().parent / "skills" / "teacher-routing"
    if stale_skill.is_dir():
        try:
            shutil.rmtree(stale_skill)
            removed = True
            if verbose:
                print(f"Removed stale previous-brand skill: {stale_skill}")
        except OSError:
            pass

    return removed


def _cmd_install(args: argparse.Namespace) -> None:
    """Install School globally for OpenCode."""
    config = SchoolConfig()
    force = getattr(args, "force", False)

    print("School Installer")
    print("----------------------------")

    print(f"Python: {sys.version_info.major}.{sys.version_info.minor} OK")

    # Check OpenCode config
    config_file = config.opencode_config_file()
    if config_file is None:
        print("WARNING: OpenCode config not found")
        print(f"  Expected at: {config.opencode_config_file()}")
        print("  School will work in development mode only.")
        return

    print(f"OpenCode config: {config_file}")

    # Clean up stale pre-rename plugin artefacts
    _clean_legacy_plugin(config)

    # Remove stale previous-brand artefacts (rebrand cleanup)
    _clean_stale_brand(config)

    # Check if already installed
    plugin_file = config.school_plugin_file()
    if plugin_file.exists() and not force:
        print(f"School is already installed at: {plugin_file}")
        print("Use --force to reinstall.")
        return

    # Create plugins directory (auto-discovery)
    plugins_dir = config.opencode_plugins_dir()
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Write TypeScript plugin
    plugin_file.write_text(TS_PLUGIN_SOURCE, encoding="utf-8")
    print(f"Plugin installed: {plugin_file}")

    # Write the school-routing skill alongside the plugin
    skill_file = install_skill()
    print(f"Skill installed: {skill_file}")

    # Verify bridge
    bridge = discover_bridge(".")
    if bridge:
        print(f"Bridge: {bridge.tier} OK")
    else:
        print("WARNING: Bridge not found. Run `school doctor` for diagnostics.")

    print("")
    print("Installation complete!")
    print("Restart OpenCode to use School.")


def install_skill(dest_root: str | Path | None = None) -> Path:
    """Write the school-routing skill to OpenCode's user skill directory."""
    from .skill_source import ROUTING_SKILL_MD

    root = (
        Path(dest_root)
        if dest_root
        else Path.home() / ".config" / "opencode" / "skills"
    )
    target = root / "school-routing" / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(ROUTING_SKILL_MD, encoding="utf-8")
    return target


def _cmd_doctor(args: argparse.Namespace) -> None:
    """Run School diagnostics."""
    config = SchoolConfig()
    bridge = discover_bridge(".")

    print("SCHOOL DOCTOR")
    print("=" * 40)
    print("")

    results: list[tuple[str, bool, str]] = []

    # 1. Python version
    py_ok = sys.version_info >= (3, 11)
    py_msg = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if not py_ok:
        py_msg += " (requires 3.11+)"
    results.append(("Python runtime", py_ok, py_msg))

    # 2. School package importable
    try:
        from school import __version__ as school_ver  # noqa: F401
        results.append(("SCHOOL package", True, f"v{school_ver}"))
    except Exception as exc:
        results.append(("SCHOOL package", False, str(exc)))

    # 3. V2.6 memory system
    try:
        from core.routing.v26.memory_manager import MemoryManager  # noqa: F401
        from core.routing.v26.persistence import ScopeIsolatedStorage  # noqa: F401
        from core.routing.v26.security import V26SecurityPolicy  # noqa: F401
        results.append(("V2.6 memory system", True, "available"))
    except Exception as exc:
        results.append(("V2.6 memory system", False, str(exc)))

    # 4. V2.5 routing
    try:
        from core.routing.integration import SchoolIntegrationBridge  # noqa: F401
        results.append(("V2.5 routing", True, "available"))
    except Exception as exc:
        results.append(("V2.5 routing", False, str(exc)))

    # 5. Bridge discovery
    if bridge:
        results.append(("Bridge", True, f"tier={bridge.tier}"))
    else:
        results.append(("Bridge", False, "no bridge found"))

    # 6. OpenCode config
    config_file = config.opencode_config_file()
    opencode_found = config_file is not None and config_file.exists()
    results.append(("OpenCode config", opencode_found,
                     str(config_file) if opencode_found else "not found"))

    # 7. Plugin file
    plugin_file = config.school_plugin_file()
    plugin_exists = plugin_file.exists()
    results.append(("Plugin file", plugin_exists,
                     str(plugin_file) if plugin_exists else "not found"))

    # 8. Memory directory (canonical plus legacy pre-rename locations)
    memory_candidates = (
        Path(".school") / "memory",
        Path(".teacher") / "memory",
        Path(".lerev") / "memory",
        Path(".evo") / "memory",
    )
    mem_exists = any(candidate.exists() for candidate in memory_candidates)
    results.append(("Project memory", True,
                     "exists" if mem_exists else "no data yet (will be created)"))

    # Print results
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {detail}")

    print("")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    if passed == total:
        print("RESULT: SCHOOL IS READY")
    else:
        failed = total - passed
        print(f"RESULT: {failed} issue(s) found — fix them above")
    print("")


def _cmd_uninstall(args: argparse.Namespace) -> None:
    """Uninstall School from OpenCode."""
    config = SchoolConfig()

    print("School Uninstaller")
    print("----------------------------")

    # Remove plugin file from auto-discovery directory
    plugin_file = config.school_plugin_file()
    if plugin_file.exists():
        plugin_file.unlink()
        print(f"Removed plugin: {plugin_file}")

    # Also clean up stale pre-rename artefacts
    _clean_legacy_plugin(config)

    print("")
    print("Uninstall complete.")
    print("Note: .school/memory/ was NOT removed (use explicit action to delete).")
    print("Restart OpenCode to apply changes.")


def _auto_install(config: SchoolConfig) -> None:
    """Auto-install plugin on first run (silent)."""
    plugins_dir = config.opencode_plugins_dir()
    plugins_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = config.school_plugin_file()
    plugin_file.write_text(TS_PLUGIN_SOURCE, encoding="utf-8")
    _clean_legacy_plugin(config, verbose=False)


def _cmd_mcp(args: argparse.Namespace) -> None:
    """Run the School MCP server (stdio) or print client configuration."""
    if getattr(args, "mcp_command", None) == "config":
        from school.mcp.config import build_client_config

        client = getattr(args, "client", None) or "generic"
        try:
            preset = build_client_config(client)
        except ValueError as exc:
            sys.stderr.write(f"{exc}\n")
            sys.exit(1)
        print(f"# School MCP config for {preset['name']} ({preset['format']})")
        print(f"# File: {preset['path']}")
        print(preset["config"])
        if preset.get("cli"):
            print(f"# CLI alternative: {preset['cli']}")
        return

    try:
        from school.mcp.server import main as mcp_main
    except ImportError as exc:
        sys.stderr.write(
            "School MCP server requires the optional 'mcp' package.\n"
            "Install it with: pip install 'school[mcp]'\n"
            f"(import failed: {exc})\n"
        )
        sys.exit(1)
    mcp_main()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="school",
        description="School - Universal agent learning and memory system",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("version", help="Print School version")
    subparsers.add_parser("status", help="Show School status")
    install_parser = subparsers.add_parser("install", help="Install School globally for OpenCode")
    install_parser.add_argument(
        "--force", action="store_true", help="Force reinstall even if already installed"
    )
    subparsers.add_parser("doctor", help="Run School diagnostics")
    subparsers.add_parser("uninstall", help="Uninstall School from OpenCode")
    mcp_parser = subparsers.add_parser(
        "mcp", help="Run the School MCP server over stdio, or print client config"
    )
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_config_parser = mcp_subparsers.add_parser(
        "config", help="Print copy-paste MCP client configuration"
    )
    mcp_config_parser.add_argument(
        "client",
        nargs="?",
        default="generic",
        help="MCP client preset (claude, codex, opencode, cursor, ...)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Auto-install plugin on first run (server-only commands don't need it)
    if args.command not in ("version", "uninstall", "install", "mcp"):
        config = SchoolConfig()
        if not config.is_school_installed():
            _auto_install(config)

    commands = {
        "version": _cmd_version,
        "status": _cmd_status,
        "install": _cmd_install,
        "doctor": _cmd_doctor,
        "uninstall": _cmd_uninstall,
        "mcp": _cmd_mcp,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()
        sys.exit(1)
