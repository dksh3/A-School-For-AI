"""S7: school_session — manage session lifecycle, summaries, and exports."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.agent.observer import safe_str

SESSION_FILE = "sessions.json"
ACTIONS = frozenset({"create", "resume", "summarize", "export", "list"})


@dataclass
class SessionResult:
    ok: bool = True
    action: str = ""
    session_id: str = ""
    focus: str = ""
    summary: str = ""
    sessions: list[dict[str, Any]] = field(default_factory=list)
    data: str = ""
    error: str = ""


def _session_path(worktree: str) -> Path:
    return Path(worktree) / ".school" / "agent" / SESSION_FILE


def _load(worktree: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(_session_path(worktree).read_text(encoding="utf-8"))
        return [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []
    except Exception:
        return []


def _save(worktree: str, sessions: list[dict[str, Any]]) -> None:
    path = _session_path(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sessions, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _count_notes(entry: dict[str, Any]) -> int:
    try:
        return len(entry.get("notes", []))
    except Exception:
        return 0


def _apply(worktree: str, action: str, session_id: str, focus: str) -> SessionResult:
    sessions = _load(worktree)

    if action == "create":
        sid = session_id or f"s{len(sessions) + 1}"
        entry = {
            "id": sid,
            "focus": focus,
            "state": "active",
            "created_ms": int(time.time() * 1000),
            "notes": [],
        }
        sessions.append(entry)
        _save(worktree, sessions)
        return SessionResult(ok=True, action=action, session_id=sid, focus=focus)

    if action == "list":
        return SessionResult(ok=True, action=action, sessions=sessions)

    if action == "resume":
        for s in sessions:
            if safe_str(s.get("id", "")) == session_id:
                s["state"] = "active"
                _save(worktree, sessions)
                return SessionResult(
                    ok=True, action=action, session_id=session_id,
                    focus=safe_str(s.get("focus", "")),
                )
        return SessionResult(
            ok=False, action=action, session_id=session_id,
            error="session not found",
        )

    if action == "summarize":
        for s in sessions:
            if safe_str(s.get("id", "")) == session_id:
                n = _count_notes(s)
                summary = (
                    f"Session {session_id}: focus={safe_str(s.get('focus', ''))}, {n} notes"
                )
                return SessionResult(
                    ok=True, action=action, session_id=session_id, summary=summary,
                )
        return SessionResult(
            ok=False, action=action, session_id=session_id,
            error="session not found",
        )

    if action == "export":
        for s in sessions:
            if safe_str(s.get("id", "")) == session_id:
                return SessionResult(
                    ok=True,
                    action=action,
                    session_id=session_id,
                    data=json.dumps(s, indent=1, ensure_ascii=False),
                )
        return SessionResult(
            ok=False, action=action, session_id=session_id,
            error="session not found",
        )

    return SessionResult(ok=False, action=action, error="unreachable")


def session(
    worktree: str,
    action: str,
    session_id: str = "",
    focus: str = "",
) -> SessionResult:
    """Manage sessions: create / resume / summarize / export / list."""
    action_s = safe_str(action)
    session_id_s = safe_str(session_id)
    focus_s = safe_str(focus)
    if os.environ.get("SCHOOL_SESSION", "") == "0":
        return SessionResult(ok=True, action=action_s)

    if action_s not in ACTIONS:
        return SessionResult(ok=False, action=action_s, error=f"unknown action: {action_s}")

    try:
        return _apply(worktree, action_s, session_id_s, focus_s)
    except Exception as exc:
        return SessionResult(
            ok=False,
            action=action_s,
            session_id=session_id_s,
            error=safe_str(exc, 300) or type(exc).__name__,
        )


__all__ = ["SessionResult", "session"]
