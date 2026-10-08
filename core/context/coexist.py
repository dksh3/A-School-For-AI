# core/context/coexist.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.context.store import context_dir

STATE_FILE = "coexistence.json"
DCP_TOKEN = "@tarquinen/opencode-dcp"
MAX_READ_BYTES = 1_048_576
OFFER_TEXT = (
    "School can now handle compression — with restore, budgets, and status. "
    "Keep DCP, or switch? Run `school context switch` or "
    "`school context keep` to decide."
)

_DCP_CACHE: dict[tuple[str, str], bool] = {}


def ctx_enabled() -> bool:
    return os.environ.get("SCHOOL_CTX", "") != "0"


def state_path(worktree: str) -> Path:
    return context_dir(worktree) / STATE_FILE


def load_state(worktree: str) -> dict[str, Any]:
    try:
        data = json.loads(state_path(worktree).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            decision = str(data.get("decision", "") or "")
            return {
                "version": 1,
                "dcp_seen": bool(data.get("dcp_seen")),
                "offer_shown": bool(data.get("offer_shown")),
                "decision": decision if decision in {"switch", "keep"} else "",
            }
    except (OSError, ValueError, TypeError):
        pass
    return {"version": 1, "dcp_seen": False, "offer_shown": False, "decision": ""}


def save_state(worktree: str, patch: dict[str, Any]) -> dict[str, Any]:
    try:
        state = load_state(worktree)
        merged = {**state, **{k: v for k, v in patch.items() if k in state}}
        if merged.get("decision") not in {"", "switch", "keep"}:
            merged["decision"] = state["decision"]
        path = state_path(worktree)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=1), encoding="utf-8")
        return merged
    except OSError:
        return load_state(worktree)


def _read_bounded(path: Path) -> str:
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_READ_BYTES)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")

def detect_dcp(worktree: str, home: Path | None = None) -> bool:
    home_path = Path.home() if home is None else Path(home)
    root = Path(worktree)
    configs = [
        root / "opencode.json",
        root / "opencode.jsonc",
        root / ".opencode" / "opencode.json",
        root / ".opencode" / "opencode.jsonc",
        home_path / ".config" / "opencode" / "opencode.json",
        home_path / ".config" / "opencode" / "opencode.jsonc",
    ]
    for path in configs:
        if DCP_TOKEN in _read_bounded(path):
            return True
    dirs = [
        root / ".opencode" / "plugins",
        root / "plugins",
        home_path / ".config" / "opencode" / "plugins",
    ]
    for folder in dirs:
        try:
            names = sorted(p.name for p in folder.iterdir() if p.is_file())[:50]
        except OSError:
            continue
        if any("dcp" in name.lower() for name in names):
            return True
        for name in names:
            if name.endswith((".ts", ".js", ".mjs")) and DCP_TOKEN in _read_bounded(folder / name):
                return True
    return False


def detect_dcp_cached(worktree: str, home: Path | None = None) -> bool:
    key = (str(Path(worktree)), str(home) if home is not None else "")
    if key not in _DCP_CACHE:
        _DCP_CACHE[key] = detect_dcp(key[0], home=home)
    return _DCP_CACHE[key]


def clear_cache() -> None:
    _DCP_CACHE.clear()


def view_mode(worktree: str, dcp_hint: bool = False, home: Path | None = None) -> str:
    if not ctx_enabled():
        return "off"
    if os.environ.get("SCHOOL_COMPRESS", "") == "0":
        return "off"
    state = load_state(worktree)
    decision = state.get("decision", "")
    if decision == "switch":
        return "school"
    if decision == "keep":
        return "dcp"
    if dcp_hint or detect_dcp_cached(worktree, home=home):
        return "dcp"
    return "school"


__all__ = [
    "DCP_TOKEN",
    "MAX_READ_BYTES",
    "OFFER_TEXT",
    "STATE_FILE",
    "clear_cache",
    "ctx_enabled",
    "detect_dcp",
    "detect_dcp_cached",
    "load_state",
    "save_state",
    "state_path",
    "view_mode",
]
