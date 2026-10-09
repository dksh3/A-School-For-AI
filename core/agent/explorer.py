"""S7: school_explore — explore codebases and extract structural knowledge."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from core.agent.observer import safe_str


@dataclass
class ExploreResult:
    ok: bool = True
    target: str = ""
    structure: str = ""
    patterns: list[str] = field(default_factory=list)
    conventions: list[str] = field(default_factory=list)
    error: str = ""


def explore(
    worktree: str,
    target: str,
    depth: str = "file",
    focus: str = "structure",
) -> ExploreResult:
    """Explore a path and extract structure, patterns, conventions."""
    if os.environ.get("SCHOOL_EXPLORE", "") == "0":
        return ExploreResult(ok=True, target=safe_str(target))

    if not isinstance(target, str) or not target:
        return ExploreResult(ok=False, error="target must be a non-empty string")

    try:
        root = Path(worktree) / target if not Path(target).is_absolute() else Path(target)
        if not root.exists():
            return ExploreResult(ok=False, target=target, error=f"not found: {target}")

        files = []
        if root.is_file():
            files = [root]
        else:
            try:
                files = sorted(p for p in root.rglob("*") if p.is_file())[:100]
            except OSError:
                return ExploreResult(ok=False, target=target, error="cannot read directory")

        exts: dict[str, int] = {}
        for f in files:
            ext = f.suffix or "(none)"
            exts[ext] = exts.get(ext, 0) + 1

        structure = (
            f"{len(files)} files, extensions: "
            f"{dict(sorted(exts.items(), key=lambda x: -x[1]))}"
        )
        patterns = [f"uses {ext} x{n}" for ext, n in sorted(exts.items(), key=lambda x: -x[1])[:5]]
        conventions = []
        if any(f.suffix == ".py" for f in files):
            conventions.append("Python project")
        if any(f.suffix in (".ts", ".tsx") for f in files):
            conventions.append("TypeScript project")
        if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
            conventions.append("Python packaging")

        return ExploreResult(
            ok=True,
            target=target,
            structure=structure,
            patterns=patterns,
            conventions=conventions,
        )
    except Exception as exc:
        return ExploreResult(
            ok=False, target=safe_str(target), error=safe_str(exc, 300) or type(exc).__name__
        )


__all__ = ["ExploreResult", "explore"]
