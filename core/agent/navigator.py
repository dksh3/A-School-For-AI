"""S7: school_navigate — read, list, search, and map project files."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.agent.observer import safe_str

ACTIONS = frozenset({"read", "list", "search", "map"})
_MAX_CONTENT = 8000
_MAX_ENTRIES = 200
_MAX_MATCHES = 50


@dataclass
class NavigateResult:
    ok: bool = True
    action: str = ""
    path: str = ""
    content: str = ""
    entries: list[str] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)
    tree: str = ""
    error: str = ""


def _resolve_target(worktree: Any, path: Any) -> Path:
    """Resolve (worktree, path) into a target Path; raises on hostile input."""
    if path:
        p = Path(path)
        return Path(worktree) / p if not p.is_absolute() else p
    return Path(worktree)


def navigate(
    worktree: str,
    action: str,
    path: str = "",
    pattern: str = "",
    depth: int = 3,
) -> NavigateResult:
    """Navigate project files: read / list / search / map."""
    action_s = safe_str(action)
    path_s = safe_str(path)
    if os.environ.get("SCHOOL_NAVIGATE", "") == "0":
        return NavigateResult(ok=True, action=action_s)

    if action_s not in ACTIONS:
        return NavigateResult(ok=False, action=action_s, error=f"unknown action: {action_s}")

    try:
        return _dispatch(worktree, action_s, path, path_s, pattern, depth)
    except Exception as exc:
        return NavigateResult(
            ok=False, action=action_s, path=path_s,
            error=safe_str(exc, 300) or type(exc).__name__,
        )


def _dispatch(
    worktree: Any,
    action: str,
    path: Any,
    path_s: str,
    pattern: Any,
    depth: Any,
) -> NavigateResult:
    try:
        target = _resolve_target(worktree, path)
    except Exception as exc:
        return NavigateResult(
            ok=False, action=action, path=path_s, error=f"bad path: {safe_str(exc, 200)}"
        )

    if action == "read":
        try:
            is_file = target.is_file()
        except Exception:
            is_file = False
        if not is_file:
            return NavigateResult(ok=False, action=action, path=path_s, error="not a file")
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return NavigateResult(
                ok=False, action=action, path=path_s,
                error=safe_str(exc, 200) or type(exc).__name__,
            )
        return NavigateResult(
            ok=True, action=action, path=path_s, content=content[:_MAX_CONTENT]
        )

    if action == "list":
        try:
            is_dir = target.is_dir()
        except Exception:
            is_dir = False
        if not is_dir:
            return NavigateResult(
                ok=False, action=action, path=path_s, error="not a directory"
            )
        try:
            entries = sorted(str(p.relative_to(target)) for p in target.iterdir())
        except Exception as exc:
            return NavigateResult(
                ok=False, action=action, path=path_s,
                error=safe_str(exc, 200) or type(exc).__name__,
            )
        return NavigateResult(
            ok=True, action=action, path=path_s, entries=entries[:_MAX_ENTRIES]
        )

    if action == "search":
        try:
            is_dir = target.is_dir()
        except Exception:
            is_dir = False
        if not is_dir:
            return NavigateResult(
                ok=False, action=action, path=path_s, error="not a directory"
            )
        try:
            if isinstance(pattern, str) and pattern:
                rx = re.compile(pattern, re.IGNORECASE)
            else:
                rx = re.compile(".", re.IGNORECASE)
        except Exception as exc:
            return NavigateResult(
                ok=False, action=action, error=f"bad pattern: {safe_str(exc, 120)}"
            )
        matches: list[dict[str, Any]] = []
        try:
            paths = sorted(target.rglob("*"))
        except Exception as exc:
            return NavigateResult(
                ok=False, action=action, path=path_s,
                error=safe_str(exc, 200) or type(exc).__name__,
            )
        for f in paths:
            if not f.is_file() or len(matches) >= _MAX_MATCHES:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(text.splitlines(), 1):
                    if rx.search(line):
                        matches.append({
                            "file": str(f.relative_to(target)),
                            "line": i,
                            "text": line[:200],
                        })
                        if len(matches) >= _MAX_MATCHES:
                            break
            except Exception:
                continue
        return NavigateResult(ok=True, action=action, path=path_s, matches=matches)

    # map
    try:
        max_depth = int(depth)
    except Exception:
        max_depth = 3
    try:
        root = target if target.is_dir() else Path(worktree)
    except Exception:
        root = target
    lines: list[str] = []

    def _walk(p: Path, prefix: str = "", lvl: int = 0) -> None:
        if lvl > max_depth:
            return
        try:
            children = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))[:20]
        except OSError:
            return
        for child in children:
            lines.append(f"{prefix}{child.name}{'/' if child.is_dir() else ''}")
            if child.is_dir() and lvl < max_depth:
                _walk(child, prefix + "  ", lvl + 1)

    _walk(root)
    return NavigateResult(
        ok=True, action=action, path=path_s, tree="\n".join(lines[:_MAX_ENTRIES])
    )


__all__ = ["NavigateResult", "navigate"]
