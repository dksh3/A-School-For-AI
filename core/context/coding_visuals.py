"""Coding-agent visualizations — 30 specialized charts for dev workflows.

Pure Unicode output. Works in CLI, tool panels, any agent interface.

Types:
  1. code_coverage      — per-file test coverage bars
  2. complexity_heat    — cyclomatic complexity by function
  3. diff_summary       — +/- lines changed comparison
  4. test_results       — pass/fail/skip matrix
  5. dependency_graph   — import/require tree
  6. file_size_bars     — LOC/bytes comparison
  7. git_timeline       — commit history sparkline
  8. error_rate         — error frequency over time
  9. perf_benchmark     — before/after timing comparison
  10. api_latency       — endpoint response waterfall
  11. build_pipeline    — CI/CD stage status
  12. security_scan     — vulnerability severity matrix
  13. code_churn        — files changed frequency
  14. db_schema         — table/entity relationship map
  15. memory_profile    — heap/stack usage over time
  16. flame_chart       — CPU profile stacked bars
  17. deploy_status     — environment status matrix
  18. feature_flags     — on/off toggle display
  19. package_versions  — dependency version comparison
  20. log_density       — log level frequency heatmap
  21. duplication       — duplicate code block detection
  22. refactor_progress — before/after line counts
  23. endpoint_map      — REST API route tree
  24. cache_stats       — hit/miss rate bars
  25. concurrency       — async task overlap timeline
  26. gc_pressure       — garbage collection events
  27. network_waterfall — HTTP request timing
  28. queue_depth       — message queue backlog
  29. error_matrix      — errors by service/time grid
  30. review_progress   — code review status board
"""

from __future__ import annotations

from core.context.visual_dispatch import harden

DENSITY = " ░▒▓█"
PARTIAL = " ▏▎▍▌▋▊▉█"
BAR_FILL = "█"
BAR_EMPTY = "░"
ARROW = "→"

_STATUS = {
    "pass": "✓", "ok": "✓", "success": "✓", "done": "✓",
    "fail": "✗", "error": "✗", "broken": "✗",
    "skip": "○", "pending": "○", "waiting": "○",
    "warn": "⚠", "warning": "⚠",
    "run": "◐", "running": "◐", "active": "◐",
    "block": "⊘", "blocked": "⊘",
    "queue": "◌", "queued": "◌",
}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _bar(ratio: float, width: int, fill: str = BAR_FILL, empty: str = BAR_EMPTY) -> str:
    r = _clamp(ratio)
    filled = int(r * width)
    return fill * filled + empty * (width - filled)


# ── 1. Code coverage ────────────────────────────────────────────────────────

def render_code_coverage(
    files: list[tuple[str, float]],
    width: int = 20,
    label: str = "",
    threshold: float = 0.8,
) -> str:
    """Per-file coverage bars.  ``files = [(path, coverage_ratio), ...]``."""
    if not files:
        return "(no data)"
    name_w = max(len(n) for n, _ in files)
    lines = []
    if label:
        lines.append(label)
    for name, cov in files:
        bar = _bar(cov, width)
        pct = f"{cov * 100:.0f}%"
        flag = "✓" if cov >= threshold else "✗"
        lines.append(f"  {name:<{name_w}} │{bar}│ {pct} {flag}")
    total = sum(c for _, c in files) / len(files)
    lines.append(f"  {'AVG':<{name_w}} │{_bar(total, width)}│ {total * 100:.0f}%")
    return "\n".join(lines)


# ── 2. Complexity heat ─────────────────────────────────────────────────────

def render_complexity_heat(
    functions: list[tuple[str, int]],
    width: int = 3,
    label: str = "",
) -> str:
    """Cyclomatic complexity heat by function name."""
    if not functions:
        return "(no data)"
    max_c = max(c for _, c in functions) or 1
    lines = []
    if label:
        lines.append(label)
    name_w = max(len(n) for n, _ in functions)
    for name, comp in functions:
        level = min(int(comp / max_c * (len(DENSITY) - 1)), len(DENSITY) - 1)
        heat = DENSITY[level] * width
        risk = "LOW" if comp <= 5 else ("MED" if comp <= 10 else "HIGH")
        lines.append(f"  {name:<{name_w}} {heat} {comp:>3} [{risk}]")
    return "\n".join(lines)


