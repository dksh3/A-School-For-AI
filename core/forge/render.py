"""Forge renderer — Markdown + School visuals for every Forge artifact.

Public surface:

* ``render_artifact(kind, obj, interview=None, width=60) -> Artifact``
  dispatches on ``kind`` ("blueprint" | "edict" | "weave" | "compass" |
  "bundle") and returns a rendered ``Artifact``: clean GitHub Markdown body
  plus a School visual (text-art via ``core.context.visuals``).
* ``render_bundle(interview, width=60) -> dict[str, Artifact]`` builds all
  five artifacts at once (blueprint/edict/weave/compass + a ``bundle`` index).
* ``to_markdown_blueprint / to_markdown_edict / to_markdown_weave /
  to_markdown_compass / to_markdown_bundle`` render one artifact to Markdown.

Universal: headings carry the domain label ("Writing Blueprint", "Research
Blueprint", …) and never assume coding.

FAIL-OPEN: every public boundary catches ``Exception`` and returns a
graceful ``Artifact`` (or per-renderer safe text). This module never raises.
"""

from __future__ import annotations

from typing import Any

from core.context.visual_dispatch import render_visual
from core.context.visuals import (
    render_bar_chart,
    render_donut,
    render_kpi,
    render_sparkline,
    render_status_matrix,
    render_timeline,
)
from core.forge.blueprint import (
    build_blueprint,
    by_dimension,
    collect_answers,
    domain_label,
)
from core.forge.compass import build_compass
from core.forge.edict import Edict, build_edict
from core.forge.models import (
    AcceptanceCriteria,
    Artifact,
    Blueprint,
    Command,
    Directive,
    Domain,
    Formation,
    _safe_float,
    _safe_int,
    _safe_list,
    _safe_str,
)
from core.forge.weave import build_weave

__all__ = [
    "render_artifact",
    "render_bundle",
    "to_markdown_blueprint",
    "to_markdown_bundle",
    "to_markdown_compass",
    "to_markdown_edict",
    "to_markdown_weave",
]

_KINDS = ("blueprint", "edict", "weave", "compass", "bundle")
_GAP = "_Not yet specified._"


# --- small fail-open helpers -----------------------------------------------

def _short(text: Any, limit: int = 120) -> str:
    try:
        s = _safe_str(text)
        return s if len(s) <= limit else s[: limit - 3].rsplit(" ", 1)[0] + "..."
    except Exception:  # noqa: BLE001
        return ""


def _cell(text: Any) -> str:
    """Escape one Markdown table cell. Never raises."""
    try:
        s = _safe_str(text).replace("\n", " ").replace("\r", " ")
        return s.replace("|", "\\|") or "—"
    except Exception:  # noqa: BLE001
        return "—"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    """GitHub Markdown table. Never raises."""
    try:
        head = "| " + " | ".join(headers) + " |"
        sep = "|" + "|".join(" --- " for _ in headers) + "|"
        body = ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
        return "\n".join([head, sep, *body])
    except Exception:  # noqa: BLE001
        return ""


def _bullets(items: Any, gap: str = "_None identified._") -> str:
    try:
        rows = [_safe_str(i) for i in _safe_list(items)]
        rows = [r for r in rows if r]
        return "\n".join(f"- {r}" for r in rows) if rows else gap
    except Exception:  # noqa: BLE001
        return gap


def _interview_meta(interview: Any) -> dict[str, Any]:
    """Safe interview metadata for headers/visuals. Never raises."""
    meta: dict[str, Any] = {
        "id": "", "title": "", "slug": "", "domain": "general",
        "label": "General", "coverage": 0.0, "confidence": 0.0,
        "answered_dims": set(),
    }
    try:
        meta["id"] = _short(getattr(interview, "id", ""), 24)
        meta["title"] = _short(getattr(interview, "title", ""), 80)
        meta["slug"] = _short(getattr(interview, "slug", ""), 64)
    except Exception:  # noqa: BLE001
        pass
    try:
        dom = Domain.coerce(getattr(interview, "domain", Domain.GENERAL))
        meta["domain"] = dom.value
        meta["label"] = domain_label(dom)
    except Exception:  # noqa: BLE001
        pass
    try:
        meta["coverage"] = max(0.0, min(1.0, _safe_float(interview.coverage(), 0.0)))
    except Exception:  # noqa: BLE001
        meta["coverage"] = 0.0
    try:
        meta["confidence"] = max(0.0, min(1.0, _safe_float(
            interview.overall_confidence(), 0.0)))
    except Exception:  # noqa: BLE001
        meta["confidence"] = 0.0
    try:
        buckets = by_dimension(collect_answers(interview))
        meta["answered_dims"] = {d for d, rows in buckets.items() if rows}
    except Exception:  # noqa: BLE001
        pass
    return meta


