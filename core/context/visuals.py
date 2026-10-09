"""Universal terminal visualizations — 28+ chart types for any agent, any domain.

Renders pure-Unicode output (no ANSI required) so it works in:
  * CLI terminals (optional ANSI colors)
  * OpenCode tool output panels
  * Any AI agent text interface (coding, writing, research, data, ops, …)
  * Markdown-rendered panels

Visual types:
  1. sparkline           — ▁▂▃▄▅▆▇█ trend lines
  2. heatmap             — ░▒▓█ 2D intensity grid
  3. donut / ring        — ◔◕● circular progress
  4. radar / spider      — multi-axis polygon
  5. gauge / meter       — threshold needle
  6. timeline / gantt    — workflow phases
  7. tree                — hierarchical branches
  8. flow / sankey       — flow paths
  9. spinner frames      — ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ animation
  10. waterfall          — cumulative +/- bars
  11. braille chart      — high-density 2×4 dot plot
  12. sub-cell bar       — ▏▎▍▌▋▊▉ precision fill
  13. status matrix      — grid of state cells
  14. network graph      — node-edge connections
  15. dashboard          — multi-panel layout
  16. gradient bar       — smooth density ramp
  17. emoji status       — cross-platform indicators
  18. comparison table   — markdown table with winner highlight
  19. bar chart          — horizontal labeled bars
  20. histogram          — frequency distribution bins
  21. stats box          — 5-number summary (min/Q1/med/Q3/max)
  22. delta arrows       — ↑↓→ change indicators with magnitude
  23. kanban board       — multi-column task board
  24. KPI / big number   — large metric display
  25. pie chart          — segmented pie (block chars)
  26. scatter plot       — ASCII point cloud
  27. funnel             — decreasing conversion stages
  28. calendar heatmap   — GitHub-style contribution grid
  29. word cloud         — frequency-weighted text
  30. progress ring bar  — mini inline donut
"""

from __future__ import annotations

import math
from typing import Any

from core.context.visual_dispatch import harden

# ── Character sets ──────────────────────────────────────────────────────────

SPARK_CHARS = "▁▂▃▄▅▆▇█"
SPARK_REV = "█▇▆▅▄▃▂▁"
DENSITY = " ░▒▓█"
PARTIAL = " ▏▎▍▌▋▊▉█"
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SPINNER_CLASSIC = "|/-\\"
DONUT = "○◔◑◕●"
ARROW_R = "→"
ARROW_L = "←"

# Braille dot patterns (2×4 per cell)
BRAILLE_BASE = 0x2800
BRAILLE_DOTS = [
    [0x01, 0x08],
    [0x02, 0x10],
    [0x04, 0x20],
    [0x40, 0x80],
]


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# ── 1. Sparkline ────────────────────────────────────────────────────────────

def render_sparkline(
    values: list[float], width: int = 0, label: str = ""
) -> str:
    """Trend sparkline: ``▁▃▅█▆▄▂``.  *width* resamples; 0 = one char per value."""
    if not values:
        return f"{label} (no data)" if label else "(no data)"
    data = values
    if width > 0 and width != len(values):
        data = _resample(values, width)
    lo, hi = min(data), max(data)
    rng = hi - lo or 1.0
    chars = []
    for v in data:
        idx = int((v - lo) / rng * (len(SPARK_CHARS) - 1))
        chars.append(SPARK_CHARS[idx])
    spark = "".join(chars)
    return f"{label} {spark}" if label else spark


def _resample(values: list[float], width: int) -> list[float]:
    if width <= 0 or not values:
        return values
    if width >= len(values):
        return list(values)
    step = (len(values) - 1) / (width - 1)
    return [values[round(i * step)] for i in range(width)]


# ── 2. Heatmap ─────────────────────────────────────────────────────────────

def render_heatmap(
    grid: list[list[float]],
    col_labels: list[str] | None = None,
    row_labels: list[str] | None = None,
    width: int = 3,
) -> str:
    """2D intensity grid using density chars ░▒▓█."""
    if not grid:
        return "(no data)"
    flat = [v for row in grid for v in row]
    lo, hi = min(flat), max(flat)
    rng = hi - lo or 1.0
    lines = []
    col_w = max((len(str(c)) for c in (col_labels or [])), default=width)
    row_w = max((len(str(r)) for r in (row_labels or [])), default=3)

    if col_labels:
        header = " " * row_w + "  "
        for cl in col_labels:
            header += f"{cl:>{col_w}} "
        lines.append(header)

    for ri, row in enumerate(grid):
        rl = (row_labels[ri] if row_labels and ri < len(row_labels) else "")
        cells = ""
        for v in row:
            idx = int((v - lo) / rng * (len(DENSITY) - 1))
            char = DENSITY[idx]
            cells += char * width + " "
        lines.append(f"{rl:<{row_w}}  {cells}")
    return "\n".join(lines)


