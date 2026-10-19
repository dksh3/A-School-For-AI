"""School CLI - command-line interface for School."""

from __future__ import annotations

import argparse
import contextlib
import shutil
import sys
from pathlib import Path

from school import __version__
from school.config import SchoolConfig
from school.discovery import discover_bridge
from school.plugin_source import TS_PLUGIN_SOURCE


def _safe_err(exc: BaseException) -> str:
    """str(exc) that can never raise (hostile exceptions break __str__)."""
    try:
        return str(exc)
    except Exception:  # noqa: BLE001 — fail-open
        try:
            return repr(exc)
        except Exception:  # noqa: BLE001 — fail-open
            return f"<unprintable {type(exc).__name__}>"


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

    # Strict JSON output: NaN/Infinity and exotic values would produce
    # invalid JSON for machine consumers — sanitise before dumping.
    from school.bridge import _json_safe

    print(json.dumps(_json_safe(report), indent=2, default=str, allow_nan=False))
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
        try:
            resp = handler(req)
        except Exception as exc:  # noqa: BLE001 — fail-open: --json must
            # still emit valid JSON and the CLI must never traceback.
            resp = {
                "ok": False,
                "error": {"type": "runtime", "message": _safe_err(exc)},
            }
    if not isinstance(resp, dict):
        resp = {"ok": True, "result": resp}

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


def _write_stdout(text: str) -> None:
    """Write rendered output without ever closing or corrupting sys.stdout.

    The previous implementation wrapped ``sys.stdout.buffer`` in a fresh
    TextIOWrapper; its garbage collection closed the *shared* buffer and
    silently destroyed all buffered output plus every later write.
    """
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    except (UnicodeEncodeError, ValueError, OSError):
        pass  # narrow console encoding or closed wrapper: fall back to bytes
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        with contextlib.suppress(Exception):
            buffer.write(text.encode("utf-8", errors="replace"))
            buffer.flush()


