"""Plugin install plans + per-CLI config. Fail-open."""

from __future__ import annotations

from .adapters import ADAPTERS, emit_plugin

CLI_CLIENTS: list[str] = sorted(ADAPTERS)


def config_for(cli: str) -> dict:
    """Config/registration payload for a CLI. FAIL-OPEN: never raises."""
    try:
        payload = emit_plugin(cli)
        ext = {
            "opencode": "ts",
            "claude_code": "json",
            "codex": "toml",
            "cursor": "json",
            "generic": "md",
        }.get(cli, "txt")
        return {
            "cli": cli,
            "filename": f"school.{ext}",
            "format": ext,
            "payload": payload,
            "bytes": len(payload),
        }
    except Exception as exc:  # noqa: BLE001
        return {"cli": cli, "error": str(exc)[:120]}


def install_plan() -> dict:
    """A fail-open install plan for every supported CLI at once."""
    try:
        return {
            "supported": CLI_CLIENTS,
            "default": "opencode",
            "steps": [
                "Emit the plugin payload for your CLI (config_for).",
                "Write it to the CLI's plugin/MCP location.",
                "Ensure `python -m school_mcp.server` is reachable (MCP path).",
                "Restart the agent; School tools appear as school_*.",
            ],
            "configs": {cli: config_for(cli) for cli in CLI_CLIENTS},
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:120], "supported": CLI_CLIENTS}


def verify(cli: str) -> dict:
    """Verify a CLI adapter emits a non-empty payload. Fail-open."""
    try:
        cfg = config_for(cli)
        ok = bool(cfg.get("payload")) and "error" not in cfg
        return {"cli": cli, "ok": ok, "bytes": cfg.get("bytes", 0)}
    except Exception as exc:  # noqa: BLE001
        return {"cli": cli, "ok": False, "error": str(exc)[:120]}