# ── 3. Diff summary ─────────────────────────────────────────────────────────

def render_diff_summary(
    files: list[tuple[str, int, int]],
    width: int = 20,
    label: str = "",
) -> str:
    """Per-file diff +/- bars.  ``files = [(path, added, removed), ...]``."""
    if not files:
        return "(no data)"
    max_chg = max(a + r for _, a, r in files) or 1
    name_w = max(len(n) for n, _, _ in files)
    lines = []
    if label:
        lines.append(label)
    total_a = total_r = 0
    for name, added, removed in files:
        total_a += added
        total_r += removed
        a_len = int(added / max_chg * width)
        r_len = int(removed / max_chg * width)
        bar = "+" * a_len + "-" * r_len
        bar = bar.ljust(width, "·")
        lines.append(f"  {name:<{name_w}} │{bar}│ +{added}/-{removed}")
    net = total_a - total_r
    sign = "+" if net >= 0 else ""
    bar_total = "+" * (total_a // 10 or 1) + "-" * (total_r // 10 or 1)
    lines.append(f"  {'TOTAL':<{name_w}} │{bar_total}│ {sign}{net}")
    return "\n".join(lines)


# ── 4. Test results matrix ─────────────────────────────────────────────────

def render_test_results(
    suites: list[tuple[str, dict[str, int]]],
    label: str = "",
) -> str:
    """Test result matrix.  ``suites = [(name, {'pass':n,'fail':n,'skip':n}), ...]``."""
    if not suites:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  {'SUITE':<20} {'PASS':>5} {'FAIL':>5} {'SKIP':>5}  STATUS")
    lines.append(f"  {'─' * 20} {'─' * 5} {'─' * 5} {'─' * 5}  ──────")
    total_p = total_f = total_s = 0
    for name, stats in suites:
        p = stats.get("pass", 0)
        f = stats.get("fail", 0)
        s = stats.get("skip", 0)
        total_p += p
        total_f += f
        total_s += s
        status = "✓ PASS" if f == 0 else "✗ FAIL"
        lines.append(f"  {name:<20} {p:>5} {f:>5} {s:>5}  {status}")
    lines.append(f"  {'─' * 20} {'─' * 5} {'─' * 5} {'─' * 5}  ──────")
    total_status = "✓ ALL PASS" if total_f == 0 else f"✗ {total_f} FAILURES"
    lines.append(f"  {'TOTAL':<20} {total_p:>5} {total_f:>5} {total_s:>5}  {total_status}")
    return "\n".join(lines)


# ── 5. Dependency graph ─────────────────────────────────────────────────────

def render_dependency_graph(
    root: str,
    deps: dict[str, list[str]],
    max_depth: int = 3,
    label: str = "",
) -> str:
    """Dependency tree from ``{package: [children, ...]}``."""
    lines = []
    if label:
        lines.append(label)

    def _walk(name: str, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        children = deps.get(name, [])
        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            conn = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")
            lines.append(f"{prefix}{conn}{child}")
            _walk(child, child_prefix, depth + 1)

    lines.append(f"  {root}")
    _walk(root, "  ", 0)
    return "\n".join(lines)


# ── 6. File size bars ───────────────────────────────────────────────────────

def render_file_size_bars(
    files: list[tuple[str, int]],
    width: int = 30,
    label: str = "",
    unit: str = "LOC",
) -> str:
    """File size comparison bars.  ``files = [(name, size), ...]``."""
    if not files:
        return "(no data)"
    max_size = max(s for _, s in files) or 1
    name_w = max(len(n) for n, _ in files)
    lines = []
    if label:
        lines.append(label)
    for name, size in files:
        bar = _bar(size / max_size, width)
        lines.append(f"  {name:<{name_w}} │{bar}│ {size} {unit}")
    return "\n".join(lines)


# ── 7. Git timeline ─────────────────────────────────────────────────────────

def render_git_timeline(
    commits: list[tuple[str, str, int]],
    width: int = 40,
    label: str = "",
) -> str:
    """Git commit sparkline.  ``commits = [(hash, author, files_changed), ...]``."""
    if not commits:
        return "(no data)"
    values = [c for _, _, c in commits]
    max_v = max(values) or 1
    chars = "▁▂▃▄▅▆▇█"
    spark = ""
    for v in values:
        idx = int(v / max_v * (len(chars) - 1))
        spark += chars[idx]
    if width > 0 and width < len(spark):
        spark = spark[:width]
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  Commits: {spark}  ({len(commits)} commits)")
    # Recent commits
    for h, author, changed in commits[-5:]:
        lines.append(f"    {h[:7]} {author:<12} {changed} files")
    return "\n".join(lines)


# ── 8. Error rate ───────────────────────────────────────────────────────────

def render_error_rate(
    counts: list[int],
    width: int = 30,
    label: str = "",
) -> str:
    """Error frequency bars over time."""
    if not counts:
        return "(no data)"
    max_c = max(counts) or 1
    lines = []
    if label:
        lines.append(label)
    chars = "▁▂▃▄▅▆▇█"
    spark = ""
    for c in counts:
        idx = int(c / max_c * (len(chars) - 1))
        spark += chars[idx]
    lines.append(f"  Errors: {spark}  ({sum(counts)} total, max {max_c})")
    return "\n".join(lines)


# ── 9. Performance benchmark ────────────────────────────────────────────────

def render_perf_benchmark(
    benchmarks: list[tuple[str, float, float]],
    width: int = 20,
    label: str = "",
) -> str:
    """Before/after timing.  ``benches = [(name, before_ms, after_ms), ...]``."""
    if not benchmarks:
        return "(no data)"
    max_t = max(max(b, a) for _, b, a in benchmarks) or 1.0
    name_w = max(len(n) for n, _, _ in benchmarks)
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  {'BENCH':<{name_w}}  {'BEFORE':>{width}}  {'AFTER':>{width}}  Δ")
    for name, before, after in benchmarks:
        b_bar = _bar(before / max_t, width, "▓", "░")
        a_bar = _bar(after / max_t, width, "█", "░")
        delta = after - before
        pct = (delta / before * 100) if before else 0
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        lines.append(f"  {name:<{name_w}}  {b_bar}  {a_bar}  {arrow}{abs(pct):.0f}%")
    return "\n".join(lines)


# ── 10. API latency waterfall ───────────────────────────────────────────────

def render_api_latency(
    endpoints: list[tuple[str, float, float]],
    width: int = 30,
    label: str = "",
) -> str:
    """API endpoint latency bars.  ``endpoints = [(route, p50_ms, p99_ms), ...]``."""
    if not endpoints:
        return "(no data)"
    max_lat = max(p9 for _, _, p9 in endpoints) or 1.0
    name_w = max(len(n) for n, _, _ in endpoints)
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  {'ENDPOINT':<{name_w}}  {'P50':<{width}}  {'P99':<{width}}")
    for name, p50, p99 in endpoints:
        bar50 = _bar(p50 / max_lat, width, "▒", "░")
        bar99 = _bar(p99 / max_lat, width, "█", "░")
        lines.append(f"  {name:<{name_w}}  {bar50}  {bar99}  p50={p50:.0f}ms p99={p99:.0f}ms")
    return "\n".join(lines)


# ── 11. Build pipeline ──────────────────────────────────────────────────────

def render_build_pipeline(
    stages: list[tuple[str, str, float]],
    label: str = "",
) -> str:
    """CI/CD pipeline status.  ``stages = [(name, status, duration_s), ...]``."""
    if not stages:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    for i, (name, status, dur) in enumerate(stages):
        icon = _STATUS.get(status.lower(), "?")
        is_last = i == len(stages) - 1
        conn = "└─" if is_last else "├─"
        next_line = "  " if is_last else "│ "
        dur_str = f" ({dur:.1f}s)" if dur > 0 else ""
        lines.append(f"  {conn} {icon} {name}{dur_str}")
        if not is_last:
            lines.append(f"  {next_line}")
    return "\n".join(lines)


# ── 12. Security scan ───────────────────────────────────────────────────────

def render_security_scan(
    vulns: list[tuple[str, str, str]],
    label: str = "",
) -> str:
    """Vulnerability matrix.  ``vulns = [(id, severity, package), ...]``."""
    if not vulns:
        return "  ✓ No vulnerabilities found"
    sev_icon = {
        "critical": "🔴", "high": "🟠", "medium": "🟡",
        "low": "🔵", "info": "⚪",
    }
    lines = []
    if label:
        lines.append(label)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    sorted_v = sorted(vulns, key=lambda x: sev_order.get(x[1].lower(), 5))
    for vid, sev, pkg in sorted_v:
        icon = sev_icon.get(sev.lower(), "❓")
        lines.append(f"  {icon} [{sev.upper():>8}] {vid}  {pkg}")
    counts: dict[str, int] = {}
    for _, sev, _ in vulns:
        counts[sev] = counts.get(sev, 0) + 1
    summary = " · ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
    lines.append(f"  ── {len(vulns)} total ({summary})")
    return "\n".join(lines)


# ── 13. Code churn ──────────────────────────────────────────────────────────

def render_code_churn(
    files: list[tuple[str, int, int]],
    width: int = 20,
    label: str = "",
) -> str:
    """Files changed frequency (churn).  ``files = [(path, commits, lines), ...]``."""
    if not files:
        return "(no data)"
    max_commits = max(c for _, c, _ in files) or 1
    name_w = max(len(n) for n, _, _ in files)
    lines = []
    if label:
        lines.append(label)
    for name, commits, lines_changed in files:
        bar = _bar(commits / max_commits, width, "▓", "░")
        lines.append(f"  {name:<{name_w}} │{bar}│ {commits} commits, {lines_changed} lines")
    return "\n".join(lines)


# ── 14. DB schema ───────────────────────────────────────────────────────────

def render_db_schema(
    tables: dict[str, list[str]],
    label: str = "",
) -> str:
    """Database schema map.  ``tables = {table: [columns, ...]}``."""
    if not tables:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    for table, cols in tables.items():
        border = "─" * (len(table) + 4)
        lines.append(f"  ┌{border}┐")
        lines.append(f"  │  {table}  │")
        lines.append(f"  ├{border}┤")
        for col in cols:
            lines.append(f"  │  • {col:<{len(table)}}  │")
        lines.append(f"  └{border}┘")
    return "\n".join(lines)


# ── 15. Memory profile ──────────────────────────────────────────────────────

def render_memory_profile(
    heap: list[float],
    stack: list[float] | None = None,
    width: int = 40,
    label: str = "",
) -> str:
    """Memory usage sparkline over time."""
    if not heap:
        return "(no data)"
    chars = "▁▂▃▄▅▆▇█"
    max_h = max(heap) or 1
    heap_spark = "".join(chars[int(v / max_h * 7)] for v in heap[:width])
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  Heap:  {heap_spark}  (peak {max_h:.1f}MB)")
    if stack:
        max_s = max(stack) or 1
        stack_spark = "".join(chars[int(v / max_s * 7)] for v in stack[:width])
        lines.append(f"  Stack: {stack_spark}  (peak {max_s:.1f}MB)")
    return "\n".join(lines)


# ── 16. Flame chart ─────────────────────────────────────────────────────────

def render_flame_chart(
    frames: list[tuple[str, float, int]],
    width: int = 40,
    label: str = "",
) -> str:
    """CPU flame chart.  ``frames = [(name, duration_ms, depth), ...]``."""
    if not frames:
        return "(no data)"
    max_dur = max(d for _, d, _ in frames) or 1.0
    lines = []
    if label:
        lines.append(label)
    for name, dur, depth in frames:
        bar_len = max(1, int(dur / max_dur * width))
        indent = "  " * depth
        bar = "█" * bar_len
        lines.append(f"  {indent}{bar} {name} ({dur:.1f}ms)")
    return "\n".join(lines)


# ── 17. Deploy status ───────────────────────────────────────────────────────

def render_deploy_status(
    envs: list[tuple[str, str, str]],
    label: str = "",
) -> str:
    """Deployment environment matrix.  ``envs = [(env, version, status), ...]``."""
    if not envs:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    env_w = max(len(e) for e, _, _ in envs)
    ver_w = max(len(v) for _, v, _ in envs)
    for env, version, status in envs:
        icon = _STATUS.get(status.lower(), "?")
        lines.append(f"  {env:<{env_w}}  v{version:<{ver_w}}  {icon} {status}")
    return "\n".join(lines)


# ── 18. Feature flags ───────────────────────────────────────────────────────

def render_feature_flags(
    flags: list[tuple[str, bool, str]],
    label: str = "",
) -> str:
    """Feature flag status.  ``flags = [(name, enabled, description), ...]``."""
    if not flags:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    name_w = max(len(n) for n, _, _ in flags)
    for name, enabled, desc in flags:
        toggle = "🟢 ON " if enabled else "○  OFF"
        lines.append(f"  {toggle}  {name:<{name_w}}  {desc}")
    enabled_count = sum(1 for _, e, _ in flags if e)
    lines.append(f"  ── {enabled_count}/{len(flags)} enabled")
    return "\n".join(lines)


# ── 19. Package versions ────────────────────────────────────────────────────

def render_package_versions(
    packages: list[tuple[str, str, str]],
    label: str = "",
) -> str:
    """Dependency version display.  ``packages = [(name, current, latest), ...]``."""
    if not packages:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    name_w = max(len(n) for n, _, _ in packages)
    for name, current, latest in packages:
        up_to_date = current == latest
        icon = "✓" if up_to_date else "↑"
        lines.append(f"  {icon} {name:<{name_w}}  {current:>10} → {latest:<10}")
    outdated = sum(1 for _, c, lat in packages if c != lat)
    lines.append(f"  ── {len(packages)} packages, {outdated} outdated")
    return "\n".join(lines)


# ── 20. Log density ─────────────────────────────────────────────────────────

def render_log_density(
    log_counts: dict[str, list[int]],
    width: int = 3,
    label: str = "",
) -> str:
    """Log level density heatmap.  ``counts = {'ERROR': [...], 'WARN': [...], ...}``."""
    if not log_counts:
        return "(no data)"
    all_vals = [v for counts in log_counts.values() for v in counts]
    max_v = max(all_vals) or 1
    lines = []
    if label:
        lines.append(label)
    level_order = ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"]
    for level in level_order:
        if level not in log_counts:
            continue
        counts = log_counts[level]
        bar = ""
        for v in counts:
            idx = min(int(v / max_v * (len(DENSITY) - 1)), len(DENSITY) - 1)
            bar += DENSITY[idx] * width
        total = sum(counts)
        lines.append(f"  {level:>8}  {bar}  ({total})")
    return "\n".join(lines) or "(no data)"


# ── 21. Duplication ─────────────────────────────────────────────────────────

def render_duplication(
    duplicates: list[tuple[str, str, int]],
    label: str = "",
) -> str:
    """Duplicate code block detection.  ``dups = [(file1, file2, lines), ...]``."""
    if not duplicates:
        return "  ✓ No duplication detected"
    lines = []
    if label:
        lines.append(label)
    for f1, f2, lines_count in duplicates:
        bar_len = min(lines_count // 5, 20)
        bar = "▓" * bar_len
        lines.append(f"  {bar}  {lines_count} lines  {f1} ↔ {f2}")
    total_dup = sum(ln for _, _, ln in duplicates)
    lines.append(f"  ── {len(duplicates)} duplicates, {total_dup} lines total")
    return "\n".join(lines)


# ── 22. Refactor progress ───────────────────────────────────────────────────

def render_refactor_progress(
    metrics: list[tuple[str, int, int]],
    width: int = 20,
    label: str = "",
) -> str:
    """Before/after line counts.  ``metrics = [(metric, before, after), ...]``."""
    if not metrics:
        return "(no data)"
    max_v = max(max(b, a) for _, b, a in metrics) or 1
    name_w = max(len(n) for n, _, _ in metrics)
    lines = []
    if label:
        lines.append(label)
    for name, before, after in metrics:
        b_bar = _bar(before / max_v, width, "▒", "░")
        a_bar = _bar(after / max_v, width, "█", "░")
        delta = after - before
        pct = (delta / before * 100) if before else 0
        sign = "+" if delta >= 0 else ""
        lines.append(f"  {name:<{name_w}}  {b_bar} → {a_bar}  {sign}{delta} ({sign}{pct:.0f}%)")
    return "\n".join(lines)


# ── 23. Endpoint map ────────────────────────────────────────────────────────

def render_endpoint_map(
    routes: list[tuple[str, str, str]],
    label: str = "",
) -> str:
    """REST API route tree.  ``routes = [(method, path, handler), ...]``."""
    if not routes:
        return "(no data)"
    method_colors = {
        "GET": "🟢", "POST": "🟡", "PUT": "🔵",
        "PATCH": "🟠", "DELETE": "🔴",
    }
    lines = []
    if label:
        lines.append(label)
    for method, path, handler in routes:
        icon = method_colors.get(method.upper(), "⚪")
        lines.append(f"  {icon} {method:<7} {path:<35} {handler}")
    lines.append(f"  ── {len(routes)} endpoints")
    return "\n".join(lines)


# ── 24. Cache stats ─────────────────────────────────────────────────────────

def render_cache_stats(
    caches: list[tuple[str, int, int]],
    width: int = 20,
    label: str = "",
) -> str:
    """Cache hit/miss bars.  ``caches = [(name, hits, misses), ...]``."""
    if not caches:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    name_w = max(len(n) for n, _, _ in caches)
    for name, hits, misses in caches:
        total = hits + misses or 1
        hit_ratio = hits / total
        bar = _bar(hit_ratio, width, "█", "░")
        pct = f"{hit_ratio * 100:.1f}%"
        lines.append(f"  {name:<{name_w}} │{bar}│ {pct} hit ({hits}/{total})")
    return "\n".join(lines)


# ── 25. Concurrency timeline ────────────────────────────────────────────────

def render_concurrency(
    tasks: list[tuple[str, float, float]],
    width: int = 40,
    total: float = 0.0,
    label: str = "",
) -> str:
    """Async task overlap timeline.  ``tasks = [(name, start_s, end_s), ...]``."""
    if not tasks:
        return "(no data)"
    if total <= 0:
        total = max(e for _, _, e in tasks) or 1.0
    name_w = max(len(n) for n, _, _ in tasks)
    lines = []
    if label:
        lines.append(label)
    for name, start, end in tasks:
        s = int(_clamp(start / total) * width)
        e = int(_clamp(end / total) * width)
        bar = "░" * s + "█" * max(1, e - s) + "░" * (width - e)
        lines.append(f"  {name:<{name_w}} │{bar}│ {start:.1f}s-{end:.1f}s")
    lines.append(f"  {'':<{name_w}}  0{'─' * (width - 2)}{total:.0f}s")
    return "\n".join(lines)


# ── 26. GC pressure ─────────────────────────────────────────────────────────

def render_gc_pressure(
    events: list[tuple[str, float, float]],
    width: int = 30,
    label: str = "",
) -> str:
    """Garbage collection event timeline.  ``events = [(gen, time_s, pause_ms), ...]``."""
    if not events:
        return "  ✓ No GC events recorded"
    total_time = max(t for _, t, _ in events) or 1.0
    lines = []
    if label:
        lines.append(label)
    for gen, time_s, pause in events:
        pos = int(_clamp(time_s / total_time) * width)
        bar = list("░" * width)
        bar[min(pos, width - 1)] = "█"
        bar_str = "".join(bar)
        lines.append(f"  {gen:>2} │{bar_str}│ t={time_s:.1f}s pause={pause:.1f}ms")
    total_pause = sum(p for _, _, p in events)
    lines.append(f"  ── {len(events)} events, total pause {total_pause:.1f}ms")
    return "\n".join(lines)


# ── 27. Network waterfall ───────────────────────────────────────────────────

def render_network_waterfall(
    requests: list[tuple[str, float, float, str]],
    width: int = 30,
    label: str = "",
) -> str:
    """HTTP request waterfall.  ``requests = [(url, start_ms, dur_ms, status), ...]``."""
    if not requests:
        return "(no data)"
    total = max(s + d for _, s, d, _ in requests) or 1.0
    name_w = max(len(u) for u, _, _, _ in requests)
    lines = []
    if label:
        lines.append(label)
    for url, start, dur, status in requests:
        s = int(_clamp(start / total) * width)
        e = int(_clamp((start + dur) / total) * width)
        bar = "░" * s + "█" * max(1, e - s) + "░" * (width - e)
        icon = "✓" if status.startswith("2") else ("⚠" if status.startswith("4") else "✗")
        lines.append(f"  {url:<{name_w}} │{bar}│ {icon} {status} ({dur:.0f}ms)")
    return "\n".join(lines)


# ── 28. Queue depth ─────────────────────────────────────────────────────────

def render_queue_depth(
    queues: list[tuple[str, int, int]],
    width: int = 20,
    label: str = "",
) -> str:
    """Message queue depth.  ``queues = [(name, current, max_seen), ...]``."""
    if not queues:
        return "(no data)"
    max_depth = max(m for _, _, m in queues) or 1
    name_w = max(len(n) for n, _, _ in queues)
    lines = []
    if label:
        lines.append(label)
    for name, current, max_seen in queues:
        bar = _bar(current / max_depth, width)
        health = "✓" if current < max_depth * 0.8 else "⚠"
        lines.append(f"  {name:<{name_w}} │{bar}│ {current}/{max_seen} {health}")
    return "\n".join(lines)


# ── 29. Error matrix ────────────────────────────────────────────────────────

def render_error_matrix(
    data: list[list[int]],
    row_labels: list[str],
    col_labels: list[str],
    width: int = 3,
    label: str = "",
) -> str:
    """Error count heatmap by service/time."""
    if not data:
        return "(no data)"
    flat = [v for row in data for v in row]
    max_v = max(flat) or 1
    lines = []
    if label:
        lines.append(label)
    # Column headers
    col_w = max((len(str(c)) for c in col_labels), default=width)
    header = " " * (max(len(str(r)) for r in row_labels) + 2)
    for cl in col_labels:
        header += f"{cl:>{col_w + 1}}"
    lines.append(header)
    for ri, row in enumerate(data):
        rl = row_labels[ri] if ri < len(row_labels) else ""
        cells = ""
        for v in row:
            idx = min(int(v / max_v * (len(DENSITY) - 1)), len(DENSITY) - 1)
            cells += DENSITY[idx] * width + " "
        lines.append(f"  {rl:<{max(len(str(r)) for r in row_labels)}}  {cells}")
    return "\n".join(lines)


# ── 30. Review progress ─────────────────────────────────────────────────────

def render_review_progress(
    reviews: list[tuple[str, str, int, int]],
    label: str = "",
) -> str:
    """Code review status board.  ``reviews = [(pr, status, comments, files), ...]``."""
    if not reviews:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  {'PR':<12} {'STATUS':<12} {'FILES':>5} {'COMMENTS':>8}")
    lines.append(f"  {'─' * 12} {'─' * 12} {'─' * 5} {'─' * 8}")
    for pr, status, comments, files in reviews:
        icon = _STATUS.get(status.lower(), "?")
        lines.append(f"  {pr:<12} {icon} {status:<10} {files:>5} {comments:>8}")
    approved = sum(1 for _, s, _, _ in reviews if s.lower() in ("pass", "approved", "done"))
    lines.append(f"  ── {approved}/{len(reviews)} approved")
    return "\n".join(lines)


__all__ = [
    "render_code_coverage",
    "render_complexity_heat",
    "render_diff_summary",
    "render_test_results",
    "render_dependency_graph",
    "render_file_size_bars",
    "render_git_timeline",
    "render_error_rate",
    "render_perf_benchmark",
    "render_api_latency",
    "render_build_pipeline",
    "render_security_scan",
    "render_code_churn",
    "render_db_schema",
    "render_memory_profile",
    "render_flame_chart",
    "render_deploy_status",
    "render_feature_flags",
    "render_package_versions",
    "render_log_density",
    "render_duplication",
    "render_refactor_progress",
    "render_endpoint_map",
    "render_cache_stats",
    "render_concurrency",
    "render_gc_pressure",
    "render_network_waterfall",
    "render_queue_depth",
    "render_error_matrix",
    "render_review_progress",
]

# Fail-open hardening: every render_* coerces hostile args and never raises.
harden(globals())
