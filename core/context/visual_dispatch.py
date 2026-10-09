"""Central visual dispatcher — routes type names to any of the 101 renderers.

Used by bridge, CLI, MCP, and TS plugin so every surface supports every visual.
All inputs are sanitized so hostile / malformed data never crashes a renderer.
"""
from __future__ import annotations

import functools
import inspect
import math
from typing import Any


def _safe_float(v: Any, default: float = 0.0) -> float:
    """Coerce to a finite float, falling back to *default* for NaN/inf/None/garbage."""
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except Exception:  # noqa: BLE001 — coercion must never raise
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        n = int(_safe_float(v, float(default)))
        return max(-(10**9), min(10**9, n))
    except Exception:  # noqa: BLE001
        return default


def _safe_str(v: Any, default: str = "") -> str:
    try:
        return v if isinstance(v, str) else ("" if v is None else str(v))
    except Exception:  # noqa: BLE001
        return default


def _safe_bool(v: Any) -> bool:
    try:
        return bool(v)
    except Exception:  # noqa: BLE001
        return False


def _pair(item: Any, n: int = 2) -> tuple:
    """Return an n-tuple from any sequence, padding with zeros/empty strings."""
    if item is None:
        item = ()
    try:
        seq = list(item)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        seq = []
    pad = [""] * n
    for i, s in enumerate(seq[:n]):
        pad[i] = s
    return tuple(pad)


def _conv(raw: Any, n: int, *fns: Any) -> list:
    """Convert a raw list of sequences to list of n-tuples via *fns* converters."""
    try:
        if not isinstance(raw, (list, tuple)):
            return []
        out = []
        for item in raw:
            p = _pair(item, n)
            out.append(tuple(fns[i](p[i]) if i < len(fns) else p[i] for i in range(n)))
        return out
    except Exception:  # noqa: BLE001
        return []