# ── 3. Donut / Ring chart ──────────────────────────────────────────────────

def render_donut(
    ratio: float, size: int = 5, label: str = "", show_pct: bool = True
) -> str:
    """Circular progress using ◔◕●.  *size* = ring diameter in chars."""
    r = _clamp(ratio)
    diameter = max(3, size | 1)  # force odd
    cx = cy = diameter // 2
    filled_frac = r
    lines = []
    for y in range(diameter):
        row = ""
        for x in range(diameter):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy * 4)  # ellipse
            if dist > diameter / 2 + 0.3:
                row += " "
            elif dist > diameter / 2 - 0.8:
                angle = (math.atan2(dy * 2, dx) / (2 * math.pi)) + 0.5
                if angle <= filled_frac:
                    row += "●"
                else:
                    row += "○"
            else:
                if filled_frac >= 1.0:
                    row += "●"
                else:
                    row += "◌"
        lines.append(row)
    pct = f" {r * 100:.0f}%" if show_pct else ""
    body = "\n".join(lines)
    if label:
        return f"{label}\n{body}{pct}"
    return f"{body}{pct}"


# ── 4. Radar / Spider chart ────────────────────────────────────────────────

def render_radar(
    axes: list[tuple[str, float]], size: int = 11, max_val: float = 1.0
) -> str:
    """Multi-axis radar.  ``axes = [('speed', 0.8), ('acc', 0.6), ...]``."""
    if not axes:
        return "(no data)"
    n = len(axes)
    cx = cy = size // 2
    # Build grid
    grid = [[" "] * size for _ in range(size)]
    # Draw axis lines
    for i, (_name, val) in enumerate(axes):
        angle = (2 * math.pi * i / n) - math.pi / 2
        # Draw axis line to edge
        for t in range(size // 2):
            x = int(cx + math.cos(angle) * t)
            y = int(cy + math.sin(angle) * t * 0.5)
            if 0 <= x < size and 0 <= y < size and grid[y][x] == " ":
                grid[y][x] = "·"
        # Draw value point
        r = _clamp(val / max_val) * (size / 2 - 1)
        x = int(cx + math.cos(angle) * r)
        y = int(cy + math.sin(angle) * r * 0.5)
        if 0 <= x < size and 0 <= y < size:
            grid[y][x] = "●"
    # Draw center
    grid[cy][cx] = "┼"
    body = "\n".join("".join(row) for row in grid)
    # Legend
    legend = "  ".join(f"{name}:{val:.0%}" for name, val in axes)
    return f"{body}\n{legend}"


# ── 5. Gauge / Meter ───────────────────────────────────────────────────────

def render_gauge(
    value: float,
    max_val: float = 1.0,
    width: int = 30,
    label: str = "",
    thresholds: tuple[float, float] = (0.6, 0.85),
) -> str:
    """Gauge with threshold zones: green / yellow / red."""
    r = _clamp(value / max_val) if max_val else 0.0
    filled = round(r * width)
    # Threshold markers
    zone_lo, zone_hi = thresholds
    bar = ""
    for i in range(width):
        pos = (i + 1) / width
        if i < filled:
            if pos >= zone_hi:
                bar += "█"  # red zone
            elif pos >= zone_lo:
                bar += "▓"  # yellow zone
            else:
                bar += "▒"  # green zone
        else:
            bar += "░"
    pct = f"{r * 100:.0f}%"
    zone = "LOW" if r < zone_lo else ("MED" if r < zone_hi else "HIGH")
    prefix = f"{label} " if label else ""
    return f"{prefix}┌{bar}┐ {pct} [{zone}]"


# ── 6. Timeline / Gantt ────────────────────────────────────────────────────

def render_timeline(
    phases: list[tuple[str, float, float]],
    width: int = 30,
    total: float = 0.0,
    label: str = "",
) -> str:
    """Gantt-style timeline.  ``phases = [(name, start, end), ...]``."""
    if not phases:
        return "(no data)"
    if total <= 0:
        total = max(e for _, _, e in phases) or 1.0
    name_w = max(len(n) for n, _, _ in phases)
    lines = []
    if label:
        lines.append(label)
    for name, start, end in phases:
        s = int(_clamp(start / total) * width)
        e = int(_clamp(end / total) * width)
        bar = "░" * s + "█" * max(1, e - s) + "░" * (width - e)
        dur = f"{end - start:.1f}s" if end - start >= 0.1 else ""
        lines.append(f"{name:<{name_w}} │{bar}│ {dur}")
    # Time axis
    axis = " " * name_w + " 0"
    axis += " " * (width - 4) + f"{total:.0f}"
    lines.append(axis)
    return "\n".join(lines)


# ── 7. Tree ────────────────────────────────────────────────────────────────

def render_tree(
    items: list[dict[str, Any]],
    indent: int = 0,
    prefix: str = "",
    connector: str = "├── ",
    last_connector: str = "└── ",
    child_indent: str = "│   ",
    last_child_indent: str = "    ",
) -> str:
    """Hierarchical tree.  Items: ``[{'name': 'x', 'children': [...]}]``."""
    if not items:
        return "(empty)"
    lines = []
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        conn = last_connector if is_last else connector
        name = item.get("name", item.get("label", "?"))
        badge = f"  [{item['badge']}]" if "badge" in item else ""
        lines.append(f"{prefix}{conn}{name}{badge}")
        children = item.get("children", [])
        if children:
            child_prefix = prefix + (last_child_indent if is_last else child_indent)
            lines.append(
                render_tree(
                    children,
                    prefix=child_prefix,
                    connector=connector,
                    last_connector=last_connector,
                    child_indent=child_indent,
                    last_child_indent=last_child_indent,
                )
            )
    return "\n".join(lines) or "(empty)"


# ── 8. Flow / Sankey ───────────────────────────────────────────────────────

def render_flow(
    nodes: list[str],
    flows: list[tuple[int, int, float]],
    width: int = 20,
    label: str = "",
) -> str:
    """Sankey-style flow diagram.  ``flows = [(from_idx, to_idx, weight)]``."""
    if not nodes or not flows:
        return "(no data)"
    max_w = max(w for _, _, w in flows) or 1.0
    lines = []
    if label:
        lines.append(label)
    node_w = max(len(n) for n in nodes)
    for fi, ti, weight in flows:
        bar_len = max(1, int((weight / max_w) * width))
        arrow = "═" * bar_len
        src_val = nodes[fi] if 0 <= fi < len(nodes) else "?"
        dst = nodes[ti] if 0 <= ti < len(nodes) else "?"
        src = f"{src_val:<{node_w}}"
        lines.append(f"{src} {ARROW_R}{arrow}→ {dst}  ({weight:.0f})")
    return "\n".join(lines)


# ── 9. Spinner ─────────────────────────────────────────────────────────────

def render_spinner(frame: int = 0, label: str = "", style: str = "braille") -> str:
    """Animated spinner frame.  Call repeatedly with incrementing *frame*."""
    frames = SPINNER_FRAMES if style == "braille" else SPINNER_CLASSIC
    char = frames[frame % len(frames)]
    return f"{char} {label}" if label else char


def render_spinner_seq(
    label: str = "", frames: int = 10, style: str = "braille"
) -> str:
    """Return all spinner frames as one line (for docs/demo)."""
    src = SPINNER_FRAMES if style == "braille" else SPINNER_CLASSIC
    try:
        n = frames if isinstance(frames, int) and frames > 0 else 1
    except Exception:  # noqa: BLE001
        n = 1
    return " ".join(src[i % len(src)] for i in range(n))


# ── 10. Waterfall ──────────────────────────────────────────────────────────

def render_waterfall(
    items: list[tuple[str, float]],
    width: int = 20,
    label: str = "",
) -> str:
    """Cumulative +/- waterfall chart."""
    if not items:
        return "(no data)"
    running = 0.0
    max_magnitude = max(abs(v) for _, v in items) or 1.0
    lines = []
    if label:
        lines.append(label)
    name_w = max(len(n) for n, _ in items)
    for name, delta in items:
        prev = running
        running += delta
        s = int(_clamp(min(prev, running) / max_magnitude, 0, 1) * width)
        e = int(_clamp(max(prev, running) / max_magnitude, 0, 1) * width)
        if delta >= 0:
            bar = "░" * s + "▓" * max(1, e - s) + "░" * (width - e)
        else:
            bar = "░" * s + "▒" * max(1, e - s) + "░" * (width - e)
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"{name:<{name_w}} │{bar}│ {sign}{delta:.0f} → {running:.0f}"
        )
    return "\n".join(lines)


