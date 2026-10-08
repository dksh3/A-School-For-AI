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


def _cmd_skills(args: argparse.Namespace) -> None:
    """1A-2Z skill commands (Phase 2: GitHub discovery is opt-in)."""
    import json

    from core.skillgen.github import discovery
    from core.skillgen.registry import registry_for

    action = getattr(args, "skills_command", None)
    if action is None:
        sys.stderr.write(
            "school skills: choose list, search, github-search, discover, "
            "analyze, compare, or import\n"
        )
        sys.exit(1)

    keywords = [str(k) for k in (getattr(args, "keywords", None) or [])]
    if action == "list":
        registry = registry_for(".")
        report = {
            "ok": True,
            "skills": [
                {
                    "name": s.name,
                    "state": s.state.value,
                    "scope": s.scope.value,
                    "confidence": s.confidence,
                    "successes": s.success_count,
                    "failures": s.failure_count,
                    "source": s.provenance.get("source_type", "local"),
                }
                for s in sorted(registry.all(), key=lambda s: s.name)
            ],
            "count": registry.count(),
        }
    elif action == "search":
        import os

        from core.skillgen.matcher import match

        report = {
            "ok": True,
            "matches": match(
                registry_for("."),
                str(args.query or ""),
                agent_id=os.environ.get("SCHOOL_AGENT", "opencode"),
                project_id=os.environ.get("SCHOOL_PROJECT", ""),
                session_id=os.environ.get("SCHOOL_SESSION", ""),
                include_unusable=True,
                limit=10,
            ),
        }
    elif action == "github-search":
        report = discovery.search_github(
            task=str(args.task or ""),
            capability_gap=str(args.gap or ""),
            keywords=keywords,
            skill_name=str(args.skill_name or ""),
        )
    elif action == "discover":
        report = discovery.discover(
            task=str(args.task or ""),
            capability_gap=str(args.gap or ""),
            keywords=keywords,
            skill_name=str(args.skill_name or ""),
            max_files=int(args.max_files),
        )
    elif action == "analyze":
        report = discovery.analyze_external(
            args.owner,
            args.repo,
            file_path=str(args.file_path or ""),
            task=str(args.task or ""),
            registry=registry_for("."),
        )
    elif action == "compare":
        report = discovery.compare(
            args.owner,
            args.repo,
            file_path=str(args.file_path or ""),
            registry=registry_for("."),
        )
    elif action == "import":
        report = discovery.import_external(
            args.owner,
            args.repo,
            file_path=str(args.file_path or ""),
            approve=bool(args.approve),
            scope=str(args.scope or "agent"),
            acknowledge_license=bool(args.acknowledge_license),
            registry=registry_for("."),
            agent_id=str(args.agent_id or "opencode"),
            project_id=str(args.project or ""),
            session_id=str(args.session or ""),
        )
    else:  # pragma: no cover - argparse restricts choices
        sys.stderr.write(f"school skills: unknown action {action!r}\n")
        sys.exit(1)

    print(json.dumps(report, indent=2, default=str))
    if not report.get("ok"):
        sys.exit(1)


def _read_messages() -> list[dict]:
    """Read a JSON array of messages from stdin (empty when unavailable)."""
    import json

    try:
        if sys.stdin is None or sys.stdin.isatty():
            return []
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return []
    return data if isinstance(data, list) else []