def _path(meta: dict[str, Any], kind: str) -> str:
    try:
        slug = _safe_str(meta.get("slug")) or _safe_str(meta.get("id")) or "draft"
        return f".school/forge/{slug}/{_safe_str(kind)}.md"
    except Exception:  # noqa: BLE001
        return ""


def _fallback_artifact(kind: Any, note: str = "") -> Artifact:
    """A graceful artifact for catastrophic input. Never raises."""
    try:
        k = _safe_str(kind) or "artifact"
        title = f"{k.capitalize()} (recovered)"
        md = (
            f"# {title}\n\n"
            f"_Forge recovered gracefully while rendering this artifact.\n"
            f"Reason: {_short(note or 'input could not be fully interpreted', 120)}_\n"
        )
        vis = f"{title}\n  [recovered] fail-open render — content unavailable"
        return Artifact(kind=k, title=title, markdown=md, visual=vis,
                        domain="", metadata={"fail_open": True})
    except Exception:  # noqa: BLE001
        return Artifact(kind="artifact", title="Recovered",
                        markdown="# Recovered\n", visual="[recovered]")


# --- model coercion --------------------------------------------------------

def _coerce_blueprint(obj: Any) -> Blueprint:
    try:
        if isinstance(obj, Blueprint):
            return obj
        if isinstance(obj, dict):
            return Blueprint.from_dict(obj)
        bp = Blueprint()
        for fld in ("title", "goal", "problem", "proposed", "slug"):
            try:
                v = _safe_str(getattr(obj, fld, ""))
                if v:
                    setattr(bp, fld, v)
            except Exception:  # noqa: BLE001
                continue
        try:
            bp.domain = Domain.coerce(getattr(obj, "domain", Domain.GENERAL))
        except Exception:  # noqa: BLE001
            bp.domain = Domain.GENERAL
        for fld in ("non_goals", "constraints", "assumptions",
                    "success_metrics", "open_questions"):
            try:
                rows = [_safe_str(r) for r in _safe_list(getattr(obj, fld, []))]
                setattr(bp, fld, [r for r in rows if r][:20])
            except Exception:  # noqa: BLE001
                continue
        for fld in ("risks", "decomposition", "traceability"):
            try:
                rows = [r for r in _safe_list(getattr(obj, fld, []))
                        if isinstance(r, dict)]
                setattr(bp, fld, rows[:40])
            except Exception:  # noqa: BLE001
                continue
        try:
            gloss = getattr(obj, "glossary", {})
            if isinstance(gloss, dict):
                bp.glossary = {_safe_str(k): _safe_str(v)
                               for k, v in list(gloss.items())[:40]}
        except Exception:  # noqa: BLE001
            pass
        return bp
    except Exception:  # noqa: BLE001
        return Blueprint()


def _command_list(raw: Any) -> list[Command]:
    out: list[Command] = []
    try:
        for item in _safe_list(raw)[:200]:
            try:
                if isinstance(item, Command):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(Command.from_dict(item))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return out
    return out


def _directive_list(raw: Any) -> list[Directive]:
    out: list[Directive] = []
    try:
        for item in _safe_list(raw)[:200]:
            try:
                if isinstance(item, Directive):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(Directive.from_dict(item))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return out
    return out


def _coerce_edict(obj: Any) -> Edict:
    try:
        if isinstance(obj, Edict):
            return obj
        if isinstance(obj, dict):
            return Edict(
                commands=_command_list(obj.get("commands")),
                directives=_directive_list(obj.get("directives")),
            )
        holder_c = getattr(obj, "commands", None)
        holder_d = getattr(obj, "directives", None)
        if holder_c is not None or holder_d is not None:
            return Edict(commands=_command_list(holder_c),
                         directives=_directive_list(holder_d))
        seq = _safe_list(obj)
        if len(seq) == 2 and isinstance(seq[0], (list, tuple)) \
                and isinstance(seq[1], (list, tuple)):
            return Edict(commands=_command_list(seq[0]),
                         directives=_directive_list(seq[1]))
        return Edict(commands=_command_list(seq))
    except Exception:  # noqa: BLE001
        return Edict()