# ── 11. Braille chart (high-density line plot) ─────────────────────────────

def render_braille_chart(
    series: list[list[float]],
    width: int = 16,
    height: int = 8,
    labels: list[str] | None = None,
) -> str:
    """High-density line plot using Braille 2×4 dot matrix."""
    if not series:
        return "(no data)"
    all_vals = [v for s in series for v in s]
    lo, hi = min(all_vals), max(all_vals)
    rng = hi - lo or 1.0

    pixel_w = width * 2
    pixel_h = height * 4
    canvas = [[0] * pixel_w for _ in range(pixel_h)]

    colors = [1, 2, 4]  # bit patterns per series
    for si, data in enumerate(series):
        pts = _resample(data, pixel_w)
        for x, v in enumerate(pts):
            y = int((v - lo) / rng * (pixel_h - 1))
            y = pixel_h - 1 - y  # flip
            canvas[y][x] |= colors[si % len(colors)]

    lines = []
    for row_y in range(0, pixel_h, 4):
        row = ""
        for col_x in range(0, pixel_w, 2):
            dot = 0
            for dy in range(4):
                for dx in range(2):
                    y, x = row_y + dy, col_x + dx
                    if y < pixel_h and x < pixel_w and canvas[y][x]:
                        dot |= BRAILLE_DOTS[dy][dx]
            row += chr(BRAILLE_BASE + dot)
        lines.append(row)

    if labels:
        legend = "  ".join(
            f"{SPARK_CHARS[i % len(SPARK_CHARS)]} {lb}"
            for i, lb in enumerate(labels)
        )
        lines.append(legend)
    return "\n".join(lines)


