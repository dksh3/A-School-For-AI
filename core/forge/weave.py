"""Weave builder — formations: phases, dependencies, lanes, critical path.

``build_weave(interview, commands=None, blueprint=None) -> Formation`` turns
the edict's commands into an execution formation showing real structure:

* **phases**   — commands grouped by ``command.phase``, each with a milestone
* **dependencies** — ``(before, after)`` pairs from ``command.depends_on``
* **lanes**    — parallel-lane grouping (dependency-depth waves that can run
  concurrently)
* **critical_path** — the longest dependency chain by cumulative effort
* **kind**     — ``CRITICAL_PATH`` when a real chain exists, else ``PHASES``

Universal: groupings work from any domain's commands — a chapter-by-chapter
writing plan forms the same shape as a deployment plan.

FAIL-OPEN: every public boundary catches ``Exception`` and returns an empty
``Formation``. This module never raises.
"""

from __future__ import annotations

from typing import Any

from core.forge.blueprint import default_phases
from core.forge.models import (
    Blueprint,
    Command,
    Domain,
    Formation,
    FormationKind,
    Interview,
    _safe_float,
    _safe_int,
    _safe_list,
    _safe_str,
)

__all__ = ["build_weave"]

_MAX_COMMANDS = 200


def build_weave(
    interview: Interview,
    commands: list[Command] | None = None,
    blueprint: Blueprint | None = None,
) -> Formation:
    """Build the execution ``Formation`` from commands + interview context.

    When *commands* is omitted (or empty) the edict is consulted to derive
    them, so the weave is always meaningful.  Accepts ``list[Command]``, an
    ``Edict``, or ``list[dict]`` command payloads.

    FAIL-OPEN: never raises; returns a safe (possibly empty) Formation.
    """
    try:
        return _build_weave_impl(interview, commands, blueprint)
    except Exception:  # noqa: BLE001
        return Formation()


def _coerce_commands(raw: Any) -> list[Command]:
    """Accept Edict / list[Command] / list[dict] / junk. Never raises."""
    out: list[Command] = []
    try:
        holder = getattr(raw, "commands", None)
        items = _safe_list(holder if holder is not None else raw)
        for item in items[:_MAX_COMMANDS]:
            try:
                if isinstance(item, Command):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(Command.from_dict(item))
                else:
                    cmd = Command(
                        id=_safe_str(getattr(item, "id", "")),
                        title=_safe_str(getattr(item, "title", "")),
                        detail=_safe_str(getattr(item, "detail", "")),
                        kind=_safe_str(getattr(item, "kind", "step"), "step"),
                        phase=_safe_str(getattr(item, "phase", "")),
                        estimated_minutes=max(
                            0, _safe_int(getattr(item, "estimated_minutes", 0))
                        ),
                        depends_on=[
                            _safe_str(d)
                            for d in _safe_list(getattr(item, "depends_on", []))
                        ],
                    )
                    if cmd.id or cmd.title:
                        out.append(cmd)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return out
    return out


def _minutes(cmd: Command) -> float:
    try:
        v = _safe_float(cmd.estimated_minutes, 0.0)
        return v if v > 0 else 1.0
    except Exception:  # noqa: BLE001
        return 1.0