def _coerce_formation(obj: Any) -> Formation:
    try:
        if isinstance(obj, Formation):
            return obj
        if isinstance(obj, dict):
            return Formation.from_dict(obj)
        f = Formation()
        f.phases = [p for p in _safe_list(getattr(obj, "phases", []))
                    if isinstance(p, dict)][:40]
        f.lanes = [p for p in _safe_list(getattr(obj, "lanes", []))
                   if isinstance(p, dict)][:40]
        for dep in _safe_list(getattr(obj, "dependencies", []))[:200]:
            try:
                a, b = dep
                f.dependencies.append((_safe_str(a), _safe_str(b)))
            except Exception:  # noqa: BLE001
                continue
        f.critical_path = [_safe_str(x) for x in
                           _safe_list(getattr(obj, "critical_path", []))][:200]
        return f
    except Exception:  # noqa: BLE001
        return Formation()


def _coerce_acceptance(obj: Any) -> AcceptanceCriteria:
    try:
        if isinstance(obj, AcceptanceCriteria):
            return obj
        if isinstance(obj, dict):
            return AcceptanceCriteria.from_dict(obj)
        acc = AcceptanceCriteria()
        acc.scenarios = [s for s in _safe_list(getattr(obj, "scenarios", []))
                         if isinstance(s, dict)][:40]
        acc.checklist = [_safe_str(c) for c in
                         _safe_list(getattr(obj, "checklist", [])) if _safe_str(c)][:60]
        acc.metrics = [m for m in _safe_list(getattr(obj, "metrics", []))
                       if isinstance(m, dict)][:40]
        return acc
    except Exception:  # noqa: BLE001
        return AcceptanceCriteria()


# --- Markdown renderers ----------------------------------------------------

def to_markdown_blueprint(bp: Blueprint, interview: Any = None) -> str:
    """Render a blueprint as clean GitHub Markdown. Never raises."""
    try:
        b = _coerce_blueprint(bp)
        meta = _interview_meta(interview)
        label = domain_label(b.domain) or meta.get("label", "General")
        title = _safe_str(b.title) or _safe_str(meta.get("title")) or "Untitled"
        out: list[str] = [f"# Blueprint — {_short(title, 90)}", ""]
        out.append(
            f"> **Domain:** {label} · **Slug:** `{_short(b.slug or meta.get('slug'), 40)}`\n"
            f"> Discovery coverage: {_pct(meta.get('coverage', 0.0))} · "
            f"Answer confidence: {_pct(meta.get('confidence', 0.0))}"
        )
        out += ["", "## Goal", "", _safe_str(b.goal) or _GAP]
        out += ["", "## Problem", "", _safe_str(b.problem) or _GAP]
        out += ["", "## Proposed Solution", "", _safe_str(b.proposed) or _GAP]

        rows = [
            [i, d.get("title", ""), d.get("detail", ""), d.get("source", "")]
            for i, d in enumerate(_dict_rows(b.decomposition), 1)
        ]
        out += ["", "## Work Breakdown", "",
                _table(["#", "Item", "Detail", "Source"], rows)
                if rows else _GAP]

        out += ["", "## Non-Goals", "", _bullets(b.non_goals)]
        out += ["", "## Constraints", "", _bullets(b.constraints)]
        out += ["", "## Assumptions", "", _bullets(b.assumptions)]
        out += ["", "## Success Metrics", "", _bullets(b.success_metrics)]

        risk_rows = [
            [r.get("risk", ""), r.get("impact", ""), r.get("mitigation", ""),
             r.get("source", "")]
            for r in _dict_rows(b.risks)
        ]
        out += ["", "## Risks", "",
                _table(["Risk", "Impact", "Mitigation", "Source"], risk_rows)
                if risk_rows else "_No risks identified yet._"]

        out += ["", "## Open Questions", "", _bullets(b.open_questions)]

        gloss_rows = [[k, v] for k, v in sorted(_glossary(b.glossary).items())]
        out += ["", "## Glossary", "",
                _table(["Term", "Definition"], gloss_rows)
                if gloss_rows else "_No terms defined yet._"]

        trace_rows = [
            [t.get("question_id", ""), t.get("dimension", ""),
             t.get("lands_in", ""), t.get("excerpt", "")]
            for t in _dict_rows(b.traceability)
        ]
        out += ["", "## Traceability", "",
                _table(["Question", "Dimension", "Lands in", "Excerpt"], trace_rows)
                if trace_rows else "_No interview answers to trace yet._"]
        return "\n".join(out).rstrip() + "\n"
    except Exception:  # noqa: BLE001
        return "# Blueprint\n\n_Not yet specified._\n"