# ── 12. Sub-cell progress bar ──────────────────────────────────────────────

def render_subcell_bar(
    ratio: float,
    width: int = 20,
    label: str = "",
    fill_char: str = "█",
    empty_char: str = " ",
) -> str:
    """Precision progress bar with ▏▎▍▌▋▊▉ sub-cell resolution."""
    r = _clamp(ratio)
    whole = r * width
    full = int(whole)
    frac = whole - full
    part_idx = int(frac * 8)
    bar = fill_char * full + PARTIAL[part_idx]
    if full + (1 if part_idx > 0 else 0) < width:
        bar += empty_char * (width - full - (1 if part_idx > 0 else 0))
    pct = f"{r * 100:.1f}%"
    return f"{label} {bar} {pct}" if label else f"{bar} {pct}"


# ── 13. Status matrix ──────────────────────────────────────────────────────

_STATUS_MAP = {
    "ok": "●",
    "pass": "●",
    "done": "●",
    "running": "◐",
    "active": "◐",
    "pending": "○",
    "waiting": "○",
    "fail": "✕",
    "error": "✕",
    "blocked": "⊘",
    "skip": "◌",
    "warn": "⚠",
}


def render_status_matrix(
    items: list[tuple[str, str]],
    cols: int = 4,
    label: str = "",
) -> str:
    """Grid of status cells.  ``items = [(name, status), ...]``."""
    if not items:
        return "(no data)"
    cells = []
    for name, status in items:
        icon = _STATUS_MAP.get(status.lower(), "?")
        cells.append(f"{icon} {name}")
    cell_w = max(len(c) for c in cells) + 2
    lines = []
    if label:
        lines.append(label)
    for i in range(0, len(cells), cols):
        row = cells[i : i + cols]
        lines.append("  ".join(f"{c:<{cell_w}}" for c in row).rstrip())
    return "\n".join(lines)


# ── 14. Network graph ──────────────────────────────────────────────────────

def render_network(
    nodes: list[dict[str, Any]],
    edges: list[tuple[int, int]],
    size: int = 21,
    label: str = "",
) -> str:
    """Simple ASCII node-edge graph."""
    if not nodes:
        return "(no data)"
    n = len(nodes)
    # Position nodes on a circle
    positions = []
    cx = cy = size // 2
    rx = size // 2 - 1
    ry = size // 4
    for i in range(n):
        angle = (2 * math.pi * i / n) - math.pi / 2
        x = int(cx + math.cos(angle) * rx)
        y = int(cy + math.sin(angle) * ry)
        positions.append((x, y))

    grid = [[" "] * size for _ in range(size)]

    # Draw edges
    for a, b in edges:
        if a >= n or b >= n:
            continue
        x1, y1 = positions[a]
        x2, y2 = positions[b]
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        for t in range(steps + 1):
            x = x1 + (x2 - x1) * t // steps
            y = y1 + (y2 - y1) * t // steps
            if 0 <= x < size and 0 <= y < size and grid[y][x] == " ":
                grid[y][x] = "·"

    # Draw nodes
    for i, (x, y) in enumerate(positions):
        if 0 <= x < size and 0 <= y < size:
            grid[y][x] = str(i) if n <= 10 else "●"

    body = "\n".join("".join(row) for row in grid)
    legend = "  ".join(
        f"{i}:{nd.get('name', '?')}" for i, nd in enumerate(nodes[:8])
    )
    prefix = f"{label}\n" if label else ""
    return f"{prefix}{body}\n{legend}"