def _build_weave_impl(
    interview: Any,
    commands: Any,
    blueprint: Any,
) -> Formation:
    formation = Formation()
    cmds = _coerce_commands(commands)
    if not cmds:
        try:
            from core.forge.edict import build_edict

            cmds = _coerce_commands(build_edict(interview, blueprint))
        except Exception:  # noqa: BLE001
            cmds = []
    if not cmds:
        return formation

    known: dict[str, Command] = {}
    for c in cmds:
        try:
            cid = _safe_str(c.id) or _safe_str(c.title)
            if cid and cid not in known:
                c.id = cid
                known[cid] = c
        except Exception:  # noqa: BLE001
            continue
    order = [c.id for c in cmds if c.id in known]

    # -- dependencies (resolvable, de-duplicated, order-preserving) -------
    deps_by_cmd: dict[str, list[str]] = {}
    pairs: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for c in cmds:
        cid = _safe_str(c.id)
        for d in _safe_list(getattr(c, "depends_on", [])):
            try:
                dep = _safe_str(d)
                if dep in known and dep != cid and (dep, cid) not in seen_pairs:
                    seen_pairs.add((dep, cid))
                    pairs.append((dep, cid))
                    deps_by_cmd.setdefault(cid, []).append(dep)
            except Exception:  # noqa: BLE001
                continue
    formation.dependencies = pairs

    # -- phases: grouped with milestones ---------------------------------
    phase_names: list[str] = []
    for c in cmds:
        name = _safe_str(c.phase) or "General"
        if name not in phase_names:
            phase_names.append(name)
    if not phase_names:
        try:
            dom = Domain.coerce(getattr(interview, "domain", Domain.GENERAL))
        except Exception:  # noqa: BLE001
            dom = Domain.GENERAL
        phase_names = default_phases(dom)

    for i, name in enumerate(phase_names):
        members = [c for c in cmds if (_safe_str(c.phase) or "General") == name]
        checks = [c for c in members if _safe_str(c.kind) == "check"]
        if checks:
            criterion = _safe_str(checks[0].title).removeprefix("Verify: ")
            milestone = criterion or _safe_str(checks[0].title)
        else:
            milestone = (f"Exit when all {len(members)} command(s) are "
                         f"complete and self-verified")
        try:
            formation.phases.append({
                "name": name,
                "index": i,
                "commands": [_safe_str(c.id) for c in members],
                "command_titles": [_safe_str(c.title) for c in members],
                "estimated_minutes": int(sum(_minutes(c) for c in members)),
                "milestone": _short(milestone, 120),
            })
        except Exception:  # noqa: BLE001
            continue

    # -- lanes: dependency-depth waves that can run in parallel ----------
    levels: dict[str, int] = {}

    def level_of(cid: str, stack: set[str]) -> int:
        if cid in levels:
            return levels[cid]
        if cid in stack:
            return 0
        stack.add(cid)
        lv = 0
        for dep in deps_by_cmd.get(cid, []):
            if dep in known:
                lv = max(lv, level_of(dep, stack) + 1)
        stack.discard(cid)
        levels[cid] = lv
        return lv

    try:
        for cid in order:
            level_of(cid, set())
    except Exception:  # noqa: BLE001
        for cid in order:
            levels[cid] = 0

    by_level: dict[int, list[Command]] = {}
    for cid in order:
        lv = levels.get(cid, 0)
        by_level.setdefault(lv, []).append(known[cid])
    for lv in sorted(by_level):
        members = by_level[lv]
        try:
            formation.lanes.append({
                "name": f"Lane {lv + 1}",
                "level": lv,
                "commands": [_safe_str(c.id) for c in members],
                "command_titles": [_safe_str(c.title) for c in members],
                "estimated_minutes": int(sum(_minutes(c) for c in members)),
                "can_start": "immediately" if lv == 0 else f"when Lane {lv} completes",
            })
        except Exception:  # noqa: BLE001
            continue

    # -- critical path: longest chain by cumulative effort ---------------
    dependents: dict[str, list[str]] = {cid: [] for cid in order}
    for dep, cid in pairs:
        try:
            if dep in dependents and cid in known and cid not in dependents[dep]:
                dependents[dep].append(cid)
        except Exception:  # noqa: BLE001
            continue

    best_total: dict[str, float] = {}
    best_next: dict[str, str | None] = {}

    def best_from(cid: str, stack: set[str]) -> float:
        if cid in best_total:
            return best_total[cid]
        if cid in stack:
            return 0.0
        stack.add(cid)
        top = 0.0
        nxt: str | None = None
        for child in dependents.get(cid, []):
            v = best_from(child, stack)
            if v > top:
                top = v
                nxt = child
        stack.discard(cid)
        total = _minutes(known[cid]) + top
        best_total[cid] = total
        best_next[cid] = nxt
        return total

    try:
        for cid in order:
            best_from(cid, set())
        start = None
        best = -1.0
        for cid in order:
            total = best_total.get(cid, 0.0)
            if total > best:
                best = total
                start = cid
        path: list[str] = []
        cur = start
        guard = 0
        while cur is not None and guard <= len(order) + 1:
            path.append(cur)
            cur = best_next.get(cur)
            guard += 1
        formation.critical_path = path
    except Exception:  # noqa: BLE001
        formation.critical_path = []

    # -- richest kind ----------------------------------------------------
    if len(formation.critical_path) >= 2 and formation.dependencies:
        formation.kind = FormationKind.CRITICAL_PATH
    else:
        formation.kind = FormationKind.PHASES
    return formation


def _short(text: str, limit: int = 120) -> str:
    s = _safe_str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 3].rsplit(" ", 1)[0] + "..."