def to_markdown_edict(edict: Edict, interview: Any = None) -> str:
    """Render an edict (commands + directives) as Markdown. Never raises."""
    try:
        e = _coerce_edict(edict)
        meta = _interview_meta(interview)
        label = meta.get("label", "General")
        title = _safe_str(meta.get("title")) or f"{label} Edict"
        total = sum(max(0, _safe_int(c.estimated_minutes)) for c in e.commands)
        out = [f"# Edict — {_short(title, 90)}", ""]
        out.append(
            f"> **Domain:** {label} · **Commands:** {len(e.commands)} · "
            f"**Directives:** {len(e.directives)} · **Estimated effort:** ~{total} min"
        )
        out += ["", "## Commands", ""]
        if e.commands:
            phase_order: list[str] = []
            for c in e.commands:
                p = _safe_str(c.phase) or "General"
                if p not in phase_order:
                    phase_order.append(p)
            for i, phase in enumerate(phase_order, 1):
                rows = []
                for c in e.commands:
                    if (_safe_str(c.phase) or "General") != phase:
                        continue
                    rows.append([
                        c.id, c.kind, _short(c.title, 70),
                        max(0, _safe_int(c.estimated_minutes)),
                        ", ".join(_safe_str(d) for d in c.depends_on) or "—",
                    ])
                out += [f"### Phase {i} — {_short(phase, 60)}", ""]
                out += [_table(["ID", "Kind", "Command", "Est. (min)", "Depends on"], rows), ""]
        else:
            out += ["_No commands derived yet — complete the interview._", ""]

        out += ["## Directives", ""]
        if e.directives:
            for kind in ("always", "never", "prefer", "avoid"):
                rows = [
                    [d.id, _short(d.rule, 80), _short(d.rationale, 80),
                     f"{_safe_float(d.strength, 1.0):.2f}"]
                    for d in e.directives if _safe_str(d.kind) == kind
                ]
                if rows:
                    out += [f"### {kind.capitalize()}", ""]
                    out += [_table(["ID", "Rule", "Rationale", "Strength"], rows), ""]
        else:
            out += ["_No directives derived yet._", ""]
        return "\n".join(out).rstrip() + "\n"
    except Exception:  # noqa: BLE001
        return "# Edict\n\n_No commands derived yet._\n"


def to_markdown_weave(formation: Formation, interview: Any = None) -> str:
    """Render a formation (phases/dependencies/lanes/path) as Markdown."""
    try:
        f = _coerce_formation(formation)
        meta = _interview_meta(interview)
        label = meta.get("label", "General")
        title = _safe_str(meta.get("title")) or f"{label} Formation"
        kind = _safe_str(f.kind) or "phases"
        out = [f"# Weave — {_short(title, 90)}", ""]
        out.append(
            f"> **Formation:** {_safe_str(kind) or 'phases'} · "
            f"**Phases:** {len(f.phases)} · **Dependencies:** {len(f.dependencies)} · "
            f"**Lanes:** {len(f.lanes)}"
        )

        rows = []
        for i, p in enumerate(_dict_rows(f.phases), 1):
            cmds = _safe_list(p.get("commands"))
            rows.append([
                i, p.get("name", ""), p.get("milestone", ""),
                f"{len(cmds)} cmd", _safe_int(p.get("estimated_minutes")),
            ])
        out += ["", "## Phases", "",
                _table(["#", "Phase", "Milestone", "Commands", "Est. (min)"], rows)
                if rows else "_No phases derived yet._"]

        dep_rows = [[_short(a, 40), _short(b, 40)] for a, b in _pairs(f.dependencies)]
        out += ["", "## Dependencies", "",
                _table(["Before", "After"], dep_rows)
                if dep_rows else "_No dependencies between commands._"]

        lane_rows = []
        for lane in _dict_rows(f.lanes):
            cmds = _safe_list(lane.get("commands"))
            lane_rows.append([
                lane.get("name", ""), lane.get("can_start", ""),
                f"{len(cmds)} cmd", _safe_int(lane.get("estimated_minutes")),
            ])
        out += ["", "## Parallel Lanes", "",
                _table(["Lane", "Starts", "Commands", "Est. (min)"], lane_rows)
                if lane_rows else "_No lanes derived yet._"]

        out += ["", "## Critical Path", ""]
        path = [_safe_str(x) for x in _safe_list(f.critical_path) if _safe_str(x)]
        if path:
            out += [f"{i}. `{_short(x, 40)}`" for i, x in enumerate(path, 1)]
        else:
            out += ["_No dependency chain yet — commands run in listed order._"]
        return "\n".join(out).rstrip() + "\n"
    except Exception:  # noqa: BLE001
        return "# Weave\n\n_No formation derived yet._\n"