def _cmd_visualize(args: argparse.Namespace) -> str:
    """school visualize: render any School visual. Returns the output string.

    Fail-open: hostile types/data/args can never raise out of this handler —
    invalid input reports to stderr and exits 2 (unknown type/invalid
    ``--data``) or 1 (render failure), keeping the CLI exit-code contract.
    """
    import json as _json

    from core.context.visual_dispatch import render_visual

    try:
        raw = args.data
        data = {}
        if raw:
            if isinstance(raw, str):
                try:
                    data = _json.loads(raw)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid --data JSON: {_safe_err(exc)}") from None
            elif isinstance(raw, dict):
                data = raw
            else:
                raise ValueError(f"invalid --data type: {type(raw).__name__}")
            if not isinstance(data, dict):
                raise ValueError("--data must be a JSON object")
    except ValueError as exc:
        print(f"visualize error: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(2) from None
    except Exception as exc:
        print(f"visualize error: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(1) from None

    try:
        out = render_visual(args.type, data=data, label=args.label, width=args.width)
        if not isinstance(out, str):
            out = str(out)
    except ValueError as exc:
        print(f"unknown visual type: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(2) from None
    except Exception as exc:
        print(f"visualize error: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(1) from None

    _write_stdout(out + "\n")
    return out


# ---------------------------------------------------------------------------
# Forge — Universal Idea→Artifact CLI (clarion / blueprint / edict / weave /
# compass / brainstorm). Universal: any kind of work — software, writing, research,
# business, planning, creative, life. Fail-open: hostile flags/JSON can never
# traceback out of these handlers.
# ---------------------------------------------------------------------------


def _forge_read_json(path: str, what: str) -> object:
    """Load a JSON document for a Forge command (exit 2 when unreadable)."""
    import json as _json

    try:
        return _json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"forge error: invalid {what}: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(2) from None


def _forge_expect_dict(raw: object, what: str) -> dict:
    """Require a JSON object where the contract says object (exit 2 otherwise).

    A wrong-shaped document is unreadable input, not an empty project: fabricating
    a blank artifact from it would be a silent success. Fail closed instead.
    """
    if isinstance(raw, dict):
        return raw
    print(
        f"forge error: {what} must be a JSON object, got {type(raw).__name__}",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _forge_interview_from_args(args: argparse.Namespace) -> object:
    """Build (or load) the discovery Interview shared by the Forge commands."""
    from core.forge.clarion import auto_answer, batch_answer, import_answers, start_interview
    from core.forge.models import Domain, Interview, InterviewMode

    interview_path = str(getattr(args, "interview", "") or "")
    if interview_path:
        raw = _forge_read_json(interview_path, "--interview JSON")
        return Interview.from_dict(_forge_expect_dict(raw, "--interview JSON"))

    doc = ""
    doc_path = str(getattr(args, "doc", "") or "")
    if doc_path:
        try:
            doc = Path(doc_path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"forge error: cannot read --doc: {_safe_err(exc)}", file=sys.stderr)
            raise SystemExit(2) from None

    answers_path = str(getattr(args, "answers", "") or "")
    if answers_path:
        mode = InterviewMode.BATCH
    elif doc:
        mode = InterviewMode.IMPORT
    else:
        mode = InterviewMode.AUTO
    interview = start_interview(
        title=str(getattr(args, "title", "") or ""),
        domain=Domain.coerce(getattr(args, "domain", "")),
        mode=mode,
        existing_doc=doc or None,
    )
    if answers_path:
        interview = batch_answer(interview, _forge_read_json(answers_path, "--answers JSON"))
    elif doc:
        interview = import_answers(interview, doc)
    else:
        interview = auto_answer(interview)
    return interview


def _forge_save_interview(args: argparse.Namespace, interview: object) -> None:
    """Write the interview JSON to --save when requested (best effort)."""
    import json as _json

    save_path = str(getattr(args, "save", "") or "")
    if not save_path:
        return
    try:
        Path(save_path).write_text(
            _json.dumps(interview.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        print(f"forge error: cannot write --save: {_safe_err(exc)}", file=sys.stderr)


def _forge_render_markdown(kind: str, obj: object, interview: object) -> str:
    """Render one Forge artifact: Markdown + School visual (fail-open)."""
    from core.forge.render import render_artifact

    art = render_artifact(kind, obj, interview)
    body = art.markdown or f"(no {kind} content)"
    return f"{body}\n\n{art.visual}" if art.visual else body


def _cmd_clarion(args: argparse.Namespace) -> str:
    """school clarion: discovery interview summary + next question (Markdown)."""
    from core.forge.clarion import interview_summary, next_question

    try:
        interview = _forge_interview_from_args(args)
        summary = interview_summary(interview)
        coverage = float(summary.get("coverage", 0.0) or 0.0)
        confidence = float(summary.get("overall_confidence", 0.0) or 0.0)
        lines = [
            f"# Clarion — {summary.get('title') or 'Untitled idea'}",
            "",
            f"- **Domain**: {summary.get('domain', 'general')} · "
            f"**Mode**: {summary.get('mode', 'auto')}",
            f"- **Coverage**: {coverage:.0%} · "
            f"**Answered**: {summary.get('answered_count', 0)} "
            f"of {summary.get('question_count', 0)} questions",
            f"- **Confidence**: {confidence:.2f} · "
            f"**Open questions**: {summary.get('open_question_count', 0)}",
            "",
            "## Open questions",
        ]
        open_questions = summary.get("open_questions") or []
        lines += [f"- {q}" for q in open_questions] or ["- (none)"]
        question = next_question(interview)
        lines += ["", "## Next question"]
        if question is not None:
            lines.append(f"- **{question.id}** [{question.dimension}] {question.prompt}")
        else:
            lines.append("- (interview complete)")
        out = "\n".join(lines) + "\n"
        _forge_save_interview(args, interview)
        _write_stdout(out)
        return out
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-open
        print(f"clarion error: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(1) from None


def _cmd_blueprint(args: argparse.Namespace) -> str:
    """school blueprint: design-spec artifact (Markdown + visual)."""
    from core.forge.blueprint import build_blueprint

    try:
        interview = _forge_interview_from_args(args)
        title = str(getattr(args, "title", "") or "")
        bp = build_blueprint(interview, title=title or None)
        out = _forge_render_markdown("blueprint", bp, interview) + "\n"
        _forge_save_interview(args, interview)
        _write_stdout(out)
        return out
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-open
        print(f"blueprint error: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(1) from None


def _cmd_edict(args: argparse.Namespace) -> str:
    """school edict: ordered commands + directives (Markdown + visual)."""
    from core.forge.edict import build_edict
    from core.forge.models import Blueprint

    try:
        interview = _forge_interview_from_args(args)
        blueprint = None
        blueprint_path = str(getattr(args, "blueprint", "") or "")
        if blueprint_path:
            raw = _forge_read_json(blueprint_path, "--blueprint JSON")
            blueprint = Blueprint.from_dict(_forge_expect_dict(raw, "--blueprint JSON"))
        edict = build_edict(interview, blueprint)
        out = _forge_render_markdown("edict", edict, interview) + "\n"
        _forge_save_interview(args, interview)
        _write_stdout(out)
        return out
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-open
        print(f"edict error: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(1) from None


def _cmd_weave(args: argparse.Namespace) -> str:
    """school weave: roadmap formation + timeline (Markdown + visual)."""
    from core.forge.models import Blueprint, Command
    from core.forge.weave import build_weave

    try:
        interview = _forge_interview_from_args(args)
        blueprint = None
        commands = None
        blueprint_path = str(getattr(args, "blueprint", "") or "")
        if blueprint_path:
            raw = _forge_read_json(blueprint_path, "--blueprint JSON")
            blueprint = Blueprint.from_dict(_forge_expect_dict(raw, "--blueprint JSON"))
        commands_path = str(getattr(args, "commands", "") or "")
        if commands_path:
            raw = _forge_read_json(commands_path, "--commands JSON")
            items = raw.get("commands") if isinstance(raw, dict) else raw
            if not isinstance(items, list):
                print(
                    "forge error: --commands JSON must be a list of commands "
                    'or an object with a "commands" list',
                    file=sys.stderr,
                )
                raise SystemExit(2)
            skipped = sum(1 for c in items if not isinstance(c, dict))
            if skipped:
                print(
                    f"forge warning: {skipped} --commands row(s) were not objects — ignored",
                    file=sys.stderr,
                )
            commands = [Command.from_dict(c) for c in items if isinstance(c, dict)]
        formation = build_weave(interview, commands, blueprint)
        out = _forge_render_markdown("weave", formation, interview) + "\n"
        _forge_save_interview(args, interview)
        _write_stdout(out)
        return out
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-open
        print(f"weave error: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(1) from None


def _cmd_compass(args: argparse.Namespace) -> str:
    """school compass: acceptance scenarios + checklist (Markdown + visual)."""
    from core.forge.compass import build_compass
    from core.forge.models import Blueprint, Command

    try:
        interview = _forge_interview_from_args(args)
        blueprint = None
        commands = None
        blueprint_path = str(getattr(args, "blueprint", "") or "")
        if blueprint_path:
            raw = _forge_read_json(blueprint_path, "--blueprint JSON")
            blueprint = Blueprint.from_dict(_forge_expect_dict(raw, "--blueprint JSON"))
        commands_path = str(getattr(args, "commands", "") or "")
        if commands_path:
            raw = _forge_read_json(commands_path, "--commands JSON")
            items = raw.get("commands") if isinstance(raw, dict) else raw
            if not isinstance(items, list):
                print(
                    "forge error: --commands JSON must be a list of commands "
                    'or an object with a "commands" list',
                    file=sys.stderr,
                )
                raise SystemExit(2)
            skipped = sum(1 for c in items if not isinstance(c, dict))
            if skipped:
                print(
                    f"forge warning: {skipped} --commands row(s) were not objects — ignored",
                    file=sys.stderr,
                )
            commands = [Command.from_dict(c) for c in items if isinstance(c, dict)]
        acceptance = build_compass(interview, blueprint, commands)
        out = _forge_render_markdown("compass", acceptance, interview) + "\n"
        _forge_save_interview(args, interview)
        _write_stdout(out)
        return out
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-open
        print(f"compass error: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(1) from None


def _cmd_prism(args: argparse.Namespace) -> str:
    """school brainstorm (legacy alias: school prism): divergent→convergent ideation."""
    from core.forge.models import Domain
    from core.forge.prism import (
        brainstorm,
        brainstorm_summary,
        cluster_ideas,
        score_ideas,
        select_top,
    )

    try:
        techniques_raw = str(getattr(args, "techniques", "") or "")
        techniques = [t.strip() for t in techniques_raw.split(",") if t.strip()] or None
        session = brainstorm(
            str(getattr(args, "topic", "") or ""),
            domain=Domain.coerce(getattr(args, "domain", "")),
            techniques=techniques,
            count=int(getattr(args, "count", 12)),
            seed=getattr(args, "seed", None),
        )
        session = score_ideas(session)
        session = select_top(session, int(getattr(args, "top", 3)))
        clusters = cluster_ideas(session)
        summary = brainstorm_summary(session)
        lines = [
            f"# Brainstorm — {session.topic or 'Untitled topic'}",
            "",
            f"- **Ideas**: {summary.get('idea_count', 0)} · "
            f"**Selected**: {summary.get('selected_count', 0)} · "
            f"**Domain**: {summary.get('domain', 'general')}",
            f"- **Techniques**: {', '.join(summary.get('techniques_used') or []) or '(default)'}",
            "",
            "## Ideas",
        ]
        for i, idea in enumerate(session.ideas, 1):
            lines.append(
                f"{i}. **{idea.title}** — score {idea.score:.2f} "
                f"(impact {idea.impact:.2f} × feasibility {idea.feasibility:.2f})"
            )
            if idea.description:
                lines.append(f"   {idea.description}")
        lines += ["", "## Clusters"]
        for name, members in (clusters or {}).items():
            lines.append(f"- **{name}**: {'; '.join(str(m) for m in members)}")
        lines += ["", "## Selected"]
        lines += [f"- {title}" for title in session.selected] or ["- (none)"]
        out = "\n".join(lines) + "\n"
        _write_stdout(out)
        return out
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-open
        print(f"brainstorm error: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(1) from None


def _calc_line(label: str, res: object) -> list[str]:
    """Render one CalcResult with full provenance (value is None on failure)."""
    ok = bool(getattr(res, "ok", False))
    value = getattr(res, "value", None)
    unit = str(getattr(res, "unit", "") or "")
    shown = f"{value} {unit}".rstrip() if ok else "(no value — check failed)"
    lines = [f"### {label}", "", f"- **value**: {shown}"]
    if not ok:
        lines.append(f"- **error**: {getattr(res, 'error', '') or 'calculation failed'}")
    formula = str(getattr(res, "formula", "") or "")
    if formula:
        lines.append(f"- formula: {formula}")
    inputs = getattr(res, "inputs", None) or {}
    for key in sorted(inputs):
        lines.append(f"- input: {key} = {inputs[key]}")
    inter = getattr(res, "intermediates", None) or {}
    for key in sorted(inter):
        lines.append(f"- intermediate: {key} = {inter[key]}")
    for attr, label2 in (("scope", "scope"), ("period", "period"), ("source", "source")):
        val = str(getattr(res, attr, "") or "")
        if val:
            lines.append(f"- {label2}: {val}")
    for lim in getattr(res, "limitations", None) or []:
        lines.append(f"- limitation: {lim}")
    return lines + [""]


def _cmd_quantify(args: argparse.Namespace) -> str:
    """school quantify: deterministic money/percent/risk/date checks with provenance."""
    from core.forge.constraints import (
        ConstraintRecord,
        check_phase_count,
        parse_budget_ceiling,
        validate_constraints,
    )
    from core.forge.quant import (
        money_remaining,
        money_total,
        percentage,
        percentage_point_change,
        relative_change,
        verify_budget,
    )
    from core.forge.risk import expected_loss, ordinal_priority, scenario_expected_value
    from core.forge.temporal import (
        check_availability,
        parse_date,
        utc_today,
        validate_schedule,
    )

    path = str(getattr(args, "file", "") or "")
    if not path:
        print("quantify error: --file is required", file=sys.stderr)
        raise SystemExit(2) from None
    raw = _forge_read_json(path, "--file JSON")
    data = _forge_expect_dict(raw, "--file JSON")
    title = str(data.get("title") or "Untitled")
    currency = str(data.get("currency") or "")
    out: list[str] = [f"# Precision report — {title}", ""]

    def _money_rows(items: object) -> tuple[list[tuple], list[str]]:
        rows: list[tuple] = []
        problems: list[str] = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                name = str(item.get("name") or "")
                amt = item.get("amount")
                cur = str(item.get("currency") or "")
                rows.append((name, amt, cur) if cur else (name, amt))
            elif isinstance(item, (list, tuple)) and len(item) in (2, 3):
                cur = str(item[2]) if len(item) == 3 else ""
                rows.append(
                    (str(item[0]), item[1], cur) if cur else (str(item[0]), item[1])
                )
            else:
                problems.append(repr(item))
        return rows, problems

    # ---- Money ----------------------------------------------------------
    budget = data.get("budget") if isinstance(data.get("budget"), dict) else {}
    if budget:
        out += ["## Money", ""]
        lines_in, bad_lines = _money_rows(budget.get("lines"))
        tax, bad_tax = _money_rows(budget.get("tax"))
        fees, bad_fees = _money_rows(budget.get("fees"))
        transport, bad_transport = _money_rows(budget.get("transport"))
        discounts, bad_discounts = _money_rows(budget.get("discounts"))
        problems = bad_lines + bad_tax + bad_fees + bad_transport + bad_discounts
        if problems:
            out += [
                "### Budget total",
                "",
                "- **value**: (no value — input error)",
                f"- **error**: {len(problems)} budget row(s) in an unrecognized shape"
                " — no total is claimed",
            ]
            out += [f"- unparsed row: {p}" for p in problems]
            out.append("")
        else:
            total = money_total(
                lines_in,
                currency=currency,
                tax=tax or None,
                fees=fees or None,
                transport=transport or None,
                discounts=discounts or None,
                source=str(budget.get("source") or ""),
            )
            out += _calc_line("Budget total", total)
            if budget.get("declared_total") is not None:
                recon = verify_budget(
                    lines_in,
                    budget.get("declared_total"),
                    currency=currency,
                    source="declared total is a claim, not an input",
                )
                out += _calc_line("Declared-total reconciliation", recon)
            ceiling_text = str(budget.get("ceiling_text") or "")
            if ceiling_text:
                ceiling, ceil_cur = parse_budget_ceiling(ceiling_text)
                out += [
                    f"- ceiling text: {ceiling_text}",
                    f"- ceiling parsed: {ceiling} {ceil_cur or currency}".rstrip(),
                    "",
                ]
                out += _calc_line(
                    "Remaining under ceiling",
                    money_remaining(
                        ceiling,
                        total.value if total.ok else None,
                        currency=ceil_cur or currency,
                        source="ceiling from requirement text",
                    ),
                )
    else:
        out += ["## Money", "", "- not supplied — no money claim is made.", ""]

    # ---- Percentages ----------------------------------------------------
    pcts = data.get("percentages")
    if isinstance(pcts, list) and pcts:
        out += ["## Percentages", ""]
        pct_bad: list[str] = []
        for i, p in enumerate(pcts, 1):
            if not isinstance(p, dict):
                pct_bad.append(repr(p))
                continue
            res = percentage(
                p.get("numerator"),
                p.get("denominator"),
                unit=str(p.get("unit") or "%"),
                scope=str(p.get("scope") or ""),
                period=str(p.get("period") or ""),
                source=str(p.get("source") or ""),
            )
            out += _calc_line(f"Percentage {i}", res)
            if p.get("claimed") not in (None, ""):
                from core.forge.quant import check_percent_consistency

                out += _calc_line(
                    f"Claimed vs computed {i}",
                    check_percent_consistency(
                        p.get("claimed"), p.get("numerator"), p.get("denominator")
                    ),
                )
        if pct_bad:
            out += [
                f"- **error**: {len(pct_bad)} row(s) in an unrecognized shape"
                " — no result is claimed for them (recognized rows above are computed"
                " normally)",
                *[f"- unparsed row: {b}" for b in pct_bad],
                "",
            ]
    else:
        out += ["## Percentages", "", "- not supplied — no percentage claim is made.", ""]

    # ---- Changes (pp vs relative) ---------------------------------------
    changes = data.get("changes")
    if isinstance(changes, list) and changes:
        out += ["## Changes", ""]
        chg_bad: list[str] = []
        for i, ch in enumerate(changes, 1):
            if not isinstance(ch, dict):
                chg_bad.append(repr(ch))
                continue
            out += _calc_line(
                f"Percentage-point change {i}",
                percentage_point_change(ch.get("before"), ch.get("after")),
            )
            out += _calc_line(
                f"Relative change {i}", relative_change(ch.get("before"), ch.get("after"))
            )
        if chg_bad:
            out += [
                f"- **error**: {len(chg_bad)} row(s) in an unrecognized shape"
                " — no result is claimed for them (recognized rows above are computed"
                " normally)",
                *[f"- unparsed row: {b}" for b in chg_bad],
                "",
            ]
    else:
        out += ["## Changes", "", "- not supplied.", ""]

    # ---- Risks ----------------------------------------------------------
    risks = data.get("risks")
    if isinstance(risks, list) and risks:
        out += ["## Risks", ""]
        rsk_bad: list[str] = []
        for i, r in enumerate(risks, 1):
            if not isinstance(r, dict):
                rsk_bad.append(repr(r))
                continue
            out += _calc_line(
                f"Expected loss {i}",
                expected_loss(
                    r.get("probability"),
                    r.get("conditional_loss"),
                    probability_class=str(r.get("probability_class") or "unknown"),
                    loss_unit=str(r.get("loss_unit") or ""),
                    probability_method=str(r.get("probability_method") or ""),
                    probability_source=str(r.get("probability_source") or ""),
                    source=str(r.get("source") or ""),
                ),
            )
            if r.get("probability_label") and r.get("severity_label"):
                out += [
                    f"### Ordinal priority {i}",
                    "",
                    f"- {ordinal_priority(str(r['probability_label']), str(r['severity_label']))}",
                    "",
                ]
        if rsk_bad:
            out += [
                f"- **error**: {len(rsk_bad)} row(s) in an unrecognized shape"
                " — no result is claimed for them (recognized rows above are computed"
                " normally)",
                *[f"- unparsed row: {b}" for b in rsk_bad],
                "",
            ]
    else:
        out += ["## Risks", "", "- not supplied — no risk figure is claimed.", ""]

    # ---- Scenarios (E[X] over the risk space) ----------------------------
    scen = data.get("scenarios")
    if isinstance(scen, list) and scen:
        out += ["## Scenarios", ""]
        outcomes: list = []
        scen_bad: list[str] = []
        for s in scen:
            if isinstance(s, dict):
                outcomes.append((s.get("probability"), s.get("outcome")))
            elif isinstance(s, (list, tuple)) and len(s) == 2:
                outcomes.append((s[0], s[1]))
            else:
                scen_bad.append(repr(s))
        if scen_bad:
            out += [
                "- **value**: (no value — input error)",
                f"- **error**: {len(scen_bad)} scenario row(s) in an unrecognized shape"
                " — no E[X] is claimed",
            ]
            out += [f"- unparsed row: {p}" for p in scen_bad]
            out.append("")
        else:
            out += _calc_line(
                "Scenario expected value",
                scenario_expected_value(
                    outcomes,
                    source="scenario table in input JSON",
                    unit=currency or str(data.get("unit") or ""),
                ),
            )

    # ---- Schedule & availability ----------------------------------------
    sched = data.get("schedule") if isinstance(data.get("schedule"), dict) else {}
    sched_contradictions: list[str] = []
    sched_time_warnings = 0
    avail = data.get("availability")
    if sched or avail:
        out += ["## Dates", ""]
        ref = None
        if sched.get("reference"):
            ref_fact = parse_date(sched.get("reference"), label="reference")
            ref = ref_fact.value
            out += [
                f"- reference date: {ref_fact.value} ({ref_fact.state})",
                f"- reference source: {ref_fact.source}",
                "",
            ]
        if sched:
            start = parse_date(sched.get("start"), label="start")
            deadline = parse_date(sched.get("deadline"), label="deadline")
            out += [
                f"- start: {start.value} ({start.state})",
                f"- deadline: {deadline.value} ({deadline.state})",
                "",
            ]
            check = validate_schedule(
                start=start.value,
                deadline=deadline.value,
                duration_days=sched.get("duration_days"),
                reference=ref or utc_today(),
            )
            sched_contradictions = list(getattr(check, "contradictions", []))
            sched_time_warnings = len(check.violations) - len(sched_contradictions)
            out += [
                f"### Schedule check — {'ok' if check.ok else 'VIOLATIONS'}",
                "",
                *[f"- violation: {v}" for v in check.violations],
                *[f"- unknown: {u}" for u in check.unknowns],
                *[f"- finding: {f}" for f in check.findings],
                "",
            ]
        if isinstance(avail, list):
            av_bad: list[str] = []
            for i, a in enumerate(avail, 1):
                if not isinstance(a, dict):
                    av_bad.append(repr(a))
                    continue
                a_from = parse_date(a.get("available_from"), label="available_from")
                a_until = parse_date(a.get("available_until"), label="available_until")
                chk = check_availability(
                    as_of=parse_date(a.get("as_of"), label="as_of").value or ref or utc_today(),
                    available_from=a_from.value,
                    available_until=a_until.value,
                    item=str(a.get("item") or f"item {i}"),
                )
                out += [
                    f"### Availability {i} — {'ok' if chk.ok else 'NOT AVAILABLE'}",
                    "",
                    *[f"- {f}" for f in chk.findings],
                    "",
                ]
            if av_bad:
                out += [
                    f"- **error**: {len(av_bad)} row(s) in an unrecognized shape"
                    " — no result is claimed for them (recognized rows above are computed"
                    " normally)",
                    *[f"- unparsed row: {b}" for b in av_bad],
                    "",
                ]
    else:
        out += ["## Dates", "", "- not supplied — no date claim is made.", ""]

    # ---- Constraints -----------------------------------------------------
    # Schedule self-contradictions are hard violations (policy: contradictions
    # hard, time-relative findings warning-only). They enter the verdict as
    # machine-checked hard rows — an empty or satisfied checklist cannot
    # certify a self-contradicting plan.
    sched_records = [
        ConstraintRecord(
            id=f"SCHEDULE-{i}",
            requirement="a schedule that does not contradict itself",
            kind="hard",
            validation_method="temporal.validate_schedule",
            actual=contradiction,
            expected="a schedule that does not contradict itself",
            evidence_source="temporal check",
            evidence_kind="machine_checked",
            result="violated",
            explanation=f"{contradiction} — a self-contradicting"
            " plan cannot satisfy a hard constraint",
        )
        for i, contradiction in enumerate(sched_contradictions, 1)
    ]
    cons = data.get("constraints")
    records: list[ConstraintRecord] = []
    cons_supplied = isinstance(cons, list) and cons
    if cons_supplied or sched_records:
        out += ["## Constraints", ""]
    if cons_supplied:
        import re as _re

        from core.forge.constraints import phase_requirement_count

        cons_bad: list[str] = []
        for c in cons:
            if not isinstance(c, dict):
                cons_bad.append(repr(c))
                continue
            requirement = str(c.get("requirement") or "")
            actual = c.get("actual")
            act_m = _re.search(r"-?\d+", str(actual)) if actual is not None else None
            if (
                c.get("result") in (None, "")
                and act_m
                and phase_requirement_count(requirement) is not None
            ):
                records.append(check_phase_count(requirement, int(act_m.group())))
            else:
                records.append(
                    ConstraintRecord(
                        id=str(c.get("id") or ""),
                        requirement=requirement,
                        kind=str(c.get("kind") or "hard"),
                        validation_method=str(c.get("validation_method") or ""),
                        actual=str(actual if actual is not None else ""),
                        expected=str(c.get("expected") or ""),
                        evidence_source=str(c.get("evidence_source") or ""),
                        evidence_kind=str(c.get("evidence_kind") or "missing"),
                        result=str(c.get("result") or "unresolved"),
                        explanation=str(c.get("explanation") or ""),
                    )
                )
        if cons_bad:
            out += [
                f"- **error**: {len(cons_bad)} constraint row(s) in an unrecognized shape"
                " — the checklist is incomplete",
                *[f"- unparsed row: {b}" for b in cons_bad],
                "",
            ]
            records.append(
                ConstraintRecord(
                    id="INPUT-ERROR",
                    requirement="every hard constraint row must be readable",
                    kind="hard",
                    validation_method="input boundary check",
                    actual="",
                    expected="a complete checklist",
                    evidence_source="cli input boundary",
                    evidence_kind="missing",
                    result="unresolved",
                    explanation=f"{len(cons_bad)} constraint row(s) could not be parsed;"
                    " an unreadable row is not evidence of satisfaction",
                )
            )
    if cons_supplied or sched_records:
        records.extend(sched_records)
        verdict = validate_constraints(records)
        out += [
            f"- checklist: {verdict.score_note}",
            *[f"- blocking: {b}" for b in verdict.blocking],
            *[f"- condition: {c}" for c in verdict.conditions],
            f"- **verdict**: {verdict.reason}",
            *(
                [
                    f"- note: {sched_time_warnings} time-relative schedule warning(s)"
                    " — reported, not verdict-affecting"
                ]
                if sched_time_warnings
                else []
            ),
            "",
        ]
    else:
        out += ["## Constraints", "", "- not supplied — nothing is certified.", ""]

    report = "\n".join(out) + "\n"
    _write_stdout(report)
    save_path = str(getattr(args, "save", "") or "")
    if save_path:
        try:
            Path(save_path).write_text(report, encoding="utf-8")
        except OSError as exc:
            print(f"quantify error: cannot write --save: {_safe_err(exc)}", file=sys.stderr)
    return report


def _cmd_elicit(args: argparse.Namespace) -> str:
    """school elicit: material unknowns -> prioritized questions + completion status."""
    from core.forge.requirements import (
        Requirement,
        Unknown,
        elicitation_status,
        from_interview,
        next_batch,
        prioritize,
        requirements_summary,
    )

    path = str(getattr(args, "file", "") or "")
    interview_path = str(getattr(args, "interview", "") or "")
    requirements: list[Requirement] = []
    unknowns: list[Unknown] = []
    unk_bad: list[str] = []
    goal = ""
    verification_defined = bool(getattr(args, "verification_defined", False))
    controller_mode = any(
        [
            getattr(args, "question_budget", None) is not None,
            bool(getattr(args, "session", "")),
            bool(getattr(args, "answers", "")),
            bool(getattr(args, "no_followups", False)),
            bool(getattr(args, "no_early_stop", False)),
        ]
    )
    session_path = str(getattr(args, "session", "") or "")
    resuming = bool(session_path and Path(session_path).exists())
    if interview_path:
        from core.forge.models import Interview

        interview_raw = _forge_read_json(interview_path, "--interview JSON")
        interview = Interview.from_dict(_forge_expect_dict(interview_raw, "--interview JSON"))
        unknowns = from_interview(interview)
        goal = str(getattr(interview, "title", "") or "")
    elif path:
        raw = _forge_read_json(path, "--file JSON")
        data = _forge_expect_dict(raw, "--file JSON")
        goal = str(data.get("goal") or "")
        verification_defined = verification_defined or bool(data.get("verification_defined"))
        for r in data.get("requirements") or []:
            if isinstance(r, dict):
                requirements.append(
                    Requirement(
                        id=str(r.get("id") or ""),
                        kind=str(r.get("kind") or "objective"),
                        text=str(r.get("text") or ""),
                        source=str(r.get("source") or "user"),
                    )
                )
        for u in data.get("unknowns") or []:
            if not isinstance(u, dict):
                unk_bad.append(repr(u))
                continue
            unknowns.append(
                Unknown(
                    id=str(u.get("id") or ""),
                    question=str(u.get("question") or ""),
                    variable=str(u.get("variable") or ""),
                    why_it_matters=str(u.get("why_it_matters") or ""),
                    affects=tuple(str(a) for a in (u.get("affects") or ())),
                    derivable=bool(u.get("derivable")),
                    derivation_note=str(u.get("derivation_note") or ""),
                    retrievable=bool(u.get("retrievable")),
                    authoritative_source=str(u.get("authoritative_source") or ""),
                    must_ask_user=bool(u.get("must_ask_user", True)),
                    if_unknown=str(u.get("if_unknown") or ""),
                    wrong_assumption_cost=str(u.get("wrong_assumption_cost") or "medium"),
                    range_safe=bool(u.get("range_safe")),
                    range_note=str(u.get("range_note") or ""),
                    state=str(u.get("state") or "UNKNOWN"),
                    provenance=str(u.get("provenance") or ""),
                    depends_on=tuple(str(d) for d in (u.get("depends_on") or ())),
                    critical=bool(u.get("critical")),
                    asked_keys=tuple(str(k) for k in (u.get("asked_keys") or ())),
                )
            )
        for i, _bad in enumerate(unk_bad, 1):
            unknowns.append(
                Unknown(
                    id=f"u:unparsed:{i}",
                    question=f"unparsed unknown row {i} — shape not recognized (fix the input)",
                    variable=f"unparsed_{i}",
                    why_it_matters="an input row could not be read; its question is unknown,"
                    " not absent",
                    affects=("correctness",),
                    derivable=False,
                    derivation_note="",
                    retrievable=False,
                    authoritative_source="",
                    must_ask_user=True,
                    if_unknown="resolve the malformed input row before trusting this status",
                    wrong_assumption_cost="high",
                    range_safe=False,
                    range_note="",
                    state="UNKNOWN",
                    provenance="cli input boundary",
                    depends_on=(),
                    critical=True,
                    asked_keys=(),
                )
            )
    elif controller_mode and resuming:
        pass  # a resumed session carries the question state
    else:
        print("elicit error: --file or --interview is required", file=sys.stderr)
        raise SystemExit(2) from None

    if controller_mode:
        return _elicit_controller(
            args, goal, requirements, unknowns, unk_bad, verification_defined
        )

    asked = {k.strip() for k in str(getattr(args, "asked", "") or "").split(",") if k.strip()}
    batch = next_batch(
        unknowns,
        asked=asked,
        batch_size=int(getattr(args, "batch_size", 5)),
    )
    status = elicitation_status(unknowns, verification_defined=verification_defined)
    out = [
        f"# Elicitation — {goal or 'Untitled'}",
        "",
        "## Requirements summary",
        "",
        requirements_summary(requirements, unknowns),
        "",
        *(
            [
                "## Unparsed input rows",
                "",
                f"- **error**: {len(unk_bad)} unknown row(s) in an unrecognized shape"
                " — each becomes a blocking unknown (unknown, not absent)",
                *[f"- unparsed row: {b}" for b in unk_bad],
                "",
            ]
            if unk_bad
            else []
        ),
        "## Priority order (highest materiality first)",
        "",
    ]
    for u in prioritize(unknowns):
        out.append(
            f"- `{u.id}` [{u.state}] cost={u.wrong_assumption_cost}"
            f"{' · critical' if u.critical else ''}{'' if u.must_ask_user else ' · optional'}"
            f" — {u.question}"
        )
    out += ["", "## Next question batch (ask these now)", ""]
    if batch:
        for u in batch:
            out.append(f"- `{u.id}` — {u.question}")
            if u.why_it_matters:
                out.append(f"  - why: {u.why_it_matters}")
            out.append(f"  - if unknown: {u.if_unknown or 'record an explicit unknown'}")
    else:
        out.append("- (none — nothing to ask right now)")
    out += [
        "",
        "## Completion status",
        "",
        f"- complete: {'yes' if status.complete else 'no'}",
        f"- blocking: {', '.join(status.blocking) or '(none)'}",
        *[f"- authorized assumption: {a}" for a in status.authorized_assumptions],
        *[f"- conflict: {c}" for c in status.unresolved_conflicts],
        f"- verification defined: {'yes' if status.verification_defined else 'no'}",
        "",
        "Assumptions are recorded as assumptions, never as facts.",
        "",
    ]
    report = "\n".join(out) + "\n"
    _write_stdout(report)
    return report


def _elicit_controller(
    args: argparse.Namespace,
    goal: str,
    requirements: list,
    unknowns: list,
    unk_bad: list[str],
    verification_defined: bool,
) -> str:
    """Controller mode: strict question budget + adaptive follow-ups + session state.

    A question consumes one budget unit only when it is actually presented.
    Follow-ups share the same budget; refused duplicates never consume or refill.
    Budget exhaustion is not success. The config is fixed for a resumed session.
    """
    import json
    import os

    from core.forge.questions import (
        DEFAULT_QUESTION_BUDGET,
        QuestionBudget,
        QuestioningSession,
    )
    from core.forge.requirements import elicitation_status, prioritize, requirements_summary

    session_path = str(getattr(args, "session", "") or "")
    batch_size = int(getattr(args, "batch_size", 5) or 5)
    budget_arg = getattr(args, "question_budget", None)
    no_followups = bool(getattr(args, "no_followups", False))
    no_early_stop = bool(getattr(args, "no_early_stop", False))

    session: QuestioningSession
    if session_path and Path(session_path).exists():
        raw = _forge_read_json(session_path, "--session JSON")
        data = _forge_expect_dict(raw, "--session JSON")
        try:
            session = QuestioningSession.from_dict(data)
        except ValueError as exc:
            print(f"elicit error: cannot restore session: {exc}", file=sys.stderr)
            raise SystemExit(2) from None
        drift: list[str] = []
        if budget_arg is not None and int(budget_arg) != session.config.question_budget:
            drift.append(
                f"--question-budget {budget_arg} vs session {session.config.question_budget}"
            )
        if no_followups == session.config.allow_followups:
            drift.append("--no-followups vs the session follow-up setting")
        if no_early_stop == session.config.stop_early:
            drift.append("--no-early-stop vs the session early-stop setting")
        if drift:
            print(
                "elicit error: configuration is fixed for a resumed session: "
                + "; ".join(drift)
                + " — start a new session (drop --session) to change it",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
    else:
        try:
            config = QuestionBudget(
                question_budget=(
                    DEFAULT_QUESTION_BUDGET if budget_arg is None else int(budget_arg)
                ),
                allow_followups=not no_followups,
                stop_early=not no_early_stop,
            )
        except (TypeError, ValueError) as exc:
            print(f"elicit error: invalid question budget: {exc}", file=sys.stderr)
            raise SystemExit(2) from None
        session = QuestioningSession(config=config, unknowns=unknowns)

    session.verification_defined = session.verification_defined or verification_defined

    answers_path = str(getattr(args, "answers", "") or "")
    if answers_path:
        raw_answers = _forge_read_json(answers_path, "--answers JSON")
        if not isinstance(raw_answers, list):
            print(
                "elicit error: --answers JSON must be a list of "
                "{id|question, answer, confidence?} objects",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        for i, row in enumerate(raw_answers, 1):
            if not isinstance(row, dict):
                print(f"elicit error: --answers row {i} must be an object", file=sys.stderr)
                raise SystemExit(2) from None
            conf = row.get("confidence")
            confidence = (
                float(conf)
                if isinstance(conf, (int, float)) and not isinstance(conf, bool)
                else None
            )
            try:
                session.record_answer(
                    str(row.get("id") or row.get("question") or ""),
                    "" if row.get("answer") is None else str(row.get("answer")),
                    confidence=confidence,
                )
            except ValueError as exc:
                print(f"elicit error: {exc}", file=sys.stderr)
                raise SystemExit(2) from None

    presented_rows = []
    while len(presented_rows) < batch_size:
        pres = session.ask_next()
        if pres is None:
            break
        presented_rows.append(pres)
    if session.stop_reason is None and session.exhausted:
        session.ask_next()  # records the honest 'budget-exhausted' stop

    report_dict = session.status_report()
    stop_line = report_dict.get("stop_reason") or (
        "(not stopped — question batch limit reached; run again to continue)"
    )
    out = [
        f"# Elicitation — {goal or 'Untitled'}",
        "",
        "## Requirements summary",
        "",
        requirements_summary(requirements, session.unknowns),
        "",
    ]
    if unk_bad:
        out += [
            "## Unparsed input rows",
            "",
            f"- **error**: {len(unk_bad)} unknown row(s) in an unrecognized shape"
            " — each becomes a blocking unknown (unknown, not absent)",
            *[f"- unparsed row: {b}" for b in unk_bad],
            "",
        ]
    out += ["## Priority order (highest materiality first)", ""]
    for u in prioritize(session.unknowns):
        out.append(
            f"- `{u.id}` [{u.state}] cost={u.wrong_assumption_cost}"
            f"{' · critical' if u.critical else ''}{'' if u.must_ask_user else ' · optional'}"
            f" — {u.question}"
        )
    out += ["", "## Next question batch (ask these now)", ""]
    if presented_rows:
        for p in presented_rows:
            out.append(f"- `{p.id}` [{p.kind}] — {p.question}")
            if p.why:
                out.append(f"  - why: {p.why}")
            out.append(f"  - remaining after: {p.remaining_after}")
    else:
        out.append("- (none — nothing to ask right now)")
    out += [
        "",
        "## Question budget",
        "",
        f"- configured maximum: {session.config.question_budget}",
        f"- presented: {session.presented}",
        f"- remaining: {session.remaining}",
        f"- follow-ups enabled: {'yes' if session.config.allow_followups else 'no'}"
        f" (follow-ups asked: {report_dict.get('followups_asked', session.followups_asked)})",
        f"- early stopping: {'yes' if session.config.stop_early else 'no'}",
        f"- why questioning stopped: {stop_line}",
    ]
    if session.stop_detail:
        out.append(f"- stop detail: {session.stop_detail}")
    unresolved = report_dict.get("unresolved_questions") or []
    out += [
        f"- outcome: {report_dict.get('outcome', session.outcome())}",
        f"- unresolved material questions: {', '.join(unresolved) or '(none)'}",
        f"- repeats refused: {report_dict.get('repeats_refused', session.repeats_refused)}",
    ]
    status = elicitation_status(
        session.unknowns, verification_defined=session.verification_defined
    )
    out += [
        "",
        "## Completion status",
        "",
        f"- complete: {'yes' if status.complete else 'no'}",
        f"- blocking: {', '.join(status.blocking) or '(none)'}",
        *[f"- authorized assumption: {a}" for a in status.authorized_assumptions],
        *[f"- conflict: {c}" for c in status.unresolved_conflicts],
        f"- verification defined: {'yes' if status.verification_defined else 'no'}",
        "",
        "Assumptions are recorded as assumptions, never as facts.",
        "",
    ]
    report = "\n".join(out) + "\n"
    if session_path:
        tmp = session_path + ".tmp"
        try:
            Path(tmp).write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
            os.replace(tmp, session_path)
        except OSError as exc:
            print(f"elicit error: cannot write --session: {exc}", file=sys.stderr)
            raise SystemExit(2) from None
    _write_stdout(report)
    return report


def _cmd_investigate(args: argparse.Namespace) -> str:
    """school investigate: adaptive diagnostic case — probe, prioritize, report."""
    import json

    from core.forge.investigate import Investigation

    path = str(getattr(args, "file", "") or "")
    if not path:
        print("investigate error: --file is required", file=sys.stderr)
        raise SystemExit(2) from None
    try:
        case = Investigation.load(path)
    except Exception as exc:  # noqa: BLE001
        print(f"investigate error: cannot load case JSON: {_safe_err(exc)}", file=sys.stderr)
        raise SystemExit(2) from None

    action = str(getattr(args, "action", "") or "report")
    if action == "probe":
        cmd = str(getattr(args, "probe_cmd", "") or "")
        if not cmd:
            print("investigate error: --probe-cmd is required for --action probe", file=sys.stderr)
            raise SystemExit(2) from None
        ev = case.probe(
            cmd,
            kind=str(getattr(args, "probe_kind", "") or "command"),
            ref=str(getattr(args, "probe_ref", "") or ""),
            timeout_s=float(getattr(args, "timeout", 60.0) or 60.0),
        )
        case.save(path)  # resumable: evidence is persisted back into the case file
        report = "\n".join(
            [
                f"# Probe evidence {ev.id}",
                "",
                f"- kind: {ev.kind}",
                f"- ref: {ev.ref or '(none)'}",
                f"- captured: {ev.captured}",
                "",
                "```",
                ev.detail,
                "```",
                "",
            ]
        )
    elif action == "status":
        report = (
            f"# Investigation status — {case.id}\n\n"
            f"```json\n{json.dumps(case.assessment(), indent=2)}\n```\n"
        )
    elif action == "next":
        nxt = case.next_action()
        if nxt is None:
            report = "# Next action\n\n(none — no open findings or questions)\n"
        else:
            report = (
                "# Next action\n\n"
                f"- target: {nxt['target']}\n"
                f"- action: {nxt['action_kind']}\n"
                f"- reason: {nxt['reason']}\n"
            )
    else:
        report = case.to_markdown()

    _write_stdout(report)
    save_path = str(getattr(args, "save", "") or "")
    if save_path:
        try:
            Path(save_path).write_text(report, encoding="utf-8")
        except OSError as exc:
            print(f"investigate error: cannot write --save: {_safe_err(exc)}", file=sys.stderr)
    return report


def _parse_args_safe(parser: argparse.ArgumentParser) -> argparse.Namespace:
    """Parse argv, coercing hostile non-str entries to safe strings.

    Raw ``sys.argv`` can be mutated programmatically with None/int/list
    entries; argparse itself raises TypeError/KeyError on those and used to
    escape ``main()`` as a traceback. Coercion keeps the pinned argparse
    contract (SystemExit(2) with usage text) while never crashing.
    """
    argv: list[str] = []
    for item in sys.argv[1:]:
        if isinstance(item, str):
            argv.append(item)
        else:
            try:
                argv.append(str(item))
            except Exception:  # noqa: BLE001 — fail-open
                argv.append(f"<{type(item).__name__}>")
    return parser.parse_args(argv)


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

    viz_parser = subparsers.add_parser(
        "visualize", help="Render School visuals (sparkline, heatmap, donut, radar, etc.)"
    )
    viz_parser.add_argument(
        "type",
        help=(
            "Visual type: sparkline|heatmap|donut|radar|gauge|timeline|tree|"
            "flow|spinner|waterfall|braille|subcell|status_matrix|network|"
            "dashboard|gradient|emoji|comparison"
        ),
    )
    viz_parser.add_argument("--label", default="", help="Label/title")
    viz_parser.add_argument("--data", default="{}", help="JSON data")
    viz_parser.add_argument("--width", type=int, default=20, help="Bar width")

    # Forge — Universal Idea→Artifact (clarion/blueprint/edict/weave/compass/brainstorm)
    forge_common = argparse.ArgumentParser(add_help=False)
    forge_common.add_argument("--title", default="", help="Idea or goal title")
    forge_common.add_argument(
        "--domain",
        default="general",
        help=(
            "coding | writing | research | business | planning | education | "
            "creative | ops | data | life | general"
        ),
    )
    forge_common.add_argument(
        "--mode", default="auto", help="interview | batch | auto | import (default auto)"
    )
    forge_common.add_argument(
        "--doc", default="", help="Existing doc file to seed answers from"
    )
    forge_common.add_argument(
        "--interview", default="", help="Saved interview JSON (skips start)"
    )
    forge_common.add_argument(
        "--answers", default="", help="Batch answers JSON file (mode=batch)"
    )
    forge_common.add_argument(
        "--save", default="", help="Write the resulting interview JSON here"
    )

    subparsers.add_parser(
        "clarion",
        parents=[forge_common],
        help="Discovery interview for ANY kind of work (idea -> requirements)",
    )
    subparsers.add_parser(
        "blueprint",
        parents=[forge_common],
        help="Design spec from a discovery interview (idea -> spec)",
    )
    edict_parser = subparsers.add_parser(
        "edict",
        parents=[forge_common],
        help="Ordered commands + directives (spec -> execution)",
    )
    edict_parser.add_argument(
        "--blueprint", default="", help="Blueprint JSON file (optional)"
    )
    weave_parser = subparsers.add_parser(
        "weave",
        parents=[forge_common],
        help="Roadmap formation + timeline (plan -> phases/lanes/critical path)",
    )
    weave_parser.add_argument(
        "--blueprint", default="", help="Blueprint JSON file (optional)"
    )
    weave_parser.add_argument(
        "--commands", default="", help="Commands JSON file (optional)"
    )
    compass_parser = subparsers.add_parser(
        "compass",
        parents=[forge_common],
        help="Acceptance scenarios + checklist (verify the artifact)",
    )
    compass_parser.add_argument(
        "--blueprint", default="", help="Blueprint JSON file (optional)"
    )
    compass_parser.add_argument(
        "--commands", default="", help="Commands JSON file (optional)"
    )
    # "brainstorm" is canonical; "prism" is the legacy alias (wire name kept for compat).
    prism_parser = subparsers.add_parser(
        "brainstorm",
        aliases=["prism"],
        help="Brainstorm ideas, score, cluster, select (any topic, any domain)",
    )
    prism_parser.add_argument("--topic", default="", help="Topic to brainstorm")
    prism_parser.add_argument(
        "--domain",
        default="general",
        help=(
            "coding | writing | research | business | planning | education | "
            "creative | ops | data | life | general"
        ),
    )
    prism_parser.add_argument(
        "--techniques", default="", help="Comma-separated techniques (optional)"
    )
    prism_parser.add_argument("--count", type=int, default=12, help="How many ideas")
    prism_parser.add_argument("--seed", type=int, default=None, help="Deterministic seed")
    prism_parser.add_argument("--top", type=int, default=3, help="How many ideas to select")
    quantify_parser = subparsers.add_parser(
        "quantify",
        help="Deterministic money/percent/risk/date checks with provenance (JSON in)",
    )
    quantify_parser.add_argument(
        "--file", default="", help="Precision request JSON (budget/percentages/risks/schedule)"
    )
    quantify_parser.add_argument("--save", default="", help="Write the report Markdown here too")
    elicit_parser = subparsers.add_parser(
        "elicit",
        help="Material unknowns + prioritized questions + completion status (JSON in); "
        "with --question-budget/--session it runs the budgeted adaptive controller",
    )
    elicit_parser.add_argument(
        "--file", default="", help="Goal/knowns JSON (requirements + unknowns)"
    )
    elicit_parser.add_argument(
        "--interview", default="", help="Adapt a saved clarion interview instead"
    )
    elicit_parser.add_argument(
        "--asked", default="", help="Comma-separated question keys already asked"
    )
    elicit_parser.add_argument(
        "--batch-size", type=int, default=5, help="How many questions to surface at once"
    )
    elicit_parser.add_argument(
        "--verification-defined",
        action="store_true",
        help="Record that acceptance verification is defined",
    )
    elicit_parser.add_argument(
        "--question-budget",
        type=int,
        default=None,
        help="Maximum user-facing questions for the session (integer 1-100; controller mode)",
    )
    elicit_parser.add_argument(
        "--session",
        default="",
        help="Questioning session JSON: created if absent, resumed if present (controller mode)",
    )
    elicit_parser.add_argument(
        "--answers",
        default="",
        help="Answers JSON: list of {id|question, answer, confidence?} objects (controller mode)",
    )
    elicit_parser.add_argument(
        "--no-followups",
        action="store_true",
        help="Disable adaptive follow-up questions (controller mode)",
    )
    elicit_parser.add_argument(
        "--no-early-stop",
        action="store_true",
        help="Do not stop early even when the objective is covered (controller mode)",
    )
    investigate_parser = subparsers.add_parser(
        "investigate",
        help="Adaptive diagnostic case: probe, prioritize, report (case JSON in)",
    )
    investigate_parser.add_argument(
        "--file", default="", help="Investigation case JSON (saved, resumable state)"
    )
    investigate_parser.add_argument(
        "--action",
        default="report",
        choices=["status", "next", "report", "probe"],
        help="status | next | report | probe (default: report)",
    )
    investigate_parser.add_argument(
        "--probe-cmd", default="", help="Shell command to probe (with --action probe)"
    )
    investigate_parser.add_argument(
        "--probe-kind", default="command", help="Evidence kind recorded for the probe"
    )
    investigate_parser.add_argument(
        "--probe-ref", default="", help="Evidence reference recorded for the probe"
    )
    investigate_parser.add_argument(
        "--timeout", type=float, default=60.0, help="Probe timeout in seconds"
    )
    investigate_parser.add_argument(
        "--save", default="", help="Write the report Markdown here too"
    )

    args = _parse_args_safe(parser)

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
        "visualize": _cmd_visualize,
        "clarion": _cmd_clarion,
        "blueprint": _cmd_blueprint,
        "edict": _cmd_edict,
        "weave": _cmd_weave,
        "compass": _cmd_compass,
        "brainstorm": _cmd_prism,
        "prism": _cmd_prism,
        "quantify": _cmd_quantify,
        "elicit": _cmd_elicit,
        "investigate": _cmd_investigate,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        try:
            cmd_func(args)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — fail-open: CLI never tracebacks
            with contextlib.suppress(Exception):
                sys.stderr.write(f"school: {args.command} recovered from error: {exc}\n")
            sys.exit(0)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
