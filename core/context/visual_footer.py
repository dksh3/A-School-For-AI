"""Add visual text-art footers to every bridge response."""
from __future__ import annotations

from typing import Any

from core.context.visual_dispatch import render_visual


def _build_visual(command: str, req: dict[str, Any], resp: dict[str, Any]) -> str:
    """Build a visual summary for any bridge command response."""
    parts: list[str] = []

    if command == "status":
        components = resp.get("components") or {}
        healthy = sum(1 for v in components.values()
                      if v in ("ok", "active", "ready", "available", "up", "pass"))
        total = max(len(components), 1)
        ratio = healthy / total
        parts.append(render_visual("gauge", data={
            "value": int(ratio * 100), "max_val": 100, "label": "Health", "width": 28,
        }))
        if components:
            items = [
                (k, "ok" if v in ("ok", "active", "ready", "available", "up", "pass") else "warn")
                for k, v in components.items()
            ]
            parts.append(render_visual("status_matrix", data={"items": items, "cols": 3}))

    elif command in ("remember", "learn"):
        mid = resp.get("id", "?")
        parts.append(render_visual("mini_ring", data={
            "ratio": 1.0, "label": f"Stored [{mid}]",
        }))

    elif command == "recall":
        hits = resp.get("hits", 0)
        parts.append(render_visual("sparkline", data={
            "values": [hits] * 8, "label": f"Recall hits: {hits}", "width": 16,
        }))

    elif command == "search":
        results = resp.get("results") or []
        parts.append(render_visual("bar_chart", data={
            "items": [{"name": r.get("text", "?")[:18], "value": r.get("score", 0.5)}
                      for r in results[:6]], "label": "Search scores",
        }))

    elif command == "diagnose":
        checks = resp.get("checks") or resp.get("components") or {}
        if checks:
            items = [
                (k, "ok" if v in ("ok", "pass", "ready", "available", "up", "active") else "warn")
                for k, v in checks.items()
            ]
            parts.append(render_visual("status_matrix", data={"items": items, "cols": 2}))
        parts.append(render_visual("gauge", data={
            "value": 85, "max_val": 100, "label": "Diag Health", "width": 24,
        }))

    elif command in ("context_status", "context_compress", "context_restore"):
        saved = resp.get("tokens_saved", 0)
        ratio = resp.get("ratio", 0.5)
        parts.append(render_visual("donut", data={
            "ratio": ratio, "label": f"Ctx {int(ratio*100)}%", "size": 5, "show_pct": True,
        }))
        parts.append(render_visual("kpi", data={
            "number": saved, "unit": "tokens saved",
        }))

    elif command in ("goal",):
        progress = resp.get("progress", 0.0)
        parts.append(render_visual("progress_wheel", data={
            "wheel_ratio": progress, "label": f"Goal {int(progress*100)}%",
        }))

    elif command in ("workflow",):
        phase = resp.get("phase", "")
        phases = resp.get("phases") or []
        if phases:
            items = [{"name": p.get("name", "?"), "start": i, "duration": 1}
                     for i, p in enumerate(phases[:8])]
            parts.append(render_visual("timeline", data={
                "phases": items, "total": len(items), "label": f"Workflow: {phase}",
            }))

    elif command in ("progress",):
        items = req.get("items") or resp.get("items") or []
        if items:
            bar_items = [{"name": str(i.get("name", "?"))[:16], "value": i.get("pct", 50)}
                         for i in items[:6] if isinstance(i, dict)]
            if bar_items:
                parts.append(render_visual("bar_chart", data={
                    "items": bar_items, "label": "Progress",
                }))

    elif command in ("research",):
        findings = resp.get("findings") or []
        count = len(findings) if isinstance(findings, list) else 2
        parts.append(render_visual("kpi", data={
            "number": count, "unit": "findings",
        }))

    elif command in ("explore", "navigate"):
        files = resp.get("files") or []
        parts.append(render_visual("kpi", data={
            "number": len(files) if isinstance(files, list) else 0, "unit": "files",
        }))

    elif command in ("execute",):
        ok = resp.get("ok", False)
        duration = resp.get("duration_ms", 0)
        parts.append(render_visual("gauge", data={
            "value": 100 if ok else 20, "max_val": 100,
            "label": "Exit " + str(resp.get("exit_code", "?")), "width": 22,
        }))
        parts.append(render_visual("kpi", data={
            "number": duration, "unit": "ms",
        }))

    elif command in ("session",):
        action = req.get("action", "")
        parts.append(render_visual("mini_ring", data={
            "ratio": 0.8, "label": f"Session [{action}]",
        }))

    elif command in ("skill_list", "skill_search", "skill_status"):
        skills = resp.get("skills") or resp.get("results") or []
        count = len(skills) if isinstance(skills, list) else 0
        parts.append(render_visual("kpi", data={
            "number": count, "unit": "skills",
        }))

    elif command in ("observe",):
        total = resp.get("total", 1)
        parts.append(render_visual("sparkline", data={
            "values": [total] * 10, "label": f"Observations: {total}", "width": 14,
        }))

    elif command in ("conflict",):
        conflicts = resp.get("conflicts") or []
        count = len(conflicts) if isinstance(conflicts, list) else 0
        parts.append(render_visual("gauge", data={
            "value": min(count * 20, 100), "max_val": 100,
            "label": "Conflicts", "width": 22,
        }))

    elif command in ("confidence",):
        score = resp.get("score", resp.get("confidence", 0.5))
        parts.append(render_visual("gauge", data={
            "value": int(score * 100), "max_val": 100,
            "label": "Confidence", "width": 26,
        }))

    elif command in ("visualize",):
        return ""  # Already has visual output

    # Universal chip footer for every command
    action = req.get("action", command)
    parts.append(render_visual("mini_ring", data={
        "ratio": 1.0 if resp.get("ok") else 0.2,
        "label": f"{command} [{action}] {'OK' if resp.get('ok') else 'ERR'}",
    }))

    return "\n".join(p for p in parts if p)


def add_visual_footer(
    resp: dict[str, Any], command: str, req: dict[str, Any]
) -> dict[str, Any]:
    """Append a visual text-art summary to a bridge response dict.

    Layer-2 Tool Choice Guard: when a request names a non-School tool, brand
    the response with the guard redirect so the agent is steered to School even
    if the JS layer is bypassed. FAIL-OPEN: never raises.
    """
    try:
        visual = _build_visual(command, req, resp)
        if visual:
            resp["visual"] = visual
    except Exception:
        pass  # fail-open
    # Second-layer guard (defense-in-depth).
    try:
        from core.context.tool_guard import brand_response

        req_tool = str(req.get("tool", "") or req.get("tool_name", "") or "")
        if req_tool:
            resp = brand_response(resp, req_tool)
    except Exception:
        pass  # fail-open
    return resp
