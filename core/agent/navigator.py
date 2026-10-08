"""S7: school_navigate — read, list, search, and map project files."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


def navigate(
    worktree: str,
    action: str,
    path: str = "",
    pattern: str = "",
    depth: int = 3,
) -> NavigateResult:
    """Navigate project files: read / list / search / map."""
    if os.environ.get("SCHOOL_NAVIGATE", "") == "0":
        return NavigateResult(ok=True, action=action)

    valid = {"read", "list", "search", "map"}
    if action not in valid:
        return NavigateResult(ok=False, action=action, error=f"unknown action: {action}")

    target = (
        Path(worktree) / path
        if path and not Path(path).is_absolute()
        else Path(path or worktree)
    )

    if action == "read":
        if not target.is_file():
            return NavigateResult(ok=False, action=action, path=path, error="not a file")
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return NavigateResult(ok=False, action=action, path=path, error=str(exc))
        return NavigateResult(ok=True, action=action, path=path, content=content[:8000])

    if action == "list":
        if not target.is_dir():
            return NavigateResult(ok=False, action=action, path=path, error="not a directory")
        try:
            entries = sorted(str(p.relative_to(target)) for p in target.iterdir())[:200]
        except OSError as exc:
            return NavigateResult(ok=False, action=action, path=path, error=str(exc))
        return NavigateResult(ok=True, action=action, path=path, entries=entries)

    if action == "search":
        if not target.is_dir():
            return NavigateResult(ok=False, action=action, path=path, error="not a directory")
        try:
            rx = re.compile(pattern, re.IGNORECASE) if pattern else re.compile(".", re.IGNORECASE)
        except re.error as exc:
            return NavigateResult(ok=False, action=action, error=f"bad pattern: {exc}")
        matches: list[dict[str, Any]] = []
        for f in sorted(target.rglob("*")):
            if not f.is_file() or len(matches) >= 50:
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
                        if len(matches) >= 50:
                            break
            except OSError:
                continue
        return NavigateResult(ok=True, action=action, path=path, matches=matches)

    # map
    root = target if target.is_dir() else Path(worktree)
    lines: list[str] = []

    def _walk(p: Path, prefix: str = "", lvl: int = 0) -> None:
        if lvl > depth:
            return
        try:
            children = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))[:20]
        except OSError:
            return
        for child in children:
            lines.append(f"{prefix}{child.name}{'/' if child.is_dir() else ''}")
            if child.is_dir() and lvl < depth:
                _walk(child, prefix + "  ", lvl + 1)

    _walk(root)
    return NavigateResult(ok=True, action=action, path=str(path), tree="\n".join(lines[:200]))


__all__ = ["NavigateResult", "navigate"]