def to_markdown_compass(acc: AcceptanceCriteria, interview: Any = None) -> str:
    """Render acceptance criteria (Given/When/Then + checklist + metrics)."""
    try:
        a = _coerce_acceptance(acc)
        meta = _interview_meta(interview)
        label = meta.get("label", "General")
        title = _safe_str(meta.get("title")) or f"{label} Acceptance"
        out = [f"# Compass — {_short(title, 90)}", ""]
        out.append(
            f"> **Domain:** {label} · **Scenarios:** {len(a.scenarios)} · "
            f"**Checklist:** {len(a.checklist)} · **Metrics:** {len(a.metrics)}"
        )
        out += ["", "## Scenarios", ""]
        if a.scenarios:
            for i, s in enumerate(_dict_rows(a.scenarios), 1):
                out.append(f"### S{i}. {_short(s.get('title', 'Scenario'), 70)}")
                out.append("")
                out.append(f"- **Given** {_safe_str(s.get('given', '')) or _GAP}")
                out.append(f"- **When** {_safe_str(s.get('when', '')) or _GAP}")
                out.append(f"- **Then** {_safe_str(s.get('then', '')) or _GAP}")
                out.append("")
        else:
            out += ["_No scenarios derived yet._", ""]

        out += ["## Checklist", ""]
        items = [_safe_str(c) for c in _safe_list(a.checklist) if _safe_str(c)]
        out += [f"- [ ] {c}" for c in items] if items else ["_No checklist items yet._"]
        out += [""]

        out += ["## Metrics", ""]
        mrows = []
        for m in _dict_rows(a.metrics):
            target = m.get("target")
            if target is None:
                target_s = "—"
            elif isinstance(target, (int, float)):
                target_s = f"{target:g}"
            else:
                target_s = _safe_str(target)
            mrows.append([
                m.get("measure") or m.get("name", ""), target_s,
                m.get("unit", "") or "—", m.get("direction", ""),
            ])
        out += [_table(["Metric", "Target", "Unit", "Direction"], mrows)
                if mrows else "_No measurable targets derived yet._"]
        return "\n".join(out).rstrip() + "\n"
    except Exception:  # noqa: BLE001
        return "# Compass\n\n_No acceptance criteria derived yet._\n"


def to_markdown_bundle(bundle: Any, interview: Any = None) -> str:
    """Render the bundle index. Never raises."""
    try:
        meta = _interview_meta(interview)
        label = meta.get("label", "General")
        title = _safe_str(meta.get("title")) or f"{label} Bundle"
        arts: dict[str, Any] = {}
        models: dict[str, Any] = {}
        if isinstance(bundle, dict):
            arts = bundle.get("artifacts") or {}
            models = bundle.get("models") or {}
            arts = arts if isinstance(arts, dict) else {}
            models = models if isinstance(models, dict) else {}
        out = [f"# Forge Bundle — {_short(title, 90)}", ""]
        out.append(
            f"> **Domain:** {label} · **Artifacts:** {len(arts) or len(models) or 4} · "
            f"Coverage: {_pct(meta.get('coverage', 0.0))} · "
            f"Confidence: {_pct(meta.get('confidence', 0.0))}"
        )
        out += ["", "## Contents", ""]
        rows = []
        for kind in _KINDS:
            art = arts.get(kind)
            mdl = models.get(kind)
            art_title = _safe_str(getattr(art, "title", "")) or kind.capitalize()
            words = len(_safe_str(getattr(art, "markdown", "")).split())
            rows.append([kind, _short(art_title, 50), words or "—",
                         _short(getattr(art, "path", ""), 60) or _path(meta, kind),
                         _item_count(kind, mdl)])
        out.append(_table(["Artifact", "Title", "Words", "Path", "Contents"], rows))
        out += ["", "## The Forge Pipeline", ""]
        out += [
            "1. **Blueprint** — the design spec: goal, problem, scope, risks, "
            "and question-level traceability.",
            "2. **Edict** — the execution contract: ordered commands and "
            "always/never directives.",
            "3. **Weave** — the formation: phases with milestones, dependency "
            "structure, parallel lanes and the critical path.",
            "4. **Compass** — the acceptance contract: Given/When/Then "
            "scenarios, a verifiable checklist and measurable targets.",
            "",
            "## Recommended Reading Order",
            "",
            "Read the **Blueprint** first to understand *why*, the **Edict** "
            "for *how*, the **Weave** for *when*, and the **Compass** for "
            "*done*.",
        ]
        return "\n".join(out).rstrip() + "\n"
    except Exception:  # noqa: BLE001
        return "# Forge Bundle\n\n_Artifacts are listed in the sibling files._\n"