# ── 15. Dashboard ──────────────────────────────────────────────────────────

def render_dashboard(
    title: str,
    panels: list[tuple[str, str]],
    width: int = 50,
) -> str:
    """Multi-panel dashboard with borders."""
    try:
        width = int(width)
    except Exception:  # noqa: BLE001
        width = 50
    width = max(6, min(200, width))
    top = f"┌{'─' * (width - 2)}┐"
    bottom = f"└{'─' * (width - 2)}┘"
    title_line = f"│ {title:<{width - 4}} │"
    sep = f"├{'─' * (width - 2)}┤"
    lines = [top, title_line, sep]
    for name, content in panels:
        header = f"│ ◆ {name:<{width - 6}} │"
        lines.append(header)
        for content_line in content.split("\n"):
            padded = content_line[: width - 4]
            lines.append(f"│ {padded:<{width - 4}} │")
        lines.append(sep)
    lines[-1] = bottom
    return "\n".join(lines)


# ── 16. Gradient bar ───────────────────────────────────────────────────────

def render_gradient(
    ratio: float, width: int = 20, label: str = "", reverse: bool = False
) -> str:
    """Smooth density gradient bar."""
    r = _clamp(ratio)
    ramp = DENSITY if not reverse else DENSITY[::-1]
    filled = r * width
    chars = []
    for i in range(width):
        pos = i / max(1, width - 1)
        idx = int(pos * (len(ramp) - 1))
        if i < filled:
            chars.append(ramp[-1])
        else:
            chars.append(ramp[idx])
    bar = "".join(chars)
    pct = f"{r * 100:.0f}%"
    return f"{label} {bar} {pct}" if label else f"{bar} {pct}"


# ── 17. Emoji status ───────────────────────────────────────────────────────

_EMOJI_STATUS = {
    "success": "✅",
    "ok": "✅",
    "done": "✅",
    "pass": "✅",
    "running": "🔄",
    "active": "🔄",
    "progress": "🔄",
    "pending": "⏳",
    "waiting": "⏳",
    "warn": "⚠️",
    "warning": "⚠️",
    "error": "❌",
    "fail": "❌",
    "blocked": "🚫",
    "skip": "⏭️",
    "info": "ℹ️",
    "memory": "🧠",
    "skill": "🎯",
    "context": "📦",
    "learn": "📚",
    "goal": "🏁",
    "speed": "⚡",
    "save": "💰",
    "time": "🕐",
    "search": "🔍",
    "build": "🔧",
}


def render_emoji_status(
    items: list[tuple[str, str]],
    cols: int = 3,
) -> str:
    """Cross-platform emoji status grid."""
    if not items:
        return "(no data)"
    cells = []
    for name, status in items:
        icon = _EMOJI_STATUS.get(status.lower(), "❓")
        cells.append(f"{icon} {name}")
    cell_w = max(len(c) for c in cells) + 2
    lines = []
    for i in range(0, len(cells), cols):
        row = cells[i : i + cols]
        lines.append("  ".join(f"{c:<{cell_w}}" for c in row).rstrip())
    return "\n".join(lines)


# ── Bonus: Comparison table ────────────────────────────────────────────────

def render_comparison(
    rows: list[dict[str, str]],
    columns: list[str] | None = None,
    winner_col: str | None = None,
) -> str:
    """Markdown-style comparison table with winner highlighting."""
    if not rows:
        return "(no data)"
    if columns is None:
        columns = list(rows[0].keys())
    col_w = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    header = "| " + " | ".join(f"{c:<{col_w[c]}}" for c in columns) + " |"
    sep = "|" + "|".join("─" * (col_w[c] + 2) for c in columns) + "|"
    lines = [header, sep]
    for row in rows:
        cells = []
        for c in columns:
            val = str(row.get(c, ""))
            marker = " ✓" if c == winner_col and val.startswith("✓") else ""
            cells.append(f"{val + marker:<{col_w[c]}}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ── 19. Bar chart (horizontal, labeled) ────────────────────────────────────

def render_bar_chart(
    items: list[tuple[str, float]],
    width: int = 30,
    label: str = "",
    show_values: bool = True,
) -> str:
    """Horizontal bar chart.  ``items = [('label', value), ...]``."""
    if not items:
        return "(no data)"
    max_val = max(abs(v) for _, v in items) or 1.0
    name_w = max(len(n) for n, _ in items)
    lines = []
    if label:
        lines.append(label)
    for name, val in items:
        bar_len = max(1, int(abs(val) / max_val * width))
        bar = "█" * bar_len
        suffix = f"  {val:.2f}" if show_values else ""
        lines.append(f"{name:<{name_w}} │{bar}│{suffix}")
    return "\n".join(lines)


# ── 20. Histogram ──────────────────────────────────────────────────────────

def render_histogram(
    values: list[float],
    bins: int = 10,
    width: int = 30,
    label: str = "",
) -> str:
    """Frequency distribution histogram with density bars."""
    if not values:
        return "(no data)"
    lo, hi = min(values), max(values)
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / step), bins - 1)
        counts[idx] += 1
    max_count = max(counts) or 1
    lines = []
    if label:
        lines.append(label)
    for i in range(bins):
        bin_lo = lo + i * step
        bin_hi = lo + (i + 1) * step
        bar_len = int(counts[i] / max_count * width)
        bar = "█" * bar_len
        range_str = f"[{bin_lo:.2f},{bin_hi:.2f})"
        lines.append(f"{range_str:>20} │{bar}│ {counts[i]}")
    return "\n".join(lines)