def _cmd_context(args: argparse.Namespace) -> None:
    """school context: status | compress | restore | switch | keep."""
    import json

    from school import bridge

    action = args.context_command
    if action is None:
        print("school context: missing subcommand", file=sys.stderr)
        sys.exit(2)

    worktree = args.worktree or str(Path.cwd())
    command = "context_status"
    req: dict = {"worktree": worktree}
    if args.session:
        req["session"] = args.session
    if action == "compress":
        command = "context_compress"
        req["messages"] = _read_messages()
    elif action == "restore":
        command = "context_restore"
        req["block_id"] = args.block_id or ""
    elif action in ("switch", "keep"):
        command = "context_coexist"
        req["action"] = "set_decision"
        req["decision"] = action

    handler = bridge._COMMANDS.get(command)
    if handler is None:
        resp = {
            "ok": False,
            "error": {"type": "protocol", "message": f"unknown: {command}"},
        }
    else:
        resp = handler(req)

    if args.json:
        print(json.dumps(resp, ensure_ascii=False))
    elif action == "status":
        print(f"mode: {resp.get('mode', '?')}")
        print(f"decision: {resp.get('decision') or '-'}")
        blocks = resp.get("blocks", 0)
        restores = resp.get("restores", 0)
        print(f"blocks: {blocks}  restores: {restores}")
        if resp.get("chip"):
            print(resp["chip"])
        if resp.get("dcp") and not resp.get("decision"):
            from core.context.coexist import OFFER_TEXT

            print(OFFER_TEXT)
    else:
        print(f"ok: {resp.get('ok')}  mode: {resp.get('mode', '')}")
        if resp.get("chip"):
            print(resp["chip"])
    if not resp.get("ok"):
        sys.exit(1)


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

    skills_parser = subparsers.add_parser(
        "skills",
        help="1A-2Z skill management (Phase 2: GitHub discovery is opt-in)",
    )
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")

    skills_subparsers.add_parser("list", help="List local 1A-2Z skills (offline)")

    skills_search_parser = skills_subparsers.add_parser(
        "search", help="Search local 1A-2Z skills (offline)"
    )
    skills_search_parser.add_argument("query", help="Capability query")

    def _add_gap_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--task", default="", help="Current task driving the gap")
        p.add_argument(
            "--gap", default="", help="Capability gap to search for (preferred)"
        )
        p.add_argument(
            "--keywords", nargs="*", default=[], help="Focused keywords (no conversation)"
        )
        p.add_argument("--skill-name", default="", help="Known skill name to match")

    github_search_parser = skills_subparsers.add_parser(
        "github-search", help="Bounded GitHub repository search (read-only)"
    )
    _add_gap_args(github_search_parser)

    discover_parser = skills_subparsers.add_parser(
        "discover",
        help="Discover skill-like files in GitHub results (read-only, no clone)",
    )
    _add_gap_args(discover_parser)
    discover_parser.add_argument(
        "--max-files", type=int, default=5, help="Max files retrieved per discovery"
    )

    def _add_repo_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--owner", required=True, help="Repository owner")
        p.add_argument("--repo", required=True, help="Repository name")
        p.add_argument("--file-path", default="", help="Specific skill file path")

    analyze_parser = skills_subparsers.add_parser(
        "analyze", help="Budgeted model analysis of one GitHub candidate"
    )
    _add_repo_args(analyze_parser)
    analyze_parser.add_argument("--task", default="", help="Capability gap context")

    compare_parser = skills_subparsers.add_parser(
        "compare", help="Compare a GitHub candidate against local skills"
    )
    _add_repo_args(compare_parser)

    import_parser = skills_subparsers.add_parser(
        "import",
        help="Import an approved GitHub candidate (requires --approve)",
    )
    _add_repo_args(import_parser)
    import_parser.add_argument(
        "--approve",
        action="store_true",
        help="Explicit user approval (required to import)",
    )
    import_parser.add_argument(
        "--acknowledge-license",
        action="store_true",
        help="Acknowledge UNKNOWN-license review before import",
    )
    import_parser.add_argument(
        "--scope",
        default="agent",
        choices=["global", "agent", "project", "session"],
        help="Import scope (default agent; never automatic global)",
    )
    import_parser.add_argument("--agent-id", default="opencode", help="Agent identity")
    import_parser.add_argument("--project", default="", help="Project id")
    import_parser.add_argument("--session", default="", help="Session id")

    context_common = argparse.ArgumentParser(add_help=False)
    context_common.add_argument(
        "--json", action="store_true", help="Print the raw bridge JSON response"
    )
    context_common.add_argument("--session", default="", help="Session id")
    context_common.add_argument(
        "--worktree", default="", help="Worktree root (default: current directory)"
    )

    context_parser = subparsers.add_parser(
        "context",
        help="Context engine: status, compress, restore, switch, keep",
    )
    context_subparsers = context_parser.add_subparsers(dest="context_command")
    context_subparsers.add_parser(
        "status",
        parents=[context_common],
        help="Blocks, view mode, chip, DCP offer",
    )
    context_subparsers.add_parser(
        "compress",
        parents=[context_common],
        help="Compress messages read as a JSON array from stdin",
    )
    restore_parser = context_subparsers.add_parser(
        "restore",
        parents=[context_common],
        help="Restore blocks by id (default: latest)",
    )
    restore_parser.add_argument(
        "block_id", nargs="?", default="", help="Block id to restore"
    )
    context_subparsers.add_parser(
        "switch",
        parents=[context_common],
        help="School owns compression from now on (clean break)",
    )
    context_subparsers.add_parser(
        "keep",
        parents=[context_common],
        help="Keep DCP for message-level compression",
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
        "skills": _cmd_skills,
        "context": _cmd_context,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()
        sys.exit(1)