# --- visual renderers ------------------------------------------------------

def _pct(ratio: Any) -> str:
    try:
        return f"{max(0.0, min(1.0, _safe_float(ratio, 0.0))) * 100:.0f}%"
    except Exception:  # noqa: BLE001
        return "0%"


def _dict_rows(rows: Any) -> list[dict[str, Any]]:
    return [r for r in _safe_list(rows) if isinstance(r, dict)]


def _glossary(gloss: Any) -> dict[str, str]:
    try:
        if isinstance(gloss, dict):
            return {_safe_str(k): _safe_str(v) for k, v in list(gloss.items())[:60]}
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _pairs(deps: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for dep in _safe_list(deps)[:200]:
        try:
            a, b = dep
            out.append((_safe_str(a), _safe_str(b)))
        except Exception:  # noqa: BLE001
            continue
    return out


def _item_count(kind: str, mdl: Any) -> str:
    try:
        if kind == "blueprint":
            b = _coerce_blueprint(mdl)
            return f"{len(b.decomposition)} items · {len(b.risks)} risks"
        if kind == "edict":
            e = _coerce_edict(mdl)
            return f"{len(e.commands)} commands · {len(e.directives)} directives"
        if kind == "weave":
            f = _coerce_formation(mdl)
            return f"{len(f.phases)} phases · {len(f.critical_path)} on critical path"
        if kind == "compass":
            a = _coerce_acceptance(mdl)
            return f"{len(a.scenarios)} scenarios · {len(a.checklist)} checks"
    except Exception:  # noqa: BLE001
        return "—"
    return "—"


def _visual_blueprint(bp: Blueprint, meta: dict[str, Any], width: int) -> str:
    parts: list[str] = []
    try:
        cov = _safe_float(meta.get("coverage", 0.0), 0.0)
        parts.append(render_kpi(
            f"{cov * 100:.0f}", label="Discovery coverage", suffix="%"))
    except Exception:  # noqa: BLE001
        pass
    try:
        answered = meta.get("answered_dims") or set()
        items = []
        for dim in ("intent", "audience", "scope", "constraints", "success",
                    "resources", "risks", "sequence", "style", "edge_cases",
                    "glossary", "open_questions"):
            name = dim.replace("_", " ")
            items.append((name, "ok" if dim in answered else "warn"))
        parts.append(render_status_matrix(items, 4, label="Dimension coverage"))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts) or "blueprint: no visual data"


def _visual_edict(edict: Edict, meta: dict[str, Any], width: int) -> str:
    parts: list[str] = []
    try:
        counts: dict[str, int] = {}
        for c in edict.commands:
            phase = _safe_str(c.phase) or "General"
            counts[phase] = counts.get(phase, 0) + 1
        items = [(k[:18], float(v)) for k, v in counts.items()]
        parts.append(render_bar_chart(items, min(width, 28),
                                      label="Commands per phase"))
    except Exception:  # noqa: BLE001
        pass
    try:
        minutes = [float(max(0, _safe_int(c.estimated_minutes)))
                   for c in edict.commands]
        if minutes:
            parts.append(render_sparkline(minutes, 0, label="Effort per command"))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts) or "edict: no visual data"