# ── 21. Stats box (5-number summary) ───────────────────────────────────────

def render_stats_box(
    values: list[float],
    label: str = "",
    width: int = 30,
) -> str:
    """Box plot with min / Q1 / median / Q3 / max."""
    if not values:
        return "(no data)"
    s = sorted(values)
    n = len(s)
    lo = s[0]
    hi = s[-1]
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    q1 = s[n // 4]
    q3 = s[3 * n // 4]
    rng = hi - lo or 1.0
    # Box position
    def _pos(v: float) -> int:
        return int((v - lo) / rng * width)

    p_q1, p_med, p_q3 = _pos(q1), _pos(med), _pos(q3)
    box = ["░"] * width
    for i in range(p_q1, min(p_q3 + 1, width)):
        box[i] = "█"
    if 0 <= p_med < width:
        box[p_med] = "│"
    # Whiskers
    if p_q1 > 0:
        box[0] = "├"
    if p_q3 < width - 1:
        box[width - 1] = "┤"
    body = "".join(box)
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  {body}")
    lines.append(f"  min={lo:.2f}  q1={q1:.2f}  med={med:.2f}  q3={q3:.2f}  max={hi:.2f}")
    return "\n".join(lines)


# ── 22. Delta arrows ───────────────────────────────────────────────────────

def render_delta(
    items: list[tuple[str, float, float]],
    label: str = "",
) -> str:
    """Change indicators with arrows.  ``items = [(name, old, new), ...]``."""
    if not items:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    name_w = max(len(n) for n, _, _ in items)
    for name, old, new in items:
        delta = new - old
        pct = delta / abs(old) * 100 if old != 0 else 0.0
        if delta > 0:
            arrow = "↑"
            sign = "+"
        elif delta < 0:
            arrow = "↓"
            sign = ""
        else:
            arrow = "→"
            sign = " "
        lines.append(
            f"{name:<{name_w}}  {arrow} {sign}{delta:.2f} ({sign}{pct:.1f}%)"
        )
    return "\n".join(lines)


# ── 23. Kanban board ───────────────────────────────────────────────────────

def render_kanban(
    columns: list[tuple[str, list[str]]],
    label: str = "",
    max_items: int = 5,
) -> str:
    """Multi-column kanban board.  ``columns = [(col_name, [card, ...]), ...]``."""
    if not columns:
        return "(no data)"
    col_w = max(max((len(c) for c in cards), default=2) for _, cards in columns)
    col_w = max(col_w, 4) + 2
    header_line = ""
    sep_line = ""
    for _name, _cards in columns:
        header_line += f"┌{'─' * col_w}┐ "
        sep_line += f"├{'─' * col_w}┤ "
    header_line = header_line.rstrip()
    sep_line = sep_line.rstrip()
    # Column names
    name_row = ""
    for name, _cards in columns:
        name_row += f"│ {name:<{col_w - 2}} │ "
    name_row = name_row.rstrip()
    # Card rows
    max_rows = max((len(cards) for _, cards in columns), default=0)
    max_rows = min(max_rows, max_items)
    card_rows = []
    for r in range(max_rows):
        row = ""
        for _name, cards in columns:
            card = cards[r] if r < len(cards) else ""
            row += f"│ {card:<{col_w - 2}} │ "
        card_rows.append(row.rstrip())
    # Empty rows to balance
    while len(card_rows) < 1:
        card_rows.append("")
    bottom = ""
    for _name, _cards in columns:
        bottom += f"└{'─' * col_w}┘ "
    bottom = bottom.rstrip()
    lines = []
    if label:
        lines.append(label)
    lines.append(header_line)
    lines.append(name_row)
    lines.append(sep_line)
    lines.extend(card_rows)
    lines.append(bottom)
    return "\n".join(lines)


# ── 24. KPI / Big number ──────────────────────────────────────────────────

_KPI_DIGITS = {
    "0": ["█▀█", "█ █", "█▄█"],
    "1": [" ▐█", "  █", " ▐█"],
    "2": ["▀▀█", "█▀ ", "█▄▄"],
    "3": ["▀▀█", " ▀█", "▀▀█"],
    "4": ["█ █", "███", "  █"],
    "5": ["█▀▀", "█▀▀", "█▄▄"],
    "6": ["█▀ ", "█▀█", "█▄█"],
    "7": ["▀▀█", "  █", "  █"],
    "8": ["█▀█", "█▀█", "█▄█"],
    "9": ["█▀█", "███", "  █"],
    ".": ["   ", "   ", "·  "],
    "-": ["   ", "▀▀▀", "   "],
    "%": ["█ █", " ▐▌", "█ █"],
    "+": ["   ", "▀█▀", "   "],
}


def render_kpi(
    value: str | float,
    label: str = "",
    suffix: str = "",
    trend: str = "",
) -> str:
    """Large KPI number display using ASCII art digits."""
    text = str(value) if not isinstance(value, float) else f"{value:.1f}"
    text += suffix
    rows = ["", "", ""]
    for ch in text:
        glyphs = _KPI_DIGITS.get(ch, ["███", "███", "███"])
        for i in range(3):
            rows[i] += glyphs[i] + " "
    lines = [r.rstrip() for r in rows]
    if label:
        lines.append(f"  {label}")
    if trend:
        lines.append(f"  {trend}")
    return "\n".join(lines)


# ── 25. Pie chart ──────────────────────────────────────────────────────────

_PIE_CHARS = "▓█"


def render_pie(
    segments: list[tuple[str, float]],
    size: int = 7,
    label: str = "",
) -> str:
    """Block-char pie chart.  ``segments = [(name, value), ...]``."""
    if not segments:
        return "(no data)"
    total = sum(abs(v) for _, v in segments) or 1.0
    fractions = [(name, v / total) for name, v in segments]
    diameter = max(5, size | 1)
    cx = cy = diameter // 2
    lines = []
    if label:
        lines.append(label)
    # Cumulative angles
    starts = []
    cum = 0.0
    for _name, frac in fractions:
        starts.append((cum, cum + frac))
        cum += frac
    for y in range(diameter):
        row = ""
        for x in range(diameter):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy * 4)
            if dist > diameter / 2 + 0.3:
                row += " "
                continue
            angle = (math.atan2(dy * 2, dx) / (2 * math.pi)) + 0.5
            for i, (s, e) in enumerate(starts):
                if s <= angle < e:
                    row += _PIE_CHARS[i % len(_PIE_CHARS)]
                    break
            else:
                row += "░"
        lines.append(row)
    # Legend
    for i, (name, frac) in enumerate(fractions):
        icon = _PIE_CHARS[i % len(_PIE_CHARS)]
        pct = f"{frac * 100:.1f}%"
        lines.append(f"  {icon} {name}: {pct}")
    return "\n".join(lines)


# ── 26. Scatter plot ───────────────────────────────────────────────────────

def render_scatter(
    points: list[tuple[float, float]],
    width: int = 30,
    height: int = 12,
    x_label: str = "",
    y_label: str = "",
) -> str:
    """ASCII scatter plot."""
    if not points:
        return "(no data)"
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    x_rng = x_hi - x_lo or 1.0
    y_rng = y_hi - y_lo or 1.0
    grid = [[" "] * width for _ in range(height)]
    for x, y in points:
        gx = int((x - x_lo) / x_rng * (width - 1))
        gy = height - 1 - int((y - y_lo) / y_rng * (height - 1))
        if 0 <= gx < width and 0 <= gy < height:
            grid[gy][gx] = "●"
    lines = []
    if y_label:
        lines.append(f"  {y_label}")
    for row in grid:
        lines.append("│" + "".join(row))
    lines.append("└" + "─" * width)
    if x_label:
        lines.append(f"  {x_label}")
    return "\n".join(lines)


# ── 27. Funnel ─────────────────────────────────────────────────────────────

def render_funnel(
    stages: list[tuple[str, float]],
    width: int = 30,
    label: str = "",
) -> str:
    """Decreasing funnel/conversion chart."""
    if not stages:
        return "(no data)"
    max_val = max(abs(v) for _, v in stages) or 1.0
    name_w = max(len(n) for n, _ in stages)
    lines = []
    if label:
        lines.append(label)
    for i, (name, val) in enumerate(stages):
        bar_len = max(1, int(abs(val) / max_val * width))
        bar = "█" * bar_len
        pct = f"{abs(val) / max_val * 100:.0f}%"
        if i > 0 and stages[i - 1][1] != 0:
            conv = abs(val) / abs(stages[i - 1][1]) * 100
            conv_str = f"  ↓{conv:.0f}%"
        else:
            conv_str = ""
        lines.append(f"{name:<{name_w}} │{bar}│ {pct}{conv_str}")
    return "\n".join(lines)


# ── 28. Calendar heatmap (GitHub-style) ────────────────────────────────────

def render_calendar_heatmap(
    data: dict[str, int],
    label: str = "",
    cols: int = 20,
) -> str:
    """GitHub-style contribution heatmap from ``{'YYYY-MM-DD': count}``."""
    if not data:
        return "(no data)"
    max_val = max(data.values()) or 1
    levels = " ░▒▓█"
    dates = sorted(data.keys())
    lines = []
    if label:
        lines.append(label)
    # Row labels (day of week abbreviated)
    day_labels = ["Mon", "Wed", "Fri"]
    row_lines = [""] * 7
    for col_idx, dt_str in enumerate(dates):
        try:
            from datetime import date

            y, m, d = map(int, dt_str.split("-"))
            dt = date(y, m, d)
            day = dt.weekday()
        except (ValueError, ImportError):
            day = col_idx % 7
        v = data.get(dt_str, 0)
        level = min(int(v / max_val * (len(levels) - 1)), len(levels) - 1)
        row_lines[day] += levels[level]
    for i, row in enumerate(row_lines):
        prefix = day_labels[i // 3] if i in (0, 2, 4) else "   "
        padded = row.ljust(cols)
        lines.append(f"{prefix} {padded}")
    # Legend
    legend = "  less " + "░▒▓█" + " more"
    lines.append(f"   {legend}")
    return "\n".join(lines)


# ── 29. Word cloud ─────────────────────────────────────────────────────────

def render_word_cloud(
    words: list[tuple[str, int]],
    max_words: int = 15,
    label: str = "",
) -> str:
    """Frequency-weighted word cloud (inline, size varies by count)."""
    if not words:
        return "(no data)"
    sorted_words = sorted(words, key=lambda x: x[1], reverse=True)[:max_words]
    max_count = sorted_words[0][1] or 1
    # Size tiers
    lines = []
    if label:
        lines.append(label)
    row = []
    row_len = 0
    for word, count in sorted_words:
        tier = count / max_count
        if tier > 0.7:
            display = f"████{word.upper()}████"
        elif tier > 0.4:
            display = f"██{word}██"
        elif tier > 0.15:
            display = f"▀{word}▀"
        else:
            display = word
        row.append(display)
        row_len += len(display) + 2
        if row_len > 60:
            lines.append("  ".join(row))
            row = []
            row_len = 0
    if row:
        lines.append("  ".join(row))
    return "\n".join(lines)


# ── 30. Mini progress ring ────────────────────────────────────────────────

def render_mini_ring(
    ratio: float,
    label: str = "",
) -> str:
    """Tiny inline donut/ring indicator (single line)."""
    r = _clamp(ratio)
    if r < 0.1:
        ring = "○"
    elif r < 0.3:
        ring = "◔"
    elif r < 0.5:
        ring = "◑"
    elif r < 0.7:
        ring = "◕"
    elif r < 0.9:
        ring = "●"
    else:
        ring = "◉"
    pct = f"{r * 100:.0f}%"
    if label:
        return f"{ring} {label} {pct}"
    return f"{ring} {pct}"


__all__ = [
    "render_sparkline",
    "render_heatmap",
    "render_donut",
    "render_radar",
    "render_gauge",
    "render_timeline",
    "render_tree",
    "render_flow",
    "render_spinner",
    "render_spinner_seq",
    "render_waterfall",
    "render_braille_chart",
    "render_subcell_bar",
    "render_status_matrix",
    "render_network",
    "render_dashboard",
    "render_gradient",
    "render_emoji_status",
    "render_comparison",
    "render_bar_chart",
    "render_histogram",
    "render_stats_box",
    "render_delta",
    "render_kanban",
    "render_kpi",
    "render_pie",
    "render_scatter",
    "render_funnel",
    "render_calendar_heatmap",
    "render_word_cloud",
    "render_mini_ring",
]

# Fail-open hardening: every render_* coerces hostile args and never raises.
harden(globals())