def _sanitize_data(data: dict[str, Any] | None) -> dict[str, Any]:
    """Return a safe shallow copy of *data* with None values replaced by empties."""
    if not isinstance(data, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in data.items():
        if v is None:
            out[k] = [] if k.endswith(("s", "items", "data", "values", "list")) else {}
            if not isinstance(out[k], (list, dict)):
                out[k] = {}
        else:
            out[k] = v
    return out


def _dim(v: Any, lo: int = 0, hi: int = 200) -> int:
    """Coerce to an int clamped to [lo, hi]; hostile/non-finite -> lo."""
    try:
        n = int(_safe_float(v, float(lo)))
    except Exception:  # noqa: BLE001
        n = lo
    return max(lo, min(hi, n))


def _seq(v: Any, cap: int = 2000) -> list:
    """Best-effort list from any value; strings/None collapse safely."""
    if v is None:
        return []
    if isinstance(v, (str, bytes, bytearray)):
        return [v]
    try:
        out = list(v)
    except Exception:  # noqa: BLE001
        return [v]
    return out[:cap]


def _as_map(v: Any) -> dict:
    """Copy a mapping to a plain dict whose iteration can never explode."""
    out: dict = {}
    if not isinstance(v, dict):
        return out
    try:
        for k, val in v.items():
            out[_safe_str(k)] = val
    except Exception:  # noqa: BLE001 — _BadDict etc.
        return {}
    return out


def _as_tree(v: Any, depth: int = 0) -> list:
    """List of node dicts (name/children[/badge]) — recursion-bounded."""
    out = []
    for x in _seq(v):
        if depth > 6:
            out.append({"name": _safe_str(x), "children": []})
            continue
        if isinstance(x, dict):
            m = _as_map(x)
            node: dict[str, Any] = {"name": _safe_str(m.get("name", m.get("label", "?")))}
            if "badge" in m:
                node["badge"] = _safe_str(m.get("badge"))
            child = m.get("children")
            node["children"] = _as_tree(child, depth + 1) if child is not None else []
            out.append(node)
        else:
            out.append({"name": _safe_str(x), "children": []})
    return out


def _safe_int_key(k: Any) -> int:
    return _safe_int(k, 0)


#: code -> coercer.  Used to normalize every renderer argument to a safe shape.
CODES: dict[str, Any] = {
    "str": _safe_str,
    "float": _safe_float,
    "int": lambda v: _dim(v, 0, 200),
    "width": lambda v: _dim(v, 0, 32),
    "bool": _safe_bool,
    "list:str": lambda v: [_safe_str(x) for x in _seq(v)],
    "list:float": lambda v: [_safe_float(x) for x in _seq(v)],
    "list:int": lambda v: [_dim(x, 0, 500) for x in _seq(v)],
    "list:bool": lambda v: [_safe_bool(x) for x in _seq(v)],
    "grid": lambda v: [[_safe_float(x) for x in _seq(row)] for row in _seq(v)],
    "tree": _as_tree,
    "rows": lambda v: [
        {_safe_str(k): _safe_str(x) for k, x in _as_map(r).items()} for r in _seq(v)
    ],
    "dict:str->int": lambda v: {_safe_str(k): _safe_int(x) for k, x in _as_map(v).items()},
    "dict:int->int": lambda v: {_safe_int_key(k): _safe_int(x) for k, x in _as_map(v).items()},
    "dict:str->list:str": lambda v: {
        _safe_str(k): [_safe_str(x) for x in _seq(val)] for k, val in _as_map(v).items()
    },
    "dict:str->list:float": lambda v: {
        _safe_str(k): [_safe_float(x) for x in _seq(val)] for k, val in _as_map(v).items()
    },
    "dict:str->str": lambda v: {_safe_str(k): _safe_str(x) for k, x in _as_map(v).items()},
}


def _row(v: Any, slots: list[str]) -> tuple:
    seq = _seq(v)
    return tuple(
        _coerce_code(seq[j] if j < len(seq) else None, slots[j]) for j in range(len(slots))
    )


def _coerce_code(v: Any, code: str) -> Any:
    if code.startswith("pair(") and code.endswith(")"):
        return _row(v, code[5:-1].split(","))
    if code.startswith("(") and code.endswith(")"):
        slots = code[1:-1].split(",")
        return [_row(x, slots) for x in _seq(v)]
    fn = CODES.get(code)
    return fn(v) if fn is not None else v


def _coerce_named(name: str, v: Any) -> Any:
    n = (name or "").lower()
    if any(k in n for k in ("width", "size", "height", "cols", "bins", "frames")):
        return _dim(v, 0, 200)
    if any(k in n for k in ("label", "text", "title", "name", "event", "root", "unit",
                            "currency", "suffix", "trend", "style", "book")):
        return _safe_str(v)
    return v


def _placeholder(name: str) -> str:
    return f"{name}\n  ⚠ hostile input coerced to a safe fallback"


#: Per-renderer argument-coercion spec: one code per positional parameter.
RENDER_SPEC: dict[str, list[str]] = {
    # ── Universal (31) ──
    "render_sparkline": ["list:float", "int", "str"],
    "render_heatmap": ["grid", "list:str", "list:str", "int"],
    "render_donut": ["float", "width", "str", "bool"],
    "render_radar": ["(str,float)", "width", "float"],
    "render_gauge": ["float", "float", "width", "str", "pair(float,float)"],
    "render_timeline": ["(str,float,float)", "width", "float", "str"],
    "render_tree": ["tree", "int", "str", "str", "str", "str", "str"],
    "render_flow": ["list:str", "(int,int,float)", "width", "str"],
    "render_spinner": ["int", "str", "str"],
    "render_spinner_seq": ["str", "int", "str"],
    "render_waterfall": ["(str,float)", "width", "str"],
    "render_braille_chart": ["grid", "width", "width", "list:str"],
    "render_subcell_bar": ["float", "width", "str", "str", "str"],
    "render_status_matrix": ["(str,str)", "width", "str"],
    "render_network": ["tree", "(int,int)", "width", "str"],
    "render_dashboard": ["str", "(str,str)", "width"],
    "render_gradient": ["float", "width", "str", "bool"],
    "render_emoji_status": ["(str,str)", "width"],
    "render_comparison": ["rows", "list:str", "str"],
    "render_bar_chart": ["(str,float)", "width", "str", "bool"],
    "render_histogram": ["list:float", "int", "width", "str"],
    "render_stats_box": ["list:float", "str", "width"],
    "render_delta": ["(str,float,float)", "str"],
    "render_kanban": ["(str,list:str)", "str", "int"],
    "render_kpi": ["str", "str", "str", "str"],
    "render_pie": ["(str,float)", "width", "str"],
    "render_scatter": ["(float,float)", "width", "width", "str", "str"],
    "render_funnel": ["(str,float)", "width", "str"],
    "render_calendar_heatmap": ["dict:str->int", "str", "width"],
    "render_word_cloud": ["(str,int)", "int", "str"],
    "render_mini_ring": ["float", "str"],
    # ── Coding (30) ──
    "render_code_coverage": ["(str,float)", "width", "str", "float"],
    "render_complexity_heat": ["(str,int)", "width", "str"],
    "render_diff_summary": ["(str,int,int)", "width", "str"],
    "render_test_results": ["(str,dict:str->int)", "str"],
    "render_dependency_graph": ["str", "dict:str->list:str", "int", "str"],
    "render_file_size_bars": ["(str,int)", "width", "str", "str"],
    "render_git_timeline": ["(str,str,int)", "width", "str"],
    "render_error_rate": ["list:float", "width", "str"],
    "render_perf_benchmark": ["(str,float,float)", "width", "str"],
    "render_api_latency": ["(str,float,float)", "width", "str"],
    "render_build_pipeline": ["(str,str,float)", "str"],
    "render_security_scan": ["(str,str,str)", "str"],
    "render_code_churn": ["(str,int,int)", "width", "str"],
    "render_db_schema": ["dict:str->list:str", "str"],
    "render_memory_profile": ["list:float", "list:float", "width", "str"],
    "render_flame_chart": ["(str,float,int)", "width", "str"],
    "render_deploy_status": ["(str,str,str)", "str"],
    "render_feature_flags": ["(str,bool,str)", "str"],
    "render_package_versions": ["(str,str,str)", "str"],
    "render_log_density": ["dict:str->list:float", "width", "str"],
    "render_duplication": ["(str,str,int)", "str"],
    "render_refactor_progress": ["(str,int,int)", "width", "str"],
    "render_endpoint_map": ["(str,str,str)", "str"],
    "render_cache_stats": ["(str,int,int)", "width", "str"],
    "render_concurrency": ["(str,float,float)", "width", "float", "str"],
    "render_gc_pressure": ["(str,float,float)", "width", "str"],
    "render_network_waterfall": ["(str,float,float,str)", "width", "str"],
    "render_queue_depth": ["(str,int,int)", "width", "str"],
    "render_error_matrix": ["grid", "list:str", "list:str", "width", "str"],
    "render_review_progress": ["(str,str,int,int)", "str"],
    # ── General (40) ──
    "render_sentiment_gauge": ["float", "float", "float", "str"],
    "render_word_count": ["str", "str"],
    "render_reading_progress": ["int", "int", "width", "str", "str"],
    "render_mood_tracker": ["(str,str)", "str"],
    "render_habit_tracker": ["(str,list:bool)", "str"],
    "render_task_priority": ["(str,str,str)", "str"],
    "render_meeting_agenda": ["(str,int,str)", "str"],
    "render_budget_tracker": ["(str,float,float)", "width", "str", "str"],
    "render_expense_breakdown": ["(str,float)", "width", "str", "str"],
    "render_weekly_schedule": ["dict:str->list:str", "str"],
    "render_countdown": ["str", "int", "int", "int"],
    "render_star_rating": ["float", "float", "str", "int"],
    "render_poll_results": ["(str,int)", "width", "str"],
    "render_survey_matrix": ["(str,list:int)", "list:str", "str"],
    "render_decision_matrix": ["(str,list:float)", "list:str", "list:float", "str"],
    "render_pros_cons": ["list:str", "list:str", "str"],
    "render_progress_wheel": ["float", "width", "str"],
    "render_fitness_stats": ["(str,float,float)", "width", "str"],
    "render_recipe_steps": ["list:str", "str"],
    "render_checklist": ["(str,bool)", "str"],
    "render_travel_itinerary": ["(str,list:str)", "str"],
    "render_study_progress": ["(str,float)", "width", "str"],
    "render_flashcard_scores": ["(str,int,int,int)", "str"],
    "render_quiz_results": ["(str,bool)", "str"],
    "render_todo_board": ["(str,list:str)", "str"],
    "render_price_comparison": ["(str,float,float)", "width", "str", "str"],
    "render_review_summary": ["dict:int->int", "str"],
    "render_mind_map": ["str", "dict:str->list:str", "str"],
    "render_contact_card": ["str", "dict:str->str", "str"],
    "render_gratitude_log": ["(str,str)", "str"],
    "render_water_intake": ["int", "width", "str"],
    "render_sleep_tracker": ["(str,float,float)", "width", "str"],
    "render_meditation_log": ["(str,float)", "width", "str"],
    "render_mood_timeline": ["(str,int)", "str"],
    "render_life_balance": ["(str,float)", "width", "str"],
    "render_savings_goal": ["float", "float", "width", "str", "str"],
    "render_workout_plan": ["(str,str,bool)", "str"],
    "render_reading_list": ["(str,str,float)", "width", "str"],
    "render_wishlist": ["(str,float,str)", "width", "str", "str"],
    "render_date_countdown": ["str", "int", "int", "width", "str"],
}


def fail_open(fn: Any, spec: list[str] | None = None) -> Any:
    """Return fn wrapped so it coerces args and NEVER raises.

    Positional args are coerced via *spec* (one code per positional parameter);
    kwargs fall back to name-based coercion.  Any residual error returns a
    graceful non-empty placeholder string.  This is the fix "in the renderer
    itself": every render_* returns a str for ANY input.
    """
    try:
        params = list(inspect.signature(fn).parameters.values())
        name_to_idx = {p.name: i for i, p in enumerate(params)}
    except Exception:  # noqa: BLE001
        name_to_idx = {}

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            args = list(args)
            if spec:
                for i, a in enumerate(args):
                    if i < len(spec):
                        args[i] = _coerce_code(a, spec[i])
                for k, v in list(kwargs.items()):
                    idx = name_to_idx.get(k)
                    if idx is not None and idx < len(spec):
                        kwargs[k] = _coerce_code(v, spec[idx])
                    else:
                        kwargs[k] = _coerce_named(k, v)
            else:
                for k, v in list(kwargs.items()):
                    kwargs[k] = _coerce_named(k, v)
            r = fn(*args, **kwargs)
            # Invariant: every render_* returns a NON-EMPTY str.
            if isinstance(r, str) and r:
                return r
            return _placeholder(getattr(fn, "__name__", "visual"))
        except Exception:  # noqa: BLE001 — fail-open by design
            return _placeholder(getattr(fn, "__name__", "visual"))

    wrapper.__harden_spec__ = spec  # type: ignore[attr-defined]
    return wrapper


def harden(gmap: dict[str, Any]) -> None:
    """Wrap every render_* callable in *gmap* with fail_open (idempotent)."""
    for name, fn in list(gmap.items()):
        if not name.startswith("render_") or not callable(fn):
            continue
        if getattr(fn, "__harden_spec__", None) is not None:
            continue
        gmap[name] = fail_open(fn, RENDER_SPEC.get(name))


def _render_visual_impl(
    viz_type: str,
    data: dict[str, Any] | None = None,
    label: str = "",
    width: int = 20,
) -> str:
    """Internal dispatcher. Wrapped by render_visual() which is fail-open."""
    data = _sanitize_data(data)
    label = _safe_str(label)
    width = max(1, _safe_int(width, 20))
    t = str(viz_type).strip().lower().replace("-", "_").replace(" ", "_")

    # Import lazily so cold-start is fast
    from core.context.coding_visuals import (
        render_api_latency,
        render_build_pipeline,
        render_cache_stats,
        render_code_churn,
        render_code_coverage,
        render_complexity_heat,
        render_concurrency,
        render_db_schema,
        render_dependency_graph,
        render_deploy_status,
        render_diff_summary,
        render_duplication,
        render_endpoint_map,
        render_error_matrix,
        render_error_rate,
        render_feature_flags,
        render_file_size_bars,
        render_flame_chart,
        render_gc_pressure,
        render_git_timeline,
        render_log_density,
        render_memory_profile,
        render_network_waterfall,
        render_package_versions,
        render_perf_benchmark,
        render_queue_depth,
        render_refactor_progress,
        render_review_progress,
        render_security_scan,
        render_test_results,
    )
    from core.context.general_visuals import (
        render_budget_tracker,
        render_checklist,
        render_contact_card,
        render_countdown,
        render_date_countdown,
        render_decision_matrix,
        render_expense_breakdown,
        render_fitness_stats,
        render_flashcard_scores,
        render_gratitude_log,
        render_habit_tracker,
        render_life_balance,
        render_meditation_log,
        render_meeting_agenda,
        render_mind_map,
        render_mood_timeline,
        render_mood_tracker,
        render_poll_results,
        render_price_comparison,
        render_progress_wheel,
        render_pros_cons,
        render_quiz_results,
        render_reading_list,
        render_reading_progress,
        render_recipe_steps,
        render_review_summary,
        render_savings_goal,
        render_sentiment_gauge,
        render_sleep_tracker,
        render_star_rating,
        render_study_progress,
        render_survey_matrix,
        render_task_priority,
        render_todo_board,
        render_travel_itinerary,
        render_water_intake,
        render_weekly_schedule,
        render_wishlist,
        render_word_count,
        render_workout_plan,
    )
    from core.context.visuals import (
        render_bar_chart,
        render_braille_chart,
        render_calendar_heatmap,
        render_comparison,
        render_dashboard,
        render_delta,
        render_donut,
        render_emoji_status,
        render_flow,
        render_funnel,
        render_gauge,
        render_gradient,
        render_heatmap,
        render_histogram,
        render_kanban,
        render_kpi,
        render_mini_ring,
        render_network,
        render_pie,
        render_radar,
        render_scatter,
        render_sparkline,
        render_spinner,
        render_spinner_seq,
        render_stats_box,
        render_status_matrix,
        render_subcell_bar,
        render_timeline,
        render_tree,
        render_waterfall,
        render_word_cloud,
    )

    # ---------- UNIVERSAL (31) ----------
    if t == "sparkline":
        raw = data.get("values") or []
        vals = [_safe_float(v) for v in raw] if isinstance(raw, (list, tuple)) else []
        return render_sparkline(vals, width=_safe_int(data.get("resample", 0)), label=label)
    if t == "heatmap":
        raw = data.get("grid") or []
        grid = [
            [_safe_float(v) for v in row]
            for row in raw
            if isinstance(row, (list, tuple))
        ] if isinstance(raw, (list, tuple)) else []
        return render_heatmap(
            grid,
            col_labels=data.get("col_labels"),
            row_labels=data.get("row_labels"),
            width=_safe_int(data.get("cell_width", 3), 3),
        )
    if t == "donut":
        return render_donut(
            _safe_float(data.get("ratio", 0)),
            size=_safe_int(data.get("size", 5), 5),
            label=label,
            show_pct=bool(data.get("show_pct", True)),
        )
    if t == "radar":
        raw = data.get("axes") or []
        axes = _conv(raw, 2, _safe_str, _safe_float)
        return render_radar(
            axes, size=_safe_int(data.get("size", 11), 11),
            max_val=_safe_float(data.get("max", 1.0), 1.0)
        )
    if t == "gauge":
        raw_th = data.get("thresholds") or [0.6, 0.85]
        th = (tuple(_safe_float(x) for x in raw_th)
              if isinstance(raw_th, (list, tuple)) else ())
        if len(th) < 2:
            th = (0.6, 0.85)
        return render_gauge(
            _safe_float(data.get("value", 0)),
            max_val=_safe_float(data.get("max", 1.0), 1.0),
            width=width,
            label=label,
            thresholds=th,
        )
    if t == "timeline":
        raw = data.get("phases") or []
        phases = [
            (_safe_str(_pair(p, 3)[0]), _safe_float(_pair(p, 3)[1]), _safe_float(_pair(p, 3)[2]))
            for p in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_timeline(
            phases, width=width, total=_safe_float(data.get("total", 0)), label=label
        )
    if t == "tree":
        items = data.get("items") or []
        if isinstance(items, (list, tuple)):
            safe_items = []
            for it in items:
                if isinstance(it, dict):
                    safe_items.append(it)
                elif isinstance(it, (list, tuple)):
                    p = _pair(it, 2)
                    safe_items.append({"name": _safe_str(p[0]), "depth": _safe_int(p[1])})
                else:
                    safe_items.append({"name": _safe_str(it), "depth": 0})
            items = safe_items
        else:
            items = []
        return render_tree(items)
    if t == "flow":
        raw_n = data.get("nodes") or []
        nodes = [_safe_str(n) for n in raw_n] if isinstance(raw_n, (list, tuple)) else []
        raw_f = data.get("flows") or []
        flows = [
            (_safe_int(_pair(f, 3)[0]), _safe_int(_pair(f, 3)[1]), _safe_float(_pair(f, 3)[2]))
            for f in raw_f
        ] if isinstance(raw_f, (list, tuple)) else []
        return render_flow(nodes, flows, width=width, label=label)
    if t == "spinner":
        return render_spinner(
            _safe_int(data.get("frame", 0)),
            label=label,
            style=_safe_str(data.get("style", "braille"), "braille"),
        )
    if t == "spinner_seq":
        return render_spinner_seq(
            label=label,
            frames=_safe_int(data.get("frames", 10), 10),
            style=_safe_str(data.get("style", "braille"), "braille"),
        )
    if t == "waterfall":
        raw = data.get("items") or []
        items = _conv(raw, 2, _safe_str, _safe_float)
        return render_waterfall(items, width=width, label=label)
    if t in ("braille", "braille_chart"):
        raw = data.get("series") or []
        series = [
            [_safe_float(v) for v in s] for s in raw if isinstance(s, (list, tuple))
        ] if isinstance(raw, (list, tuple)) else []
        return render_braille_chart(
            series,
            width=_safe_int(data.get("width", 16), 16),
            height=_safe_int(data.get("height", 8), 8),
            labels=data.get("labels"),
        )
    if t in ("subcell", "subcell_bar"):
        return render_subcell_bar(
            _safe_float(data.get("ratio", 0)), width=width, label=label
        )
    if t == "status_matrix":
        raw = data.get("items") or []
        items = _conv(raw, 2, _safe_str, _safe_str)
        return render_status_matrix(items, cols=_safe_int(data.get("cols", 4), 4), label=label)
    if t == "network":
        raw_nodes = data.get("nodes") or []
        if not isinstance(raw_nodes, (list, tuple)):
            raw_nodes = []
        nodes = [
            nd if isinstance(nd, dict) else {"name": _safe_str(nd, "?")}
            for nd in raw_nodes
        ]
        edges = [
            (_safe_int(_pair(e)[0]), _safe_int(_pair(e)[1]))
            for e in (data.get("edges") or [])
            if isinstance(e, (list, tuple))
        ] if isinstance(data.get("edges"), (list, tuple)) else []
        return render_network(nodes, edges, size=_safe_int(data.get("size", 21), 21), label=label)
    if t == "dashboard":
        raw = data.get("panels") or []
        panels = _conv(raw, 2, _safe_str, _safe_str)
        return render_dashboard(
            label or "Dashboard", panels, width=_safe_int(data.get("panel_width", 50), 50)
        )
    if t == "gradient":
        return render_gradient(
            _safe_float(data.get("ratio", 0)),
            width=width,
            label=label,
            reverse=bool(data.get("reverse", False)),
        )
    if t in ("emoji", "emoji_status"):
        raw = data.get("items") or []
        items = _conv(raw, 2, _safe_str, _safe_str)
        return render_emoji_status(items, cols=_safe_int(data.get("cols", 3), 3))
    if t == "comparison":
        rows = data.get("rows") or []
        if not isinstance(rows, (list, tuple)):
            rows = []
        return render_comparison(
            rows,
            columns=data.get("columns"),
            winner_col=data.get("winner_col"),
        )
    if t == "bar_chart":
        raw = data.get("items") or []
        items = _conv(raw, 2, _safe_str, _safe_float)
        return render_bar_chart(
            items,
            width=width,
            label=label,
            show_values=bool(data.get("show_values", True)),
        )
    if t == "histogram":
        raw = data.get("values") or []
        vals = [_safe_float(v) for v in raw] if isinstance(raw, (list, tuple)) else []
        return render_histogram(
            vals,
            bins=_safe_int(data.get("bins", 10), 10),
            width=width,
            label=label,
        )
    if t == "stats_box":
        raw = data.get("values") or []
        vals = [_safe_float(v) for v in raw] if isinstance(raw, (list, tuple)) else []
        return render_stats_box(vals, label=label, width=width)
    if t == "delta":
        raw = data.get("items") or []
        items = [
            (_safe_str(_pair(i, 3)[0]), _safe_float(_pair(i, 3)[1]), _safe_float(_pair(i, 3)[2]))
            for i in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_delta(items, label=label)
    if t == "kanban":
        raw = data.get("columns") or []
        cols = [
            (_safe_str(_pair(c)[0]), [_safe_str(x) for x in (_pair(c, 2)[1] or [])])
            for c in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_kanban(cols, label=label, max_items=_safe_int(data.get("max_items", 5), 5))
    if t == "kpi":
        val = data.get("value", 0)
        return render_kpi(
            val if isinstance(val, (int, float, str)) else 0,
            label=label,
            suffix=_safe_str(data.get("suffix", "")),
            trend=_safe_str(data.get("trend", "")),
        )
    if t == "pie":
        raw = data.get("segments") or []
        segs = _conv(raw, 2, _safe_str, _safe_float)
        return render_pie(segs, size=_safe_int(data.get("size", 7), 7), label=label)
    if t == "scatter":
        raw = data.get("points") or []
        pts = _conv(raw, 2, _safe_float, _safe_float)
        return render_scatter(
            pts,
            width=width,
            height=_safe_int(data.get("height", 12), 12),
            x_label=_safe_str(data.get("x_label", "")),
            y_label=_safe_str(data.get("y_label", "")),
        )
    if t == "funnel":
        raw = data.get("stages") or []
        stages = _conv(raw, 2, _safe_str, _safe_float)
        return render_funnel(stages, width=width, label=label)
    if t == "calendar_heatmap":
        raw = data.get("data") or {}
        cal = (
            {_safe_str(k): _safe_int(v) for k, v in raw.items()}
            if isinstance(raw, dict)
            else {}
        )
        return render_calendar_heatmap(cal, label=label, cols=_safe_int(data.get("cols", 20), 20))
    if t == "word_cloud":
        raw = data.get("words") or []
        words = _conv(raw, 2, _safe_str, _safe_int)
        return render_word_cloud(
            words, max_words=_safe_int(data.get("max_words", 15), 15), label=label
        )
    if t == "mini_ring":
        return render_mini_ring(_safe_float(data.get("ratio", 0)), label=label)

    # ---------- CODING (30) ----------
    if t == "code_coverage":
        raw = data.get("files") or []
        files = _conv(raw, 2, _safe_str, _safe_float)
        return render_code_coverage(
            files,
            width=width,
            label=label,
            threshold=_safe_float(data.get("threshold", 0.8), 0.8),
        )
    if t == "complexity_heat":
        raw = data.get("functions") or []
        fns = _conv(raw, 2, _safe_str, _safe_int)
        return render_complexity_heat(
            fns, width=_safe_int(data.get("cell_width", 3), 3), label=label
        )
    if t == "diff_summary":
        raw = data.get("files") or []
        files = [
            (_safe_str(_pair(f, 3)[0]), _safe_int(_pair(f, 3)[1]), _safe_int(_pair(f, 3)[2]))
            for f in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_diff_summary(files, width=width, label=label)
    if t == "test_results":
        raw = data.get("suites") or []
        suites = []
        if isinstance(raw, (list, tuple)):
            for s in raw:
                p = _pair(s, 2)
                inner = p[1] if isinstance(p[1], dict) else {}
                safe = {_safe_str(k): _safe_int(v) for k, v in inner.items()}
                suites.append((_safe_str(p[0]), safe))
        return render_test_results(suites, label=label)
    if t == "dependency_graph":
        raw_deps = data.get("deps") or {}
        deps = (
            {_safe_str(k): [_safe_str(x) for x in v] for k, v in raw_deps.items()}
            if isinstance(raw_deps, dict)
            else {}
        )
        return render_dependency_graph(
            _safe_str(data.get("root", "")),
            deps,
            max_depth=_safe_int(data.get("max_depth", 3), 3),
            label=label,
        )
    if t == "file_size_bars":
        raw = data.get("files") or []
        files = _conv(raw, 2, _safe_str, _safe_int)
        return render_file_size_bars(
            files, width=width, label=label, unit=_safe_str(data.get("unit", "LOC"), "LOC")
        )
    if t == "git_timeline":
        raw = data.get("commits") or []
        commits = [
            (_safe_str(_pair(c, 3)[0]), _safe_str(_pair(c, 3)[1]), _safe_int(_pair(c, 3)[2]))
            for c in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_git_timeline(commits, width=width, label=label)
    if t == "error_rate":
        raw = data.get("counts") or []
        counts = [_safe_int(c) for c in raw] if isinstance(raw, (list, tuple)) else []
        return render_error_rate(counts, width=width, label=label)
    if t == "perf_benchmark":
        raw = data.get("benchmarks") or []
        benches = [
            (_safe_str(_pair(b, 3)[0]), _safe_float(_pair(b, 3)[1]), _safe_float(_pair(b, 3)[2]))
            for b in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_perf_benchmark(benches, width=width, label=label)
    if t == "api_latency":
        raw = data.get("endpoints") or []
        eps = [
            (_safe_str(_pair(e, 3)[0]), _safe_float(_pair(e, 3)[1]), _safe_float(_pair(e, 3)[2]))
            for e in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_api_latency(eps, width=width, label=label)
    if t == "build_pipeline":
        raw = data.get("stages") or []
        stages = [
            (_safe_str(_pair(s, 3)[0]), _safe_str(_pair(s, 3)[1]), _safe_float(_pair(s, 3)[2]))
            for s in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_build_pipeline(stages, label=label)
    if t == "security_scan":
        raw = data.get("vulns") or []
        vulns = [
            (_safe_str(_pair(v, 3)[0]), _safe_str(_pair(v, 3)[1]), _safe_str(_pair(v, 3)[2]))
            for v in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_security_scan(vulns, label=label)
    if t == "code_churn":
        raw = data.get("files") or []
        files = [
            (_safe_str(_pair(f, 3)[0]), _safe_int(_pair(f, 3)[1]), _safe_int(_pair(f, 3)[2]))
            for f in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_code_churn(files, width=width, label=label)
    if t == "db_schema":
        raw = data.get("tables") or {}
        tables = (
            {_safe_str(k): [_safe_str(c) for c in v] for k, v in raw.items()}
            if isinstance(raw, dict)
            else {}
        )
        return render_db_schema(tables, label=label)
    if t == "memory_profile":
        raw_h = data.get("heap") or []
        heap = [_safe_float(x) for x in raw_h] if isinstance(raw_h, (list, tuple)) else []
        raw_s = data.get("stack") or []
        stack = ([_safe_float(x) for x in raw_s]
                 if isinstance(raw_s, (list, tuple)) and raw_s else None)
        return render_memory_profile(heap, stack=stack, width=width, label=label)
    if t == "flame_chart":
        raw = data.get("frames") or []
        frames = [
            (_safe_str(_pair(f, 3)[0]), _safe_float(_pair(f, 3)[1]), _safe_int(_pair(f, 3)[2]))
            for f in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_flame_chart(frames, width=width, label=label)
    if t == "deploy_status":
        raw = data.get("envs") or []
        envs = [
            (_safe_str(_pair(e, 3)[0]), _safe_str(_pair(e, 3)[1]), _safe_str(_pair(e, 3)[2]))
            for e in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_deploy_status(envs, label=label)
    if t == "feature_flags":
        raw = data.get("flags") or []
        flags = [
            (_safe_str(_pair(f, 3)[0]), bool(_pair(f, 3)[1]), _safe_str(_pair(f, 3)[2]))
            for f in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_feature_flags(flags, label=label)
    if t == "package_versions":
        raw = data.get("packages") or []
        pkgs = [
            (_safe_str(_pair(p, 3)[0]), _safe_str(_pair(p, 3)[1]), _safe_str(_pair(p, 3)[2]))
            for p in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_package_versions(pkgs, label=label)
    if t == "log_density":
        raw = data.get("log_counts") or {}
        logs = (
            {_safe_str(k): [_safe_int(x) for x in v] for k, v in raw.items()}
            if isinstance(raw, dict)
            else {}
        )
        return render_log_density(logs, width=_safe_int(data.get("cell_width", 3), 3), label=label)
    if t == "duplication":
        raw = data.get("duplicates") or []
        dups = [
            (_safe_str(_pair(d, 3)[0]), _safe_str(_pair(d, 3)[1]), _safe_int(_pair(d, 3)[2]))
            for d in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_duplication(dups, label=label)
    if t == "refactor_progress":
        raw = data.get("metrics") or []
        metrics = [
            (_safe_str(_pair(m, 3)[0]), _safe_int(_pair(m, 3)[1]), _safe_int(_pair(m, 3)[2]))
            for m in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_refactor_progress(metrics, width=width, label=label)
    if t == "endpoint_map":
        raw = data.get("routes") or []
        routes = [
            (_safe_str(_pair(r, 3)[0]), _safe_str(_pair(r, 3)[1]), _safe_str(_pair(r, 3)[2]))
            for r in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_endpoint_map(routes, label=label)
    if t == "cache_stats":
        raw = data.get("caches") or []
        caches = [
            (_safe_str(_pair(c, 3)[0]), _safe_int(_pair(c, 3)[1]), _safe_int(_pair(c, 3)[2]))
            for c in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_cache_stats(caches, width=width, label=label)
    if t == "concurrency":
        raw = data.get("tasks") or []
        tasks = _conv(raw, 3, _safe_str, _safe_float, _safe_float)
        return render_concurrency(
            tasks, width=width, total=_safe_float(data.get("total", 0)), label=label
        )
    if t == "gc_pressure":
        raw = data.get("events") or []
        events = [
            (_safe_str(_pair(e, 3)[0]), _safe_float(_pair(e, 3)[1]), _safe_float(_pair(e, 3)[2]))
            for e in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_gc_pressure(events, width=width, label=label)
    if t == "network_waterfall":
        raw = data.get("requests") or []
        reqs = [
            (
                _safe_str(_pair(r, 4)[0]),
                _safe_float(_pair(r, 4)[1]),
                _safe_float(_pair(r, 4)[2]),
                _safe_str(_pair(r, 4)[3]),
            )
            for r in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_network_waterfall(reqs, width=width, label=label)
    if t == "queue_depth":
        raw = data.get("queues") or []
        queues = [
            (_safe_str(_pair(q, 3)[0]), _safe_int(_pair(q, 3)[1]), _safe_int(_pair(q, 3)[2]))
            for q in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_queue_depth(queues, width=width, label=label)
    if t == "error_matrix":
        raw = data.get("data") or []
        mat = ([[_safe_int(v) for v in row]
                for row in raw if isinstance(row, (list, tuple))]
               if isinstance(raw, (list, tuple)) else [])
        return render_error_matrix(
            mat,
            _conv(data.get("row_labels"), 1, _safe_str),
            _conv(data.get("col_labels"), 1, _safe_str),
            width=_safe_int(data.get("cell_width", 3), 3),
            label=label,
        )
    if t == "review_progress":
        raw = data.get("reviews") or []
        reviews = [
            (
                _safe_str(_pair(r, 4)[0]),
                _safe_str(_pair(r, 4)[1]),
                _safe_int(_pair(r, 4)[2]),
                _safe_int(_pair(r, 4)[3]),
            )
            for r in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_review_progress(reviews, label=label)

    # ---------- GENERAL (40) ----------
    if t == "sentiment_gauge":
        return render_sentiment_gauge(
            _safe_float(data.get("positive", 0)),
            _safe_float(data.get("neutral", 0)),
            _safe_float(data.get("negative", 0)),
            label=label,
        )
    if t == "word_count":
        return render_word_count(_safe_str(data.get("text", "")), label=label)
    if t == "reading_progress":
        return render_reading_progress(
            _safe_int(data.get("current_page", 0)),
            _safe_int(data.get("total_pages", 0)),
            width=width,
            label=label,
            book_title=_safe_str(data.get("book_title", "")),
        )
    if t == "mood_tracker":
        raw = data.get("moods") or []
        moods = _conv(raw, 2, _safe_str, _safe_str)
        return render_mood_tracker(moods, label=label)
    if t == "habit_tracker":
        raw = data.get("habits") or []
        habits = [
            (_safe_str(_pair(h)[0]), [bool(x) for x in (_pair(h, 2)[1] or [])])
            for h in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_habit_tracker(habits, label=label)
    if t == "task_priority":
        raw = data.get("tasks") or []
        tasks = [
            (_safe_str(_pair(tk, 3)[0]), _safe_str(_pair(tk, 3)[1]), _safe_str(_pair(tk, 3)[2]))
            for tk in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_task_priority(tasks, label=label)
    if t == "meeting_agenda":
        raw = data.get("items") or []
        items = [
            (_safe_str(_pair(i, 3)[0]), _safe_int(_pair(i, 3)[1]), _safe_str(_pair(i, 3)[2]))
            for i in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_meeting_agenda(items, label=label)
    if t == "budget_tracker":
        raw = data.get("categories") or []
        cats = [
            (_safe_str(_pair(c, 3)[0]), _safe_float(_pair(c, 3)[1]), _safe_float(_pair(c, 3)[2]))
            for c in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_budget_tracker(
            cats,
            width=width,
            label=label,
            currency=_safe_str(data.get("currency", "$"), "$"),
        )
    if t == "expense_breakdown":
        raw = data.get("categories") or []
        cats = _conv(raw, 2, _safe_str, _safe_float)
        return render_expense_breakdown(
            cats, width=width, label=label, currency=_safe_str(data.get("currency", "$"), "$")
        )
    if t == "weekly_schedule":
        raw = data.get("schedule") or {}
        sched = (
            {_safe_str(k): [_safe_str(x) for x in v] for k, v in raw.items()}
            if isinstance(raw, dict)
            else {}
        )
        return render_weekly_schedule(sched, label=label)
    if t == "countdown":
        return render_countdown(
            _safe_str(data.get("event", "")),
            _safe_int(data.get("days", 0)),
            hours=_safe_int(data.get("hours", 0)),
            minutes=_safe_int(data.get("minutes", 0)),
        )
    if t == "star_rating":
        return render_star_rating(
            _safe_float(data.get("rating", 0)),
            max_rating=_safe_float(data.get("max_rating", 5.0), 5.0),
            label=label,
            count=_safe_int(data.get("count", 0)),
        )
    if t == "poll_results":
        raw = data.get("options") or []
        options = _conv(raw, 2, _safe_str, _safe_int)
        return render_poll_results(options, width=width, label=label)
    if t == "survey_matrix":
        raw = data.get("questions") or []
        questions = [
            (_safe_str(_pair(q)[0]), [_safe_int(x) for x in (_pair(q, 2)[1] or [])])
            for q in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_survey_matrix(
            questions,
            scale_labels=data.get("scale_labels"),
            label=label,
        )
    if t == "decision_matrix":
        raw = data.get("options") or []
        options = [
            (_safe_str(_pair(o)[0]), [_safe_float(x) for x in (_pair(o, 2)[1] or [])])
            for o in raw
        ] if isinstance(raw, (list, tuple)) else []
        raw_w = data.get("weights")
        weights = [_safe_float(w) for w in raw_w] if isinstance(raw_w, (list, tuple)) else None
        return render_decision_matrix(
            options,
            _conv(data.get("criteria"), 1, _safe_str),
            weights=weights,
            label=label,
        )
    if t == "pros_cons":
        return render_pros_cons(
            _conv(data.get("pros"), 1, _safe_str),
            _conv(data.get("cons"), 1, _safe_str),
            label=label,
        )
    if t == "progress_wheel":
        return render_progress_wheel(
            _safe_float(data.get("ratio", 0)), size=_safe_int(data.get("size", 5), 5), label=label
        )
    if t == "fitness_stats":
        raw = data.get("workouts") or []
        workouts = [
            (_safe_str(_pair(w, 3)[0]), _safe_float(_pair(w, 3)[1]), _safe_float(_pair(w, 3)[2]))
            for w in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_fitness_stats(workouts, width=width, label=label)
    if t == "recipe_steps":
        raw = data.get("steps") or []
        return render_recipe_steps(
            [_safe_str(s) for s in raw] if isinstance(raw, (list, tuple)) else [], label=label
        )
    if t == "checklist":
        raw = data.get("items") or []
        items = _conv(raw, 2, _safe_str, bool)
        return render_checklist(items, label=label)
    if t == "travel_itinerary":
        raw = data.get("days") or []
        days = [
            (_safe_str(_pair(d)[0]), [_safe_str(x) for x in (_pair(d, 2)[1] or [])])
            for d in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_travel_itinerary(days, label=label)
    if t == "study_progress":
        raw = data.get("topics") or []
        topics = _conv(raw, 2, _safe_str, _safe_float)
        return render_study_progress(topics, width=width, label=label)
    if t == "flashcard_scores":
        raw = data.get("decks") or []
        decks = [
            (
                _safe_str(_pair(d, 4)[0]),
                _safe_int(_pair(d, 4)[1]),
                _safe_int(_pair(d, 4)[2]),
                _safe_int(_pair(d, 4)[3]),
            )
            for d in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_flashcard_scores(decks, label=label)
    if t == "quiz_results":
        raw = data.get("questions") or []
        questions = _conv(raw, 2, _safe_str, bool)
        return render_quiz_results(questions, label=label)
    if t == "todo_board":
        raw = data.get("columns") or []
        cols = [
            (_safe_str(_pair(c)[0]), [_safe_str(x) for x in (_pair(c, 2)[1] or [])])
            for c in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_todo_board(cols, label=label)
    if t == "price_comparison":
        raw = data.get("products") or []
        products = [
            (_safe_str(_pair(p, 3)[0]), _safe_float(_pair(p, 3)[1]), _safe_float(_pair(p, 3)[2]))
            for p in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_price_comparison(
            products,
            width=width,
            label=label,
            currency=_safe_str(data.get("currency", "$"), "$"),
        )
    if t == "review_summary":
        raw = data.get("ratings") or {}
        ratings = (
            {_safe_int(k): _safe_int(v) for k, v in raw.items()}
            if isinstance(raw, dict)
            else {}
        )
        return render_review_summary(ratings, label=label)
    if t == "mind_map":
        raw_b = data.get("branches") or {}
        branches = (
            {_safe_str(k): [_safe_str(x) for x in v] for k, v in raw_b.items()}
            if isinstance(raw_b, dict)
            else {}
        )
        return render_mind_map(
            _safe_str(data.get("root", "")),
            branches,
            label=label,
        )
    if t == "contact_card":
        raw_f = data.get("fields") or {}
        fields = (
            {_safe_str(k): _safe_str(v) for k, v in raw_f.items()}
            if isinstance(raw_f, dict)
            else {}
        )
        return render_contact_card(
            _safe_str(data.get("name", "")),
            fields,
            label=label,
        )
    if t == "gratitude_log":
        raw = data.get("entries") or []
        entries = _conv(raw, 2, _safe_str, _safe_str)
        return render_gratitude_log(entries, label=label)
    if t == "water_intake":
        return render_water_intake(
            _safe_int(data.get("glasses", 0)),
            goal=_safe_int(data.get("goal", 8), 8),
            label=label,
        )
    if t == "sleep_tracker":
        raw = data.get("nights") or []
        nights = [
            (_safe_str(_pair(n, 3)[0]), _safe_float(_pair(n, 3)[1]), _safe_float(_pair(n, 3)[2]))
            for n in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_sleep_tracker(nights, width=width, label=label)
    if t == "meditation_log":
        raw = data.get("sessions") or []
        sessions = _conv(raw, 2, _safe_str, _safe_float)
        return render_meditation_log(sessions, width=width, label=label)
    if t == "mood_timeline":
        raw = data.get("moods") or []
        moods = _conv(raw, 2, _safe_str, _safe_int)
        return render_mood_timeline(moods, label=label)
    if t == "life_balance":
        raw = data.get("areas") or []
        areas = _conv(raw, 2, _safe_str, _safe_float)
        return render_life_balance(areas, size=_safe_int(data.get("size", 9), 9), label=label)
    if t == "savings_goal":
        return render_savings_goal(
            _safe_float(data.get("current", 0)),
            _safe_float(data.get("target", 0)),
            width=width,
            label=label,
            currency=_safe_str(data.get("currency", "$"), "$"),
        )
    if t == "workout_plan":
        raw = data.get("days") or []
        days = [
            (_safe_str(_pair(d, 3)[0]), _safe_str(_pair(d, 3)[1]), bool(_pair(d, 3)[2]))
            for d in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_workout_plan(days, label=label)
    if t == "reading_list":
        raw = data.get("books") or []
        books = [
            (_safe_str(_pair(b, 3)[0]), _safe_str(_pair(b, 3)[1]), _safe_float(_pair(b, 3)[2]))
            for b in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_reading_list(books, width=_safe_int(data.get("width", 15), 15), label=label)
    if t == "wishlist":
        raw = data.get("items") or []
        items = [
            (_safe_str(_pair(i, 3)[0]), _safe_float(_pair(i, 3)[1]), _safe_str(_pair(i, 3)[2]))
            for i in raw
        ] if isinstance(raw, (list, tuple)) else []
        return render_wishlist(
            items,
            width=_safe_int(data.get("width", 15), 15),
            label=label,
            currency=_safe_str(data.get("currency", "$"), "$"),
        )
    if t == "date_countdown":
        return render_date_countdown(
            _safe_str(data.get("event", "")),
            _safe_int(data.get("days_remaining", 0)),
            total_days=_safe_int(data.get("total_days", 365), 365),
            width=width,
            label=label,
        )

    # Unknown type: fail-open with a graceful fallback, never raise.
    return (
        f"{label or 'Visual'}\n"
        f"  ┌{'─' * 28}┐\n"
        f"  │ ⚠ Unknown visual type      │\n"
        f"  │   {str(viz_type)[:24]:<24} │\n"
        f"  │                            │\n"
        f"  │ Available: 101 types       │\n"
        f"  │ school visualize --list    │\n"
        f"  └{'─' * 28}┘"
    )


def render_visual(
    viz_type: str,
    data: dict[str, Any] | None = None,
    label: str = "",
    width: int = 20,
) -> str:
    """Render any School visual by name.

    FAIL-OPEN: never raises. On any error or unknown type, returns a graceful
    fallback card so the agent always gets usable output. This is the single
    public entry point used by the bridge, CLI, MCP, and TS plugin.
    """
    try:
        return _render_visual_impl(viz_type, data, label, width)
    except Exception as exc:  # noqa: BLE001 — fail-open by design
        name = _safe_str(label) or _safe_str(viz_type) or "Visual"
        return (
            f"{name}\n"
            f"  ┌{'─' * 28}┐\n"
            f"  │ ⚠ Render error (recovering) │\n"
            f"  │   {str(exc)[:24]:<24} │\n"
            f"  │                            │\n"
            f"  │ Visuals always available   │\n"
            f"  │ school visualize --list    │\n"
            f"  └{'─' * 28}┘"
        )


# All known type names (for enumeration / validation)
VISUAL_TYPES = [
    # Universal (31)
    "sparkline", "heatmap", "donut", "radar", "gauge", "timeline", "tree",
    "flow", "spinner", "spinner_seq", "waterfall", "braille_chart", "subcell_bar",
    "status_matrix", "network", "dashboard", "gradient", "emoji_status",
    "comparison", "bar_chart", "histogram", "stats_box", "delta", "kanban",
    "kpi", "pie", "scatter", "funnel", "calendar_heatmap", "word_cloud",
    "mini_ring",
    # Coding (30)
    "code_coverage", "complexity_heat", "diff_summary", "test_results",
    "dependency_graph", "file_size_bars", "git_timeline", "error_rate",
    "perf_benchmark", "api_latency", "build_pipeline", "security_scan",
    "code_churn", "db_schema", "memory_profile", "flame_chart", "deploy_status",
    "feature_flags", "package_versions", "log_density", "duplication",
    "refactor_progress", "endpoint_map", "cache_stats", "concurrency",
    "gc_pressure", "network_waterfall", "queue_depth", "error_matrix",
    "review_progress",
    # General (40)
    "sentiment_gauge", "word_count", "reading_progress", "mood_tracker",
    "habit_tracker", "task_priority", "meeting_agenda", "budget_tracker",
    "expense_breakdown", "weekly_schedule", "countdown", "star_rating",
    "poll_results", "survey_matrix", "decision_matrix", "pros_cons",
    "progress_wheel", "fitness_stats", "recipe_steps", "checklist",
    "travel_itinerary", "study_progress", "flashcard_scores", "quiz_results",
    "todo_board", "price_comparison", "review_summary", "mind_map",
    "contact_card", "gratitude_log", "water_intake", "sleep_tracker",
    "meditation_log", "mood_timeline", "life_balance", "savings_goal",
    "workout_plan", "reading_list", "wishlist", "date_countdown",
]