def _visual_weave(formation: Formation, meta: dict[str, Any], width: int) -> str:
    parts: list[str] = []
    try:
        rows = _dict_rows(formation.phases)
        cursor = 0.0
        spans: list[tuple[str, float, float]] = []
        for p in rows:
            dur = max(1.0, _safe_float(p.get("estimated_minutes"), 1.0))
            spans.append((_short(p.get("name", ""), 22), cursor, cursor + dur))
            cursor += dur
        if spans:
            parts.append(render_timeline(spans, min(width, 36), cursor,
                                         label="Phase timeline (est. minutes)"))
    except Exception:  # noqa: BLE001
        pass
    try:
        path = [_safe_str(x) for x in _safe_list(formation.critical_path)]
        items = [("critical path", float(len(path))),
                 ("all commands", float(max(1, sum(
                     len(_safe_list(p.get("commands")))
                     for p in _dict_rows(formation.phases)))))]
        parts.append(render_bar_chart(items, min(width, 20),
                                      label="Critical path share"))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts) or "weave: no visual data"


def _visual_compass(acc: AcceptanceCriteria, meta: dict[str, Any], width: int) -> str:
    parts: list[str] = []
    try:
        checks = len([c for c in _safe_list(acc.checklist) if _safe_str(c)])
        scen = len(_dict_rows(acc.scenarios))
        met = len(_dict_rows(acc.metrics))
        defined = bool(checks or scen or met)
        cov = _safe_float(meta.get("coverage", 0.0), 0.0)
        readiness = cov if cov > 0 else (1.0 if defined else 0.0)
        parts.append(render_donut(readiness, 5, label="Checklist completion"))
    except Exception:  # noqa: BLE001
        pass
    try:
        items = [("scenarios", float(len(_dict_rows(acc.scenarios)))),
                 ("checklist", float(len([c for c in _safe_list(acc.checklist)
                                          if _safe_str(c)]))),
                 ("metrics", float(len(_dict_rows(acc.metrics))))]
        parts.append(render_bar_chart(items, min(width, 20),
                                      label="Acceptance surface"))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts) or "compass: no visual data"


def _visual_bundle(arts: dict[str, Any], meta: dict[str, Any], width: int) -> str:
    parts: list[str] = []
    try:
        ready = sum(1 for k in _KINDS
                    if _safe_str(getattr(arts.get(k), "markdown", ""))) \
            / max(1, len(_KINDS))
        parts.append(render_visual("progress_wheel",
                                   {"ratio": ready, "size": 5},
                                   "Bundle readiness", min(width, 20)))
    except Exception:  # noqa: BLE001
        pass
    try:
        items = [(k, "ok" if _safe_str(getattr(arts.get(k), "markdown", ""))
                  else "warn") for k in _KINDS]
        parts.append(render_status_matrix(items, 3, label="Artifact status"))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts) or "bundle: no visual data"


# --- public entry points ---------------------------------------------------

def render_artifact(
    kind: Any,
    obj: Any,
    interview: Any = None,
    width: int = 60,
) -> Artifact:
    """Render one Forge artifact to Markdown + visual.

    ``kind`` is "blueprint" | "edict" | "weave" | "compass" | "bundle"; ``obj``
    is the corresponding builder output (typed object or dict).

    FAIL-OPEN: never raises. Garbage input yields a graceful Artifact with
    non-empty markdown and visual.
    """
    try:
        k = _safe_str(kind).lower().strip().replace(" ", "_").replace("-", "_")
        w = max(20, min(120, _safe_int(width, 60)))
        meta = _interview_meta(interview)
        domain = _safe_str(meta.get("domain"))
        title = _safe_str(meta.get("title")) or f"{meta.get('label', 'General')} work"

        if k == "blueprint":
            b = _coerce_blueprint(obj)
            return Artifact(
                kind="blueprint",
                title=_safe_str(b.title) or f"Blueprint — {title}",
                markdown=to_markdown_blueprint(b, interview),
                visual=_visual_blueprint(b, meta, w),
                path=_path(meta, "blueprint"),
                domain=domain,
                metadata=_artifact_meta(meta, b, None, None, None),
            )
        if k == "edict":
            e = _coerce_edict(obj)
            return Artifact(
                kind="edict",
                title=f"Edict — {title}",
                markdown=to_markdown_edict(e, interview),
                visual=_visual_edict(e, meta, w),
                path=_path(meta, "edict"),
                domain=domain,
                metadata=_artifact_meta(meta, None, e, None, None),
            )
        if k == "weave":
            f = _coerce_formation(obj)
            return Artifact(
                kind="weave",
                title=f"Weave — {title}",
                markdown=to_markdown_weave(f, interview),
                visual=_visual_weave(f, meta, w),
                path=_path(meta, "weave"),
                domain=domain,
                metadata=_artifact_meta(meta, None, None, f, None),
            )
        if k == "compass":
            a = _coerce_acceptance(obj)
            return Artifact(
                kind="compass",
                title=f"Compass — {title}",
                markdown=to_markdown_compass(a, interview),
                visual=_visual_compass(a, meta, w),
                path=_path(meta, "compass"),
                domain=domain,
                metadata=_artifact_meta(meta, None, None, None, a),
            )
        if k == "bundle":
            arts: dict[str, Any] = {}
            models: dict[str, Any] = {}
            if isinstance(obj, dict):
                arts = obj.get("artifacts") or {}
                models = obj.get("models") or {}
                arts = arts if isinstance(arts, dict) else {}
                models = models if isinstance(models, dict) else {}
            bundle_obj = {"artifacts": arts, "models": models}
            return Artifact(
                kind="bundle",
                title=f"Forge Bundle — {title}",
                markdown=to_markdown_bundle(bundle_obj, interview),
                visual=_visual_bundle(arts, meta, w),
                path=_path(meta, "bundle"),
                domain=domain,
                metadata={"artifacts": sorted(arts) or list(_KINDS),
                          "fail_open": False},
            )
        return _fallback_artifact(k or "artifact", f"unknown artifact kind: {k}")
    except Exception as exc:  # noqa: BLE001
        return _fallback_artifact(kind, _safe_str(exc)[:120])


