"""S7: school_session — manage session lifecycle, summaries, and exports."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SESSION_FILE = "sessions.json"


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
        return data if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _save(worktree: str, sessions: list[dict[str, Any]]) -> None:
    path = _session_path(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sessions, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def session(
    worktree: str,
    action: str,
    session_id: str = "",
    focus: str = "",
) -> SessionResult:
    """Manage sessions: create / resume / summarize / export / list."""
    if os.environ.get("SCHOOL_SESSION", "") == "0":
        return SessionResult(ok=True, action=action)

    valid = {"create", "resume", "summarize", "export", "list"}
    if action not in valid:
        return SessionResult(ok=False, action=action, error=f"unknown action: {action}")

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
            if s.get("id") == session_id:
                s["state"] = "active"
                _save(worktree, sessions)
                return SessionResult(
                    ok=True, action=action, session_id=session_id, focus=s.get("focus", "")
                )
        return SessionResult(
            ok=False, action=action, session_id=session_id,
            error="session not found",
        )

    if action == "summarize":
        for s in sessions:
            if s.get("id") == session_id:
                notes = s.get("notes", [])
                summary = f"Session {session_id}: focus={s.get('focus', '')}, {len(notes)} notes"
                return SessionResult(
                    ok=True, action=action, session_id=session_id, summary=summary,
                )
        return SessionResult(
            ok=False, action=action, session_id=session_id,
            error="session not found",
        )

    if action == "export":
        for s in sessions:
            if s.get("id") == session_id:
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


__all__ = ["SessionResult", "session"]
