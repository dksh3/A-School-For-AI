"""Edict builder — ordered commands + always/never directives.

``build_edict(interview, blueprint=None) -> Edict`` turns the discovery
interview into an executable edict:

* **Commands** — ordered, bite-sized executable steps derived from the
  ``sequence`` and ``scope`` answers, plus setup (from ``resources``),
  verification checks (from ``success``), derisking work (from
  ``open_questions``) and a delivery step.  Every command carries a
  ``phase``, an ``estimated_minutes`` estimate and ``depends_on`` ids.
* **Directives** — always/never/prefer/avoid rules derived from the
  ``constraints``, ``style`` and ``edge_cases`` answers.

Return type: a small ``Edict`` dataclass with ``.commands`` / ``.directives``
that also unpacks like the classic tuple::

    edict = build_edict(interview, blueprint)
    commands, directives = build_edict(interview)   # tuple-style unpacking

Ordering is stable and deterministic: commands sort by (phase, kind rank,
creation order); directives by (kind rank, creation order).

Universal: phases and command phrasing adapt to ``Domain`` — an edict for a
novel, a research study or a move reads as naturally as one for a codebase.

FAIL-OPEN: every public boundary catches ``Exception`` and returns an empty
``Edict``. This module never raises.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.forge.blueprint import (
    AnswerRec,
    answer_texts,
    by_dimension,
    clean_item,
    collect_answers,
    default_phases,
    domain_label,
    is_exclusion,
    match_any,
    parse_minutes,
)
from core.forge.models import (
    Blueprint,
    Command,
    Directive,
    Domain,
    Interview,
    _safe_float,
    _safe_list,
    _safe_str,
)

__all__ = ["Edict", "build_edict"]

# kind → execution rank and default effort (minutes)
_KIND_RANK = {"setup": 0, "learn": 1, "step": 2, "check": 3, "ship": 4}
_KIND_MINUTES = {"setup": 15, "learn": 20, "step": 45, "check": 15, "ship": 30}

# directive kind → execution rank
_DIRECTIVE_RANK = {"always": 0, "never": 1, "prefer": 2, "avoid": 3}

_NEGATION_RE = re.compile(
    r"^(never|must not|do not|don't|dont|no|avoid|cannot|can't|can not|"
    r"shall not|should not|won't|will not|refrain from)\s+",
    re.I,
)
_NEGATION_WORDS = (
    "never", "must not", "do not", "don't", "dont", "avoid", "cannot",
    "can't", "can not", "shall not", "should not", "won't", "will not", "no ",
)
_POSITIVE_RE = re.compile(
    r"^(always|must|should|shall|ensure|make sure to|remember to|please)\s+",
    re.I,
)
_PREFER_RE = re.compile(r"^(prefer|favour|favor|keep|use|lean toward)\s+", re.I)

_STYLE_KIND = "prefer"
_EDGE_PREFIX = "address edge case"


@dataclass
class Edict:
    """The execution edict: ordered ``commands`` + governing ``directives``.

    Unpacks as ``commands, directives = build_edict(...)`` and serializes
    with ``to_dict()`` / ``to_markdown()``. Never raises.
    """

    commands: list[Command] = field(default_factory=list)
    directives: list[Directive] = field(default_factory=list)

    def __iter__(self) -> Any:
        yield self.commands
        yield self.directives

    def to_dict(self) -> dict[str, Any]:
        try:
            return {
                "commands": [c.to_dict() for c in self.commands],
                "directives": [d.to_dict() for d in self.directives],
            }
        except Exception:  # noqa: BLE001
            return {"commands": [], "directives": []}

    def to_markdown(self, title: str = "Edict") -> str:
        """Compact self-contained Markdown (the rich renderer lives in
        ``core.forge.render``). Never raises."""
        try:
            lines = [f"# {_safe_str(title)}", ""]
            lines.append("## Commands")
            for i, c in enumerate(self.commands, 1):
                deps = ", ".join(_safe_str(d) for d in c.depends_on) or "—"
                lines.append(
                    f"{i}. **[{_safe_str(c.id)}]** {_safe_str(c.title)}"
                    f" _(phase: {_safe_str(c.phase)}, ~{_safe_int(c.estimated_minutes)} min,"
                    f" depends on: {deps})_"
                )
            lines.append("")
            lines.append("## Directives")
            for d in self.directives:
                lines.append(f"- **{_safe_str(d.kind)}** — {_safe_str(d.rule)}")
            return "\n".join(lines) + "\n"
        except Exception:  # noqa: BLE001
            return "# Edict\n"


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:  # noqa: BLE001
        return default


def build_edict(
    interview: Interview,
    blueprint: Blueprint | None = None,
) -> Edict:
    """Build the execution ``Edict`` (commands + directives) from an interview.

    Commands come from ``sequence``/``scope`` answers (with setup from
    ``resources``, checks from ``success``, derisking from ``open_questions``
    and one delivery step).  Directives come from ``constraints``/``style``/
    ``edge_cases`` answers.  A supplied *blueprint* augments both surfaces.

    FAIL-OPEN: never raises; returns an empty ``Edict`` on catastrophic input.
    """
    try:
        return _build_edict_impl(interview, blueprint)
    except Exception:  # noqa: BLE001
        return Edict()


def _build_edict_impl(interview: Any, blueprint: Any) -> Edict:
    edict = Edict()
    try:
        dom = Domain.coerce(getattr(interview, "domain", Domain.GENERAL))
    except Exception:  # noqa: BLE001
        dom = Domain.GENERAL
    answers = collect_answers(interview)
    bydim = by_dimension(answers)

    seq = answer_texts(bydim, "sequence")
    scope = answer_texts(bydim, "scope")
    resources = answer_texts(bydim, "resources")
    success = answer_texts(bydim, "success")
    open_qs = answer_texts(bydim, "open_questions")
    for extra in _safe_list(getattr(interview, "open_questions", [])):
        try:
            t = clean_item(extra)
            if t:
                open_qs.append(t)
        except Exception:  # noqa: BLE001
            continue

    exact = _exact_phase_count(
        answer_texts(bydim, "constraints"),
        _safe_list(getattr(blueprint, "constraints", [])),
    )
    phases = _phase_plan(seq, dom, exact=exact)
    work_phases = _work_phases(phases)
    check_phase = _check_phase(phases)
    ship_phase = _ship_phase(phases)

    created: list[tuple[Command, str]] = []  # (command, creation group)

    def add(
        kind: str,
        title: str,
        detail: str,
        phase: str,
        minutes: int | None,
        group: str,
    ) -> None:
        try:
            n = sum(1 for c, g in created if g == group) + 1
            cmd = Command(
                id=f"{kind}-{n:02d}",
                title=_short(title, 90),
                detail=_short(detail, 240),
                kind=kind,
                phase=_safe_str(phase) or phases[0],
                estimated_minutes=max(1, minutes if minutes is not None
                                      else _KIND_MINUTES.get(kind, 45)),
                depends_on=[],
            )
            created.append((cmd, group))
        except Exception:  # noqa: BLE001
            return

    # setup: gather / prepare what the interview says exists
    for t in resources[:8]:
        add("setup", f"Prepare: {t}",
            f"Confirm the resource is ready before work starts: {t}",
            phases[0], parse_minutes(t, 15), "setup")

    # learn: close open questions early (they derisk the whole plan)
    for t in dedupe(open_qs)[:5]:
        add("learn", f"Resolve open question: {t}",
            f"Decide or de-risk before committing to work: {t}",
            phases[0], parse_minutes(t, 20), "learn")

    # steps: scope answers carry the work; sequence answers order it
    scope = [t for t in scope if not is_exclusion(t)]
    if scope:
        n = len(scope[:16])
        for i, t in enumerate(scope[:16]):
            phase = work_phases[min(i * len(work_phases) // max(1, n),
                                    len(work_phases) - 1)]
            add("step", t,
                f"Work item from the {domain_label(dom).lower()} interview: {t}",
                phase, parse_minutes(t, 45), "step")
    else:
        for i, t in enumerate(seq[:16]):
            phase = phases[i] if i < len(phases) else work_phases[-1]
            add("step", t, f"Sequenced step {i + 1}: {t}",
                phase, parse_minutes(t, 45), "step")

    # checks: verifiable gates from success answers
    for t in success[:10]:
        add("check", f"Verify: {t}",
            f"Pass/fail gate — done only when this holds: {t}",
            check_phase, parse_minutes(t, 15), "check")

    # ship: one explicit delivery step
    title = _safe_str(getattr(interview, "title", "")) or _safe_str(
        getattr(blueprint, "title", "")) or domain_label(dom) + " deliverable"
    goal = _safe_str(getattr(blueprint, "goal", ""))
    add("ship", f"Deliver: {_short(title, 70)}",
        f"Hand over the finished work ({_short(goal or title, 120)})."
        if goal else "Hand over the finished work and close the loop.",
        ship_phase, 30, "ship")

    # exact-count constraints: every planned phase must carry real commands,
    # otherwise the artifact renders fewer phases than the constraint demands
    if exact is not None:
        used = {_safe_str(c.phase) for c, _g in created}
        for p in phases:
            if p not in used:
                add("step", f"Execute: {_short(p, 70)}",
                    f"Carry the remaining work of phase {p}.",
                    p, 15, "step")
                used.add(p)

    _wire_dependencies(created)
    edict.commands = _ordered_commands(created, phases)
    edict.directives = _build_directives(bydim, blueprint)
    return edict


def dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for t in items or []:
        s = _safe_str(t)
        if s and s not in out:
            out.append(s)
    return out


def _short(text: str, limit: int = 90) -> str:
    s = _safe_str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 3].rsplit(" ", 1)[0] + "..."


_EXACT_PHASES_RE = re.compile(r"(?i)\bexactly\s+(\d+)\s+phases?\b")
_ANY_PHASES_RE = re.compile(r"(?i)\b(\d+)\s+phases?\b")


def _exact_phase_count(*groups: list[str]) -> int | None:
    """An explicit phase-count constraint (``exactly 3 phases``) → clamped 1..8.

    Returns ``None`` when no constraint text states a count, leaving the
    default plan untouched. FAIL-OPEN: never raises.
    """
    try:
        for group in groups:
            for raw in group:
                text = _safe_str(raw)
                if not text:
                    continue
                m = _EXACT_PHASES_RE.search(text) or _ANY_PHASES_RE.search(text)
                if m:
                    return max(1, min(8, int(m.group(1))))
    except Exception:  # noqa: BLE001
        return None
    return None


def _phase_plan(
    seq: list[str], dom: Domain, exact: int | None = None,
) -> list[str]:
    """Ordered phase names: sequence answers when present, else domain plan.

    With *exact* (an "exactly N phases" constraint) the plan honors that count
    exactly: names pad from the domain plan or trim to fit, and the
    Verify/Deliver safety append only runs when there is room for it.
    """
    try:
        names: list[str] = []
        if seq:
            for t in seq[:6]:
                name = _short(t.rstrip("."), 48)
                name = name[0].upper() + name[1:] if name else name
                if name and name not in names:
                    names.append(name)
        base = names or default_phases(dom)
        if exact is not None:
            for p in default_phases(dom):
                if len(base) >= exact:
                    break
                if p not in base:
                    base.append(p)
            while len(base) < exact:
                base.append(f"Phase {len(base) + 1}")
            return base[:exact] or ["Prepare"]
        if not any(match_any(p, ("verify", "test", "valid", "check", "review",
                                 "revis", "assess", "audit")) for p in base):
            base.append("Verify")
        if not any(match_any(p, ("ship", "deliver", "publish", "launch",
                                 "release", "finish", "complete")) for p in base):
            base.append("Deliver")
        return base[:8] or ["Prepare", "Execute", "Verify", "Deliver"]
    except Exception:  # noqa: BLE001
        return ["Prepare", "Execute", "Verify", "Deliver"]


def _work_phases(phases: list[str]) -> list[str]:
    work = [p for p in phases if not _is_check_phase(p) and not _is_ship_phase(p)]
    return work or phases[:1] or ["Prepare"]


def _is_check_phase(name: str) -> bool:
    return match_any(name, ("verify", "test", "valid", "check", "review",
                            "revis", "assess", "audit"))


def _is_ship_phase(name: str) -> bool:
    return match_any(name, ("ship", "deliver", "publish", "launch", "release",
                            "finish", "complete"))


def _check_phase(phases: list[str]) -> str:
    for p in phases:
        if _is_check_phase(p):
            return p
    return phases[-2] if len(phases) >= 2 else phases[-1]


def _ship_phase(phases: list[str]) -> str:
    for p in reversed(phases):
        if _is_ship_phase(p):
            return p
    return phases[-1]


def _wire_dependencies(created: list[tuple[Command, str]]) -> None:
    """Give every command resolvable ``depends_on`` ids. Never raises."""
    try:
        groups: dict[str, list[Command]] = {}
        for cmd, group in created:
            groups.setdefault(group, []).append(cmd)
        setups = groups.get("setup", [])
        learns = groups.get("learn", [])
        steps = groups.get("step", [])
        checks = groups.get("check", [])
        ships = groups.get("ship", [])

        for prev, cur in zip(setups, setups[1:], strict=False):
            cur.depends_on = [prev.id]
        for prev, cur in zip(learns, learns[1:], strict=False):
            cur.depends_on = [prev.id]
        if learns and setups:
            learns[0].depends_on = [setups[-1].id]

        for prev, cur in zip(steps, steps[1:], strict=False):
            cur.depends_on = [prev.id]
        if steps and setups:
            steps[0].depends_on = [setups[-1].id]

        for i, cur in enumerate(checks):
            deps: list[str] = []
            if i > 0:
                deps.append(checks[i - 1].id)
            elif steps:
                deps.append(steps[-1].id)
            elif setups:
                deps.append(setups[-1].id)
            cur.depends_on = deps

        for ship in ships:
            ship.depends_on = [c.id for c in checks[:10]] or (
                [steps[-1].id] if steps else ([setups[-1].id] if setups else [])
            )
    except Exception:  # noqa: BLE001
        return


def _ordered_commands(
    created: list[tuple[Command, str]],
    phases: list[str],
) -> list[Command]:
    """Stable execution order: (phase, kind rank, creation order)."""
    try:
        pidx = {p: i for i, p in enumerate(phases)}
        order = {id(cmd): i for i, (cmd, _) in enumerate(created)}
        cmds = [cmd for cmd, _ in created]
        cmds.sort(key=lambda c: (
            pidx.get(_safe_str(c.phase), len(phases)),
            _KIND_RANK.get(_safe_str(c.kind), 2),
            order.get(id(c), 0),
        ))
        return cmds
    except Exception:  # noqa: BLE001
        return [cmd for cmd, _ in created]


def _build_directives(bydim: dict[str, list[AnswerRec]], blueprint: Any) -> list[Directive]:
    """always/never/prefer/avoid rules from constraints/style/edge_cases."""
    out: list[tuple[Directive, int, int]] = []
    counter = {"always": 0, "never": 0, "prefer": 0, "avoid": 0}
    seen_rules: set[str] = set()

    def add(rule: str, kind: str, rationale: str, strength: float) -> None:
        try:
            rule = _safe_str(rule)
            if not rule:
                return
            key = f"{kind}|{rule.lower()}"
            if key in seen_rules:  # blueprint + interview can overlap
                return
            seen_rules.add(key)
            counter[kind] = counter.get(kind, 0) + 1
            out.append((
                Directive(
                    id=f"{kind}-{counter[kind]:02d}",
                    rule=rule,
                    kind=kind,
                    rationale=_short(rationale, 160),
                    strength=max(0.0, min(1.0, _safe_float(strength, 1.0))),
                ),
                _DIRECTIVE_RANK.get(kind, 0),
                len(out),
            ))
        except Exception:  # noqa: BLE001
            return

    def add_constraint(text: str, rationale: str, strength: float) -> None:
        """Classify one constraint as a never/always rule. Never raises."""
        try:
            t = _safe_str(text)
            if not t:
                return
            if match_any(t, _NEGATION_WORDS):
                add(_NEGATION_RE.sub("", t) or t, "never", rationale, strength)
            else:
                add(_POSITIVE_RE.sub("", t) or t, "always", rationale, strength)
        except Exception:  # noqa: BLE001
            return

    for a in bydim.get("constraints", [])[:20]:
        add_constraint(_safe_str(a.text),
                       f"Constraint ({_safe_str(a.question_id) or 'interview'}).",
                       a.confidence)

    for a in bydim.get("style", [])[:12]:
        text = _safe_str(a.text)
        rule = _PREFER_RE.sub("", text)
        add(rule or text, _STYLE_KIND,
            f"Style preference ({_safe_str(a.question_id) or 'interview'}).", a.confidence)

    for a in bydim.get("edge_cases", [])[:12]:
        text = _safe_str(a.text)
        add(f"{_EDGE_PREFIX}: {text}", "always",
            f"Edge case ({_safe_str(a.question_id) or 'interview'}).", a.confidence)

    # a supplied blueprint adds its constraints / non-goals as guardrails
    for text in _safe_list(getattr(blueprint, "constraints", []))[:10]:
        add_constraint(clean_item(text), "From the blueprint.", 1.0)
    for text in _safe_list(getattr(blueprint, "non_goals", []))[:10]:
        t = clean_item(text)
        if t:
            add(t, "avoid", "Non-goal from the blueprint.", 0.9)

    out.sort(key=lambda row: (row[1], row[2]))
    return [d for d, _, _ in out]