def render_bundle(interview: Any, width: int = 60) -> dict[str, Artifact]:
    """Build and render all five Forge artifacts at once.

    Returns ``{"blueprint": Artifact, "edict": ..., "weave": ...,
    "compass": ..., "bundle": ...}``.  The ``bundle`` artifact is an index
    over the other four.

    FAIL-OPEN: never raises; on catastrophic input returns five graceful
    fallback artifacts.
    """
    try:
        bp = build_blueprint(interview)
        edict = build_edict(interview, bp)
        weave = build_weave(interview, edict.commands, bp)
        compass = build_compass(interview, bp, edict.commands)
        arts: dict[str, Artifact] = {
            "blueprint": render_artifact("blueprint", bp, interview, width),
            "edict": render_artifact("edict", edict, interview, width),
            "weave": render_artifact("weave", weave, interview, width),
            "compass": render_artifact("compass", compass, interview, width),
        }
        arts["bundle"] = render_artifact(
            "bundle",
            {
                "artifacts": arts,
                "models": {"blueprint": bp, "edict": edict,
                           "weave": weave, "compass": compass},
            },
            interview,
            width,
        )
        return arts
    except Exception:  # noqa: BLE001
        return {k: _fallback_artifact(k) for k in _KINDS}


def _artifact_meta(
    meta: dict[str, Any],
    bp: Any,
    edict: Any,
    formation: Any,
    acc: Any,
) -> dict[str, Any]:
    """JSON-safe metadata block for an Artifact. Never raises."""
    out: dict[str, Any] = {
        "domain": _safe_str(meta.get("domain")),
        "domain_label": _safe_str(meta.get("label")),
        "source_interview": _safe_str(meta.get("id")),
        "coverage": round(_safe_float(meta.get("coverage", 0.0), 0.0), 4),
        "confidence": round(_safe_float(meta.get("confidence", 0.0), 0.0), 4),
        "fail_open": False,
    }
    try:
        if bp is not None:
            b = _coerce_blueprint(bp)
            out["counts"] = {
                "constraints": len(b.constraints),
                "risks": len(b.risks),
                "success_metrics": len(b.success_metrics),
                "decomposition": len(b.decomposition),
                "traceability": len(b.traceability),
            }
        if edict is not None:
            e = _coerce_edict(edict)
            out["counts"] = {
                "commands": len(e.commands),
                "directives": len(e.directives),
                "estimated_minutes": sum(
                    max(0, _safe_int(c.estimated_minutes)) for c in e.commands),
            }
        if formation is not None:
            f = _coerce_formation(formation)
            out["counts"] = {
                "phases": len(f.phases),
                "dependencies": len(f.dependencies),
                "lanes": len(f.lanes),
                "critical_path": len(f.critical_path),
            }
        if acc is not None:
            a = _coerce_acceptance(acc)
            out["counts"] = {
                "scenarios": len(a.scenarios),
                "checklist": len(a.checklist),
                "metrics": len(a.metrics),
            }
    except Exception:  # noqa: BLE001
        out["fail_open"] = True
    return out
