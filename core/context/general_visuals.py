"""General-purpose visualizations — 40 charts for any assistant, any task.

Pure Unicode output. Works in CLI, tool panels, any agent interface.
For chatbots, personal assistants, writing aids, research helpers, and more.

Types:
  1.  sentiment_gauge     — positive/neutral/negative meter
  2.  word_count          — text statistics display
  3.  reading_progress    — reading completion bar
  4.  mood_tracker        — daily mood grid
  5.  habit_tracker       — habit streak grid
  6.  task_priority       — urgency vs importance matrix
  7.  meeting_agenda      — timed agenda display
  8.  budget_tracker      — budget vs actual bars
  9.  expense_breakdown   — spending category bars
  10. weekly_schedule     — 7-day schedule grid
  11. countdown           — event countdown timer
  12. star_rating         — ★★★★☆ rating display
  13. poll_results        — horizontal poll bars
  14. survey_matrix       — Likert scale heat grid
  15. decision_matrix     — weighted scoring table
  16. pros_cons           — two-column comparison
  17. progress_wheel      — circular progress indicator
  18. fitness_stats       — workout summary bars
  19. recipe_steps        — numbered step display
  20. checklist           — interactive task checklist
  21. travel_itinerary    — trip timeline
  22. study_progress      — topic completion bars
  23. flashcard_scores    — spaced repetition stats
  24. quiz_results        — score breakdown bars
  25. todo_board          — multi-column task board
  26. price_comparison    — product price comparison
  27. review_summary      — star distribution chart
  28. mind_map            — central idea branches
  29. contact_card        — person info display
  30. gratitude_log       — daily gratitude entries
  31. water_intake        — daily hydration tracker
  32. sleep_tracker       — sleep quality display
  33. meditation_log      — session duration bars
  34. mood_timeline        — mood over time sparkline
  35. life_balance        — life area radar
  36. savings_goal         — savings progress bar
  37. workout_plan         — weekly workout schedule
  38. reading_list         — book reading status
  39. wishlist             — desired items display
  40. date_countdown       — days until event
"""

from __future__ import annotations

import math

from core.context.visual_dispatch import harden

DENSITY = " ░▒▓█"
BAR_FILL = "█"
BAR_EMPTY = "░"
STAR_FULL = "★"
STAR_HALF = "⯪"
STAR_EMPTY = "☆"


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _bar(ratio: float, width: int, fill: str = BAR_FILL, empty: str = BAR_EMPTY) -> str:
    r = _clamp(ratio)
    filled = int(r * width)
    return fill * filled + empty * (width - filled)


# ── 1. Sentiment gauge ──────────────────────────────────────────────────────

def render_sentiment_gauge(
    positive: float,
    neutral: float,
    negative: float,
    label: str = "",
) -> str:
    """Sentiment distribution bar.  Values 0-1."""
    total = positive + neutral + negative or 1.0
    p, n, neg = positive / total, neutral / total, negative / total
    width = 40
    p_w = int(p * width)
    n_w = int(n * width)
    neg_w = width - p_w - n_w
    bar = "+" * p_w + "=" * n_w + "-" * neg_w
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  [{bar}]")
    lines.append(f"  Positive: {p * 100:.0f}%  Neutral: {n * 100:.0f}%  Negative: {neg * 100:.0f}%")
    if p > neg:
        lines.append("  → Overall: POSITIVE ↑")
    elif neg > p:
        lines.append("  → Overall: NEGATIVE ↓")
    else:
        lines.append("  → Overall: NEUTRAL →")
    return "\n".join(lines)


# ── 2. Word count ───────────────────────────────────────────────────────────

def render_word_count(
    text: str,
    label: str = "",
) -> str:
    """Text stats: composition mosaic + word-length sparkline."""
    words = len(text.split()) if text else 0
    chars = len(text)
    chars_no_space = len(text.replace(" ", "").replace("\n", ""))
    lines_count = text.count("\n") + 1 if text else 0
    sentences = sum(text.count(s) for s in ".!?") or 1
    avg_word_len = chars_no_space / words if words else 0
    reading_time = max(1, words // 200)
    # ── Composition mosaic: stacked segments showing text makeup ──
    spaces = chars - chars_no_space
    space_ratio = spaces / max(chars, 1)
    letter_ratio = chars_no_space / max(chars, 1)
    w = 30
    n_letters = int(letter_ratio * w)
    n_spaces = w - n_letters
    mosaic = "▓" * n_letters + "·" * n_spaces
    # ── Word length sparkline ──
    word_lens = [len(wd) for wd in text.split()[:20]] or [1]
    spk_chars = "▁▂▃▄▅▆▇█"
    mx = max(word_lens) or 1
    spark = "".join(spk_chars[min(int(wl / mx * 7), 7)] for wl in word_lens)
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  ┌{'─' * (w + 2)}┐")
    lines.append(f"  │ {mosaic} │ letters:{letter_ratio:.0%} spaces:{space_ratio:.0%}")
    lines.append(f"  └{'─' * (w + 2)}┘")
    lines.append(f"  Word lens: {spark}  (avg {avg_word_len:.1f})")
    lines.append(
        f"  📝 {words} words  🔤 {chars} chars  "
        f"📏 {lines_count} lines  📖 {sentences} sent"
    )
    lines.append(f"  ⏱ ~{reading_time} min read")
    return "\n".join(lines)


# ── 3. Reading progress ─────────────────────────────────────────────────────

def render_reading_progress(
    current_page: int,
    total_pages: int,
    width: int = 30,
    label: str = "",
    book_title: str = "",
) -> str:
    """Reading completion bar."""
    ratio = current_page / total_pages if total_pages else 0
    bar = _bar(ratio, width)
    pct = ratio * 100
    remaining = total_pages - current_page
    lines = []
    if label:
        lines.append(label)
    title_line = f"  📚 {book_title}" if book_title else ""
    if title_line:
        lines.append(title_line)
    lines.append(f"  [{bar}] {pct:.1f}%")
    lines.append(f"  Page {current_page}/{total_pages}  ({remaining} pages left)")
    return "\n".join(lines)


# ── 4. Mood tracker ─────────────────────────────────────────────────────────

def render_mood_tracker(
    moods: list[tuple[str, str]],
    label: str = "",
) -> str:
    """Mood wave + emoji day row.  ``moods = [(day, mood), ...]``."""
    mood_icons = {
        "happy": "😊", "great": "😄", "good": "🙂",
        "ok": "😐", "neutral": "😐", "meh": "😑",
        "sad": "😢", "bad": "😞", "terrible": "😫",
        "angry": "😠", "anxious": "😰", "stressed": "😤",
        "calm": "😌", "relaxed": "😌", "excited": "🤩",
        "tired": "😴", "sick": "🤒",
    }
    mood_levels = {
        "great": 5, "excited": 5, "happy": 4, "good": 4,
        "calm": 3, "relaxed": 3, "ok": 3, "neutral": 3,
        "meh": 2, "tired": 2, "sad": 2, "bad": 1,
        "terrible": 1, "angry": 1, "anxious": 1, "stressed": 1, "sick": 1,
    }
    if not moods:
        return "(no data)"
    day_w = max(len(d) for d, _ in moods)
    levels = []
    for _, mood in moods:
        mood_clean = mood.lower().split()[-1] if mood else ""
        levels.append(mood_levels.get(mood_clean, 3))
    avg = sum(levels) / len(levels) if levels else 0
    # ── Mood wave (sparkline of levels) ──
    spk = "▁▂▃▄▅▆▇█"
    wave = "".join(spk[min(int((lv - 1) / 4 * 7), 7)] for lv in levels)
    # ── Dot constellation (5-dot level per day) ──
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  Mood wave: {wave}  avg {avg:.1f}/5")
    # ── Emoji row with day labels ──
    emoji_row = []
    day_row = []
    for (day, mood), _lv in zip(moods, levels, strict=False):
        mood_clean = mood.lower().split()[-1] if mood else ""
        icon = mood_icons.get(mood_clean, mood if len(mood) <= 2 else "❓")
        emoji_row.append(f"{icon}{'':>{max(2, day_w - 1)}}")
        day_row.append(f"{day:<{day_w + 2}}")
    lines.append("  " + "".join(emoji_row))
    lines.append("  " + "".join(day_row))
    # ── Level dots (●●●○○ = 3/5) ──
    for (day, mood), lv in zip(moods, levels, strict=False):
        mood_clean = mood.lower().split()[-1] if mood else ""
        dots = "●" * lv + "○" * (5 - lv)
        icon = mood_icons.get(mood_clean, "❓")
        lines.append(f"  {day:<{day_w}} {icon} {dots} {lv}")
    return "\n".join(lines)


# ── 5. Habit tracker ────────────────────────────────────────────────────────

def render_habit_tracker(
    habits: list[tuple[str, list[bool]]],
    label: str = "",
) -> str:
    """Habit streak grid.  ``habits = [(name, [done_today, done_yesterday, ...]), ...]``."""
    if not habits:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    name_w = max(len(n) for n, _ in habits)
    for name, days in habits:
        grid = "".join("✓" if d else "·" for d in days)
        streak = 0
        for d in days:
            if d:
                streak += 1
            else:
                break
        lines.append(f"  {name:<{name_w}}  {grid}  streak: {streak}")
    total_done = sum(sum(1 for d in days if d) for _, days in habits)
    total_possible = sum(len(days) for _, days in habits) or 1
    lines.append(f"  ── {total_done}/{total_possible} completions")
    return "\n".join(lines)


# ── 6. Task priority matrix ────────────────────────────────────────────────

def render_task_priority(
    tasks: list[tuple[str, str, str]],
    label: str = "",
) -> str:
    """2×2 Eisenhower quadrant grid with positioned dots."""
    if not tasks:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    # Organize into quadrants
    quads = {
        "DO NOW 🔥": [],
        "DELEGATE 📋": [],
        "SCHEDULE 📅": [],
        "ELIMINATE 🗑": [],
    }
    for name, urgency, importance in tasks:
        u, i = urgency.lower(), importance.lower()
        if u == "high" and i == "high":
            quads["DO NOW 🔥"].append(name)
        elif u == "low" and i == "high":
            quads["DELEGATE 📋"].append(name)
        elif u == "high" and i == "low":
            quads["SCHEDULE 📅"].append(name)
        else:
            quads["ELIMINATE 🗑"].append(name)
    qw = 22
    keys = list(quads.keys())
    # ── 2×2 grid ──
    lines.append(f"  {'URGENT':^{qw}}  {'NOT URGENT':^{qw}}")
    lines.append(f"  {'─' * qw}  {'─' * qw}")
    items_tl = quads[keys[0]][:3]
    items_tr = quads[keys[1]][:3]
    for row in range(3):
        tl = f"  • {items_tl[row]:<{qw - 4}}" if row < len(items_tl) else " " * qw
        tr = f"  • {items_tr[row]:<{qw - 4}}" if row < len(items_tr) else " " * qw
        lines.append(f"  {tl}  {tr}")
    lines.append(f"  {'─' * qw}  {'─' * qw}")
    items_bl = quads[keys[2]][:3]
    items_br = quads[keys[3]][:3]
    for row in range(3):
        bl = f"  • {items_bl[row]:<{qw - 4}}" if row < len(items_bl) else " " * qw
        br = f"  • {items_br[row]:<{qw - 4}}" if row < len(items_br) else " " * qw
        lines.append(f"  {bl}  {br}")
    lines.append(f"  {'NOT IMPORTANT':^{qw}}  {'NOT IMPORTANT':^{qw}}")
    # ── Quadrant count dots ──
    for k, v in quads.items():
        dots = "●" * min(len(v), 10) + "○" * max(0, 10 - len(v))
        lines.append(f"  {k:<18} {dots}  {len(v)}")
    return "\n".join(lines)


# ── 7. Meeting agenda ───────────────────────────────────────────────────────

def render_meeting_agenda(
    items: list[tuple[str, int, str]],
    label: str = "",
) -> str:
    """Gantt timeline with time ruler and duration blocks."""
    if not items:
        return "(no data)"
    total_min = sum(d for _, d, _ in items) or 1
    topic_w = max(len(t) for t, _, _ in items)
    width = 28
    lines = []
    if label:
        lines.append(label)
    # ── Time ruler ──
    ruler = [" "] * (width + 2)
    for i in range(0, total_min + 1, max(1, total_min // 4)):
        pos = int(i / total_min * width) + 1
        if pos < width + 1:
            ruler[pos] = "┬"
    time_labels = [" "] * (width + 2)
    for i in range(0, total_min + 1, max(1, total_min // 4)):
        pos = int(i / total_min * width) + 1
        if pos < width + 1:
            lbl = f"{i}m"
            for j, ch in enumerate(lbl):
                if pos + j < width + 2:
                    time_labels[pos + j] = ch
    lines.append("  " + "".join(ruler))
    lines.append("  " + "".join(time_labels))
    # ── Gantt blocks (each topic gets a filled segment in a shared track) ──
    current = 0
    block_colors = ["█", "▓", "▒", "░"]
    for idx, (topic, dur, presenter) in enumerate(items):
        start_frac = current / total_min
        end_frac = (current + dur) / total_min
        current += dur
        track = [" "] * (width + 2)
        fill = block_colors[idx % len(block_colors)]
        for j in range(width + 2):
            frac = (j - 1) / width if j > 0 else 0
            if start_frac <= frac <= end_frac and 0 < j < width + 1:
                track[j] = fill
        start_str = f"{current - dur:3d}m"
        track_str = "".join(track)
        lines.append(f"  {topic:<{topic_w}} {start_str} {track_str} {dur}m")
        # Presenter annotation
        lines.append(f"  {'':<{topic_w}}      └─ {presenter}")
    # ── Duration distribution (radial dots) ──
    lines.append("")
    for topic, dur, _presenter in items:
        pct = dur / total_min * 100
        n_fill = int(pct / 5)
        dots = "●" * n_fill + "○" * (20 - n_fill)
        lines.append(f"  {topic:<{topic_w}} {dots} {pct:.0f}%")
    lines.append(f"  {'─' * 28} Total: {total_min} min")
    return "\n".join(lines)


# ── 8. Budget tracker ───────────────────────────────────────────────────────

def render_budget_tracker(
    categories: list[tuple[str, float, float]],
    width: int = 20,
    label: str = "",
    currency: str = "$",
) -> str:
    """Budget vs actual bars.  ``categories = [(name, budget, actual), ...]``."""
    if not categories:
        return "(no data)"
    name_w = max(len(n) for n, _, _ in categories)
    lines = []
    if label:
        lines.append(label)
    total_b = total_a = 0
    for name, budget, actual in categories:
        total_b += budget
        total_a += actual
        ratio = actual / budget if budget else 0
        bar = _bar(ratio, width, "█" if actual <= budget else "▓", "░")
        status = "✓" if actual <= budget else "⚠ OVER"
        a_str = f"{currency}{actual:.0f}/{currency}{budget:.0f}"
        lines.append(f"  {name:<{name_w}} │{bar}│ {a_str} {status}")
    t_str = f"{currency}{total_a:.0f} spent / {currency}{total_b:.0f} budget"
    lines.append(f"  {'TOTAL':<{name_w}}  {t_str}")
    return "\n".join(lines)


# ── 9. Expense breakdown ────────────────────────────────────────────────────

def render_expense_breakdown(
    categories: list[tuple[str, float]],
    width: int = 25,
    label: str = "",
    currency: str = "$",
) -> str:
    """Spending category bars with percentages."""
    if not categories:
        return "(no data)"
    total = sum(v for _, v in categories) or 1.0
    max_val = max(v for _, v in categories) or 1.0
    name_w = max(len(n) for n, _ in categories)
    lines = []
    if label:
        lines.append(label)
    for name, val in categories:
        bar = _bar(val / max_val, width)
        pct = val / total * 100
        lines.append(f"  {name:<{name_w}} │{bar}│ {currency}{val:.2f} ({pct:.1f}%)")
    lines.append(f"  {'TOTAL':<{name_w}}  {currency}{total:.2f}")
    return "\n".join(lines)


# ── 10. Weekly schedule ─────────────────────────────────────────────────────

def render_weekly_schedule(
    schedule: dict[str, list[str]],
    label: str = "",
) -> str:
    """Time-of-day heat grid + activity timeline."""
    if not schedule:
        return "(no data)"
    max_items = max(len(v) for v in schedule.values()) if schedule else 1
    day_w = max(len(d) for d in schedule) + 2
    lines = []
    if label:
        lines.append(label)
    # ── Heat grid: day rows × intensity blocks ──
    blocks = " ░▒▓█"
    lines.append(f"  {'':<{day_w}} {'AM':^6} {'PM':^6} {'EV':^6}  Load")
    for day, items in schedule.items():
        n = len(items)
        ratio = n / max(max_items, 1)
        intensity = blocks[min(int(ratio * 4) + 1, 4)]
        am = intensity if n > 0 else "·"
        pm = intensity if n > 1 else "·"
        ev = intensity if n > 2 else "·"
        # Treemap-style activity box
        box_w = int(ratio * 16)
        treemap = "█" * box_w + "░" * (16 - box_w)
        lines.append(
            f"  {day:<{day_w}} {am:^6} {pm:^6} {ev:^6}  [{treemap}] {n}"
        )
        # Activity detail line (connected timeline dots)
        if items:
            dots = "─".join("●" for _ in items[:5])
            items_str = "  ".join(items[:3])
            extra = f" +{len(items) - 3}" if len(items) > 3 else ""
            lines.append(f"  {'':<{day_w}} {dots}  {items_str}{extra}")
    return "\n".join(lines)


# ── 11. Countdown ───────────────────────────────────────────────────────────

def render_countdown(
    event: str,
    days: int,
    hours: int = 0,
    minutes: int = 0,
) -> str:
    """Event countdown timer."""
    total_hours = days * 24 + hours
    bar_width = 30
    progress = max(0, min(1, 1 - days / 365))  # rough estimate
    bar = _bar(progress, bar_width, "▓", "░")
    lines = [
        f"  ⏰ {event}",
        f"  [{bar}]",
        f"  {days} days, {hours} hours, {minutes} minutes remaining",
        f"  ≈ {total_hours} hours total",
    ]
    return "\n".join(lines)


# ── 12. Star rating ─────────────────────────────────────────────────────────

def render_star_rating(
    rating: float,
    max_rating: float = 5.0,
    label: str = "",
    count: int = 0,
) -> str:
    """Star rating display."""
    full = int(rating)
    has_half = (rating - full) >= 0.25 and (rating - full) < 0.75
    if (rating - full) >= 0.75:
        full += 1
        has_half = False
    empty = int(max_rating) - full - (1 if has_half else 0)
    stars = STAR_FULL * full + (STAR_HALF if has_half else "") + STAR_EMPTY * max(0, empty)
    lines = []
    if label:
        lines.append(label)
    count_str = f" ({count} reviews)" if count else ""
    lines.append(f"  {stars}  {rating:.1f}/{max_rating:.0f}{count_str}")
    return "\n".join(lines)


# ── 13. Poll results ────────────────────────────────────────────────────────

def render_poll_results(
    options: list[tuple[str, int]],
    width: int = 30,
    label: str = "",
) -> str:
    """Horizontal poll bar chart."""
    if not options:
        return "(no data)"
    total = sum(v for _, v in options) or 1
    max_val = max(v for _, v in options) or 1
    name_w = max(len(n) for n, _ in options)
    lines = []
    if label:
        lines.append(label)
    sorted_opts = sorted(options, key=lambda x: x[1], reverse=True)
    for name, votes in sorted_opts:
        bar = _bar(votes / max_val, width)
        pct = votes / total * 100
        lines.append(f"  {name:<{name_w}} │{bar}│ {votes} votes ({pct:.1f}%)")
    lines.append(f"  ── {total} total votes")
    return "\n".join(lines)


# ── 14. Survey matrix ───────────────────────────────────────────────────────

def render_survey_matrix(
    questions: list[tuple[str, list[int]]],
    scale_labels: list[str] | None = None,
    label: str = "",
) -> str:
    """Likert scale survey heat grid.  ``questions = [(q, [1-5 responses]), ...]``."""
    if not questions:
        return "(no data)"
    if scale_labels is None:
        scale_labels = ["Strongly Disagree", "Disagree", "Neutral", "Agree", "Strongly Agree"]
    lines = []
    if label:
        lines.append(label)
    q_w = max(len(q) for q, _ in questions)
    # Header
    header = "  " + " " * q_w + "  "
    for i in range(5):
        header += f"{i + 1:>3}"
    lines.append(header)
    for q, responses in questions:
        counts = [0] * 5
        for r in responses:
            if 1 <= r <= 5:
                counts[r - 1] += 1
        max_c = max(counts) or 1
        row = f"  {q:<{q_w}}  "
        for c in counts:
            level = int(c / max_c * 4)
            row += f" {DENSITY[level]}"
        lines.append(row)
    return "\n".join(lines)


# ── 15. Decision matrix ─────────────────────────────────────────────────────

def render_decision_matrix(
    options: list[tuple[str, list[float]]],
    criteria: list[str],
    weights: list[float] | None = None,
    label: str = "",
) -> str:
    """Weighted decision scoring table."""
    if not options or not criteria:
        return "(no data)"
    if weights is None:
        weights = [1.0] * len(criteria)
    lines = []
    if label:
        lines.append(label)
    # Header
    crit_w = max(len(c) for c in criteria)
    name_w = max(len(n) for n, _ in options)
    header = f"  {'OPTION':<{name_w}}  "
    for c in criteria:
        header += f"{c:>{crit_w}}  "
    header += "SCORE"
    lines.append(header)
    lines.append(f"  {'─' * name_w}  " + "─" * (crit_w + 2) * len(criteria) + "  ─────")
    scores = []
    for name, values in options:
        score = sum(v * w for v, w in zip(values, weights, strict=False))
        scores.append((name, score))
        row = f"  {name:<{name_w}}  "
        for v in values:
            row += f"{v:>{crit_w}.1f}  "
        row += f"{score:.2f}"
        lines.append(row)
    best = max(scores, key=lambda x: x[1])
    lines.append(f"  ★ Best: {best[0]} (score {best[1]:.2f})")
    return "\n".join(lines)


# ── 16. Pros and cons ───────────────────────────────────────────────────────

def render_pros_cons(
    pros: list[str],
    cons: list[str],
    label: str = "",
) -> str:
    """Diverging butterfly chart: cons ← ┃ → pros."""
    lines = []
    if label:
        lines.append(label)
    col_w = max(
        max((len(p) for p in pros), default=10),
        max((len(c) for c in cons), default=10),
    ) + 4
    center = 3
    total = len(pros) + len(cons) or 1
    # ── Diverging butterfly bars from center ──
    pro_bar = "█" * max(1, int(len(pros) / total * 12))
    con_bar = "▓" * max(1, int(len(cons) / total * 12))
    lines.append(f"  {'CONS':>{col_w + 2}} {'←':^{center}} │{'→':^{center}} {'PROS':<{col_w + 2}}")
    lines.append(f"  {con_bar:>{col_w + 2}} {'':^{center}} │{'':^{center}} {pro_bar:<{col_w + 2}}")
    lines.append(f"  {'─' * (col_w + 2)} {'─' * center} ┃ {'─' * center} {'─' * (col_w + 2)}")
    max_rows = max(len(pros), len(cons))
    for i in range(max_rows):
        pro = pros[i] if i < len(pros) else ""
        con = cons[i] if i < len(cons) else ""
        # Arrow direction shows which side each item is on
        pro_str = f"  + {pro}" if pro else ""
        con_str = f"  - {con}" if con else ""
        marker_l = "◀" if con else " "
        marker_r = "▶" if pro else " "
        row_l = f"  {con_str:>{col_w + 2}}"
        row_r = f"  {pro_str:<{col_w + 2}}"
        lines.append(
            f"{row_l} {marker_l:^{center}} ┃ {marker_r:^{center}} {row_r}"
        )
    lines.append(f"  {'─' * (col_w + 2)} {'─' * center} ┃ {'─' * center} {'─' * (col_w + 2)}")
    # ── Score gauge ──
    balance = (len(pros) - len(cons)) / max(total, 1)
    gauge_pos = int((balance + 1) / 2 * 20)
    gauge = "░" * gauge_pos + "◆" + "░" * (20 - gauge_pos)
    verdict = "PROS WIN" if balance > 0 else ("CONS WIN" if balance < 0 else "EVEN")
    lines.append(f"  Balance: [{gauge}] {verdict} ({len(pros)}✓ vs {len(cons)}✗)")
    return "\n".join(lines)


# ── 17. Progress wheel ──────────────────────────────────────────────────────

def render_progress_wheel(
    ratio: float,
    size: int = 5,
    label: str = "",
) -> str:
    """Circular progress indicator."""
    r = _clamp(ratio)
    diameter = max(3, size | 1)
    cx = cy = diameter // 2
    lines = []
    if label:
        lines.append(label)
    for y in range(diameter):
        row = ""
        for x in range(diameter):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy * 4)
            if dist > diameter / 2 + 0.3:
                row += " "
            elif dist > diameter / 2 - 0.8:
                angle = (math.atan2(dy * 2, dx) / (2 * math.pi)) + 0.5
                row += "●" if angle <= r else "○"
            else:
                row += "●" if r >= 1.0 else "◌"
        lines.append(f"  {row}")
    pct = f"{r * 100:.0f}%"
    lines.append(f"  {pct}")
    return "\n".join(lines)


# ── 18. Fitness stats ───────────────────────────────────────────────────────

def render_fitness_stats(
    workouts: list[tuple[str, float, float]],
    width: int = 20,
    label: str = "",
) -> str:
    """Workout summary bars.  ``workouts = [(type, duration_min, calories), ...]``."""
    if not workouts:
        return "(no data)"
    max_dur = max(d for _, d, _ in workouts) or 1.0
    name_w = max(len(n) for n, _, _ in workouts)
    lines = []
    if label:
        lines.append(label)
    total_cal = total_dur = 0
    for name, dur, cal in workouts:
        total_dur += dur
        total_cal += cal
        bar = _bar(dur / max_dur, width)
        lines.append(f"  {name:<{name_w}} │{bar}│ {dur:.0f}min  {cal:.0f}kcal")
    lines.append(f"  {'TOTAL':<{name_w}}  {total_dur:.0f}min  {total_cal:.0f}kcal")
    return "\n".join(lines)


# ── 19. Recipe steps ────────────────────────────────────────────────────────

def render_recipe_steps(
    steps: list[str],
    label: str = "",
) -> str:
    """Connected path with numbered stations + mini donut progress."""
    if not steps:
        return "(no data)"
    n = len(steps)
    lines = []
    if label:
        lines.append(label)
    # ── Connected step path ──
    for i, step in enumerate(steps, 1):
        is_done = i <= n // 2
        station = "●" if is_done else "○"
        connector = "├─" if i < n else "└─"
        check = "✓" if is_done else " "
        lines.append(f"  {connector} {station} {check} Step {i}: {step}")
    # ── Mini donut progress (3×3) ──
    r = (n // 2) / n if n else 0
    n_filled = int(r * 8)
    ring = "●" * n_filled + "○" * (8 - n_filled)
    lines.append(f"  ── [{ring}] {n} steps ({int(r * 100)}% prepared)")
    return "\n".join(lines)
    return "\n".join(lines)


# ── 20. Checklist ───────────────────────────────────────────────────────────

def render_checklist(
    items: list[tuple[str, bool]],
    label: str = "",
) -> str:
    """Dot-matrix progress + strikethrough items."""
    if not items:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    done = sum(1 for _, d in items if d)
    # ── Dot matrix progress ──
    n_dots = min(len(items), 20)
    filled_dots = int(done / max(len(items), 1) * n_dots)
    dots = "█" * filled_dots + "░" * (n_dots - filled_dots)
    lines.append(f"  Progress: [{dots}] {done}/{len(items)} ({done / len(items) * 100:.0f}%)")
    # ── Items with checkboxes + strikethrough ──
    for name, checked in items:
        mark = "☑" if checked else "☐"
        style_name = f"~~{name}~~" if checked else name
        state = "✓" if checked else "○"
        lines.append(f"  {mark} {style_name}  {state}")
    # ── Completion ring (single-line) ──
    r = done / max(len(items), 1)
    filled = int(r * 10)
    ring = "●" * filled + "○" * (10 - filled)
    lines.append(f"  ── [{ring}]")
    return "\n".join(lines)


# ── 21. Travel itinerary ────────────────────────────────────────────────────

def render_travel_itinerary(
    days: list[tuple[str, list[str]]],
    label: str = "",
) -> str:
    """Vertical route timeline with station markers."""
    if not days:
        return "(no data)"
    max_acts = max(len(a) for _, a in days) if days else 1
    lines = []
    if label:
        lines.append(label)
    total_acts = sum(len(a) for _, a in days)
    for idx, (day, activities) in enumerate(days):
        is_last = idx == len(days) - 1
        connector = "├─" if not is_last else "└─"
        station = "◉" if activities else "○"
        # ── Activity density dot trail ──
        n_acts = len(activities)
        density = "●" * n_acts + "○" * (max_acts - n_acts)
        lines.append(f"  {connector}{station} {day}  [{density}] {n_acts} stops")
        for j, act in enumerate(activities):
            is_last_act = j == len(activities) - 1
            child_conn = "│  ├─" if not is_last_act else "│  └─"
            if is_last:
                child_conn = "   ├─" if not is_last_act else "   └─"
            lines.append(f"  {child_conn} 📍 {act}")
    lines.append(f"  ── {len(days)} days · {total_acts} activities")
    return "\n".join(lines)


# ── 22. Study progress ──────────────────────────────────────────────────────

def render_study_progress(
    topics: list[tuple[str, float]],
    width: int = 20,
    label: str = "",
) -> str:
    """Topic completion bars."""
    if not topics:
        return "(no data)"
    name_w = max(len(n) for n, _ in topics)
    lines = []
    if label:
        lines.append(label)
    for name, progress in topics:
        bar = _bar(progress, width)
        pct = f"{progress * 100:.0f}%"
        icon = "✓" if progress >= 1.0 else ("🔄" if progress > 0 else "○")
        lines.append(f"  {icon} {name:<{name_w}} │{bar}│ {pct}")
    avg = sum(p for _, p in topics) / len(topics)
    lines.append(f"  {'AVG':<{name_w}} │{_bar(avg, width)}│ {avg * 100:.0f}%")
    return "\n".join(lines)


# ── 23. Flashcard scores ────────────────────────────────────────────────────

def render_flashcard_scores(
    decks: list[tuple[str, int, int, int]],
    label: str = "",
) -> str:
    """Treemap mosaic + stacked density chart."""
    if not decks:
        return "(no data)"
    name_w = max(len(n) for n, _, _, _ in decks) + 2
    total = sum(n + ln + r for _, n, ln, r in decks) or 1
    lines = []
    if label:
        lines.append(label)
    # ── Treemap mosaic (each deck = box proportional to size) ──
    lines.append(f"  {'Deck':<{name_w}} {'Mosaic':<24} {'N':>4} {'L':>4} {'R':>4}")
    for name, new, learning, review in decks:
        deck_total = new + learning + review
        w = max(1, int(deck_total / total * 24))
        n_seg = max(1, int(new / max(deck_total, 1) * w))
        l_seg = max(1, int(learning / max(deck_total, 1) * w))
        r_seg = max(0, w - n_seg - l_seg)
        mosaic = "█" * n_seg + "▓" * l_seg + "░" * r_seg
        lines.append(
            f"  {name:<{name_w}} {mosaic:<24} {new:>4} {learning:>4} {review:>4}"
        )
    # ── Stacked density bar (aggregate) ──
    agg_new = sum(n for _, n, _, _ in decks)
    agg_learn = sum(ln for _, _, ln, _ in decks)
    agg_rev = sum(r for _, _, _, r in decks)
    w = 30
    n_w = int(agg_new / total * w)
    l_w = int(agg_learn / total * w)
    r_w = w - n_w - l_w
    stack = "█" * n_w + "▓" * l_w + "░" * r_w
    lines.append(f"  {'─' * name_w} Stack: [{stack}]")
    lines.append(f"  {'TOTAL':<{name_w}} New:{agg_new} Learning:{agg_learn} Review:{agg_rev}")
    return "\n".join(lines)
    if label:
        lines.append(label)
    name_w = max(len(n) for n, _, _, _ in decks)
    total_new = total_learn = total_rev = 0
    max_total = max((n + ln + rv) for _, n, ln, rv in decks) or 1
    for name, new, learning, review in decks:
        total_new += new
        total_learn += learning
        total_rev += review
        w = 16
        n_w = int(new / max_total * w)
        l_w = int(learning / max_total * w)
        r_w = int(review / max_total * w)
        bar = "█" * n_w + "▓" * l_w + "░" * r_w + "░" * max(0, w - n_w - l_w - r_w)
        lines.append(f"  {name:<{name_w}} │{bar[:w]}│ N:{new} L:{learning} R:{review}")
    total_all = total_new + total_learn + total_rev
    tline = f"N:{total_new} L:{total_learn} R:{total_rev} = {total_all}"
    lines.append(f"  {'TOTAL':<{name_w}}  {tline}")
    return "\n".join(lines)


# ── 24. Quiz results ────────────────────────────────────────────────────────

def render_quiz_results(
    questions: list[tuple[str, bool]],
    label: str = "",
) -> str:
    """Score breakdown by question."""
    if not questions:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    correct = sum(1 for _, c in questions if c)
    total = len(questions)
    score = correct / total * 100 if total else 0
    bar = _bar(score / 100, 20)
    grade = (
        "A+" if score >= 97 else "A" if score >= 93
        else "B" if score >= 87 else "C" if score >= 77
        else "D" if score >= 67 else "F"
    )
    lines.append(f"  [{bar}] {score:.1f}%  Grade: {grade}")
    for i, (q, correct) in enumerate(questions, 1):
        mark = "✓" if correct else "✗"
        lines.append(f"  {mark} Q{i}: {q}")
    lines.append(f"  ── {correct}/{total} correct")
    return "\n".join(lines)


# ── 25. Todo board ──────────────────────────────────────────────────────────

def render_todo_board(
    columns: list[tuple[str, list[str]]],
    label: str = "",
) -> str:
    """Multi-column task board (simplified kanban)."""
    if not columns:
        return "(no data)"
    col_w = max(max((len(c) for c in cards), default=2) for _, cards in columns) + 4
    lines = []
    if label:
        lines.append(label)
    # Headers
    header = "  "
    sep = "  "
    for _name, _ in columns:
        header += f"┌{'─' * col_w}┐ "
        sep += f"├{'─' * col_w}┤ "
    lines.append(header.rstrip())
    name_row = "  "
    for name, _ in columns:
        name_row += f"│ {name:<{col_w - 2}} │ "
    lines.append(name_row.rstrip())
    lines.append(sep.rstrip())
    max_rows = max((len(cards) for _, cards in columns), default=0)
    for r in range(max_rows):
        row = "  "
        for _, cards in columns:
            card = cards[r] if r < len(cards) else ""
            row += f"│ {card:<{col_w - 2}} │ "
        lines.append(row.rstrip())
    bottom = "  "
    for _, _ in columns:
        bottom += f"└{'─' * col_w}┘ "
    lines.append(bottom.rstrip())
    return "\n".join(lines)


# ── 26. Price comparison ────────────────────────────────────────────────────

def render_price_comparison(
    products: list[tuple[str, float, float]],
    width: int = 20,
    label: str = "",
    currency: str = "$",
) -> str:
    """Product price comparison.  ``products = [(name, price, rating), ...]``."""
    if not products:
        return "(no data)"
    max_price = max(p for _, p, _ in products) or 1.0
    name_w = max(len(n) for n, _, _ in products)
    lines = []
    if label:
        lines.append(label)
    sorted_p = sorted(products, key=lambda x: x[1])
    for name, price, rating in sorted_p:
        bar = _bar(price / max_price, width)
        stars = "★" * int(rating) + "☆" * (5 - int(rating))
        lines.append(f"  {name:<{name_w}} │{bar}│ {currency}{price:.2f}  {stars}")
    cheapest = sorted_p[0]
    lines.append(f"  💰 Best price: {cheapest[0]} ({currency}{cheapest[1]:.2f})")
    return "\n".join(lines)


# ── 27. Review summary ──────────────────────────────────────────────────────

def render_review_summary(
    ratings: dict[int, int],
    label: str = "",
) -> str:
    """Star distribution chart.  ``ratings = {stars: count, ...}``."""
    if not ratings:
        return "(no data)"
    total = sum(ratings.values())
    max_count = max(ratings.values()) or 1
    lines = []
    if label:
        lines.append(label)
    for stars in range(5, 0, -1):
        count = ratings.get(stars, 0)
        bar = _bar(count / max_count, 20, "█", "░")
        pct = count / total * 100 if total else 0
        star_str = STAR_FULL * stars + STAR_EMPTY * (5 - stars)
        lines.append(f"  {star_str} │{bar}│ {count} ({pct:.0f}%)")
    avg = sum(s * c for s, c in ratings.items()) / total if total else 0
    lines.append(f"  ── {total} reviews, average: {avg:.1f}/5")
    return "\n".join(lines)


# ── 28. Mind map ────────────────────────────────────────────────────────────

def render_mind_map(
    root: str,
    branches: dict[str, list[str]],
    label: str = "",
) -> str:
    """Central idea branches."""
    lines = []
    if label:
        lines.append(label)
    lines.append(f"        [{root}]")
    items = list(branches.items())
    for i, (branch, leaves) in enumerate(items):
        is_last = i == len(items) - 1
        conn = "└── " if is_last else "├── "
        child_prefix = "    " if is_last else "│   "
        lines.append(f"  {conn}{branch}")
        for j, leaf in enumerate(leaves):
            leaf_conn = "└── " if j == len(leaves) - 1 else "├── "
            lines.append(f"  {child_prefix}{leaf_conn}{leaf}")
    return "\n".join(lines)


# ── 29. Contact card ────────────────────────────────────────────────────────

def render_contact_card(
    name: str,
    fields: dict[str, str],
    label: str = "",
) -> str:
    """Person info display card."""
    lines = []
    if label:
        lines.append(label)
    border_w = max(len(name), max((len(v) for v in fields.values()), default=0) + 12) + 4
    lines.append(f"  ┌{'─' * border_w}┐")
    lines.append(f"  │  👤 {name:<{border_w - 5}} │")
    lines.append(f"  ├{'─' * border_w}┤")
    for key, val in fields.items():
        lines.append(f"  │  {key:<12} {val:<{border_w - 16}} │")
    lines.append(f"  └{'─' * border_w}┘")
    return "\n".join(lines)


# ── 30. Gratitude log ───────────────────────────────────────────────────────

def render_gratitude_log(
    entries: list[tuple[str, str]],
    label: str = "",
) -> str:
    """Heart-dots row + entry length sparkline."""
    if not entries:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    max_len = max(len(n) for _, n in entries) if entries else 1
    # ── Heart dots (each entry gets a heart sized by text length) ──
    hearts = []
    for _, note in entries:
        sz = len(note) / max(max_len, 1)
        hearts.append("❤" if sz > 0.7 else ("♡" if sz > 0.3 else "·"))
    heart_row = " ".join(hearts)
    # ── Entry sparkline ──
    spk = "▁▂▃▄▅▆▇█"
    spark = "".join(
        spk[min(int(len(n) / max(max_len, 1) * 7), 7)] for _, n in entries
    )
    lines.append(f"  ♥  {heart_row}")
    lines.append(f"  ✨ {spark}  (length trend)")
    # ── Entries with date brackets ──
    for date, note in entries:
        sz = len(note) / max(max_len, 1)
        fill = "█" * int(sz * 8) + "░" * (8 - int(sz * 8))
        lines.append(f"  [{date}] {fill} {note}")
    lines.append(f"  ── ♥ {len(entries)} gratitude moments")
    return "\n".join(lines)


# ── 31. Water intake ────────────────────────────────────────────────────────

def render_water_intake(
    glasses: int,
    goal: int = 8,
    label: str = "",
) -> str:
    """Daily hydration tracker."""
    ratio = glasses / goal if goal else 0
    bar = _bar(ratio, goal, "💧", "░")
    pct = ratio * 100
    status = "✓ GOAL MET" if glasses >= goal else f"({goal - glasses} more to go)"
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  💧 [{bar}] {glasses}/{goal} glasses ({pct:.0f}%)")
    lines.append(f"  {status}")
    return "\n".join(lines)


# ── 32. Sleep tracker ───────────────────────────────────────────────────────

def render_sleep_tracker(
    nights: list[tuple[str, float, float]],
    width: int = 20,
    label: str = "",
) -> str:
    """Sleep quality display.  ``nights = [(night, hours, quality_0_1), ...]``."""
    if not nights:
        return "(no data)"
    max_h = max(h for _, h, _ in nights) or 1.0
    lines = []
    if label:
        lines.append(label)
    for night, hours, quality in nights:
        bar = _bar(hours / max_h, width, "█", "░")
        q_bar = _bar(quality, 5, "★", "☆")
        lines.append(f"  {night:<10} │{bar}│ {hours:.1f}h  {q_bar}")
    avg_h = sum(h for _, h, _ in nights) / len(nights)
    avg_q = sum(q for _, _, q in nights) / len(nights)
    lines.append(f"  ── Avg: {avg_h:.1f}h, quality {avg_q * 100:.0f}%")
    return "\n".join(lines)


# ── 33. Meditation log ──────────────────────────────────────────────────────

def render_meditation_log(
    sessions: list[tuple[str, float]],
    width: int = 20,
    label: str = "",
) -> str:
    """Session duration bars."""
    if not sessions:
        return "(no data)"
    max_dur = max(d for _, d in sessions) or 1.0
    name_w = max(len(n) for n, _ in sessions)
    lines = []
    if label:
        lines.append(label)
    for name, dur in sessions:
        bar = _bar(dur / max_dur, width, "▓", "░")
        lines.append(f"  🧘 {name:<{name_w}} │{bar}│ {dur:.0f}min")
    total = sum(d for _, d in sessions)
    lines.append(f"  ── {len(sessions)} sessions, {total:.0f}min total")
    return "\n".join(lines)


# ── 34. Mood timeline ───────────────────────────────────────────────────────

def render_mood_timeline(
    moods: list[tuple[str, int]],
    label: str = "",
) -> str:
    """Mood over time sparkline (1-5 scale)."""
    if not moods:
        return "(no data)"
    values = [m for _, m in moods]
    chars = "▁▂▃▄▅▆▇█"
    spark = "".join(chars[min(max(int((v - 1) / 4 * 7), 0), 7)] for v in values)
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  Mood: {spark}")
    lines.append(f"  Scale: 1 (low) ─ 5 (high)   Latest: {values[-1]}")
    avg = sum(values) / len(values)
    lines.append(f"  Average: {avg:.1f}/5")
    return "\n".join(lines)


# ── 35. Life balance ────────────────────────────────────────────────────────

def render_life_balance(
    areas: list[tuple[str, float]],
    size: int = 9,
    label: str = "",
) -> str:
    """Life area radar chart."""
    if not areas:
        return "(no data)"
    n = len(areas)
    cx = cy = size // 2
    grid = [[" "] * size for _ in range(size)]
    for i, (_name, val) in enumerate(areas):
        angle = (2 * math.pi * i / n) - math.pi / 2
        for t in range(size // 2):
            x = int(cx + math.cos(angle) * t)
            y = int(cy + math.sin(angle) * t * 0.5)
            if 0 <= x < size and 0 <= y < size and grid[y][x] == " ":
                grid[y][x] = "·"
        r = _clamp(val) * (size / 2 - 1)
        x = int(cx + math.cos(angle) * r)
        y = int(cy + math.sin(angle) * r * 0.5)
        if 0 <= x < size and 0 <= y < size:
            grid[y][x] = "●"
    grid[cy][cx] = "┼"
    lines = []
    if label:
        lines.append(label)
    body = "\n".join("  " + "".join(row) for row in grid)
    lines.append(body)
    legend = "  " + "  ".join(f"{name}:{val:.0%}" for name, val in areas)
    lines.append(legend)
    return "\n".join(lines)


# ── 36. Savings goal ────────────────────────────────────────────────────────

def render_savings_goal(
    current: float,
    target: float,
    width: int = 30,
    label: str = "",
    currency: str = "$",
) -> str:
    """Savings progress bar."""
    ratio = current / target if target else 0
    bar = _bar(ratio, width)
    pct = ratio * 100
    remaining = target - current
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  🎯 [{bar}] {pct:.1f}%")
    remaining_str = f"({currency}{remaining:.2f} to go)"
    lines.append(f"  {currency}{current:.2f} / {currency}{target:.2f}  {remaining_str}")
    if ratio >= 1.0:
        lines.append("  🎉 GOAL REACHED!")
    return "\n".join(lines)


# ── 37. Workout plan ────────────────────────────────────────────────────────

def render_workout_plan(
    days: list[tuple[str, str, bool]],
    label: str = "",
) -> str:
    """Weekly calendar grid with streak flame."""
    if not days:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    completed = sum(1 for _, _, d in days if d)
    # ── Calendar grid: 7-day week as filled/empty cells ──
    cells = []
    for _, _, done in days:
        cells.append("█" if done else "░")
    week = "".join(cells)
    lines.append(f"  Week: [{week}]")
    # ── Day entries with flame streak ──
    streak = 0
    max_streak = 0
    for day, exercise, done in days:
        if done:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
        mark = "🔥" if done else "  "
        state = "✓" if done else "→"
        fill = "▓" * (8 if done else 0) + "░" * (0 if done else 8)
        lines.append(f"  {mark} {day:<10} {state} {exercise:<25} [{fill}]")
    # ── Streak flame + completion donut ──
    r = completed / max(len(days), 1)
    filled = int(r * 10)
    ring = "●" * filled + "○" * (10 - filled)
    flame = "🔥" * min(max_streak, 5) if max_streak else "💤"
    lines.append(f"  ── [{ring}] {completed}/{len(days)} done · streak: {max_streak} {flame}")
    return "\n".join(lines)


# ── 38. Reading list ────────────────────────────────────────────────────────

def render_reading_list(
    books: list[tuple[str, str, float]],
    width: int = 15,
    label: str = "",
) -> str:
    """Book reading status.  ``books = [(title, author, progress_0_1), ...]``."""
    if not books:
        return "(no data)"
    lines = []
    if label:
        lines.append(label)
    for title, author, progress in books:
        bar = _bar(progress, width)
        pct = f"{progress * 100:.0f}%"
        icon = "✓" if progress >= 1.0 else ("📖" if progress > 0 else "📕")
        lines.append(f"  {icon} {title:<30} by {author:<15} │{bar}│ {pct}")
    return "\n".join(lines)


# ── 39. Wishlist ────────────────────────────────────────────────────────────

def render_wishlist(
    items: list[tuple[str, float, str]],
    width: int = 15,
    label: str = "",
    currency: str = "$",
) -> str:
    """Desired items display.  ``items = [(name, price, priority), ...]``."""
    if not items:
        return "(no data)"
    name_w = max(len(n) for n, _, _ in items)
    max_price = max(p for _, p, _ in items) or 1.0
    lines = []
    if label:
        lines.append(label)
    priority_icon = {"high": "🔥", "medium": "⭐", "low": "○"}
    for name, price, priority in items:
        bar = _bar(price / max_price, width, "▓", "░")
        icon = priority_icon.get(priority.lower(), "○")
        lines.append(f"  {icon} {name:<{name_w}} │{bar}│ {currency}{price:.2f} [{priority}]")
    total = sum(p for _, p, _ in items)
    lines.append(f"  ── {len(items)} items, {currency}{total:.2f} total")
    return "\n".join(lines)


# ── 40. Date countdown ──────────────────────────────────────────────────────

def render_date_countdown(
    event: str,
    days_remaining: int,
    total_days: int = 365,
    width: int = 30,
    label: str = "",
) -> str:
    """Days until event bar."""
    ratio = max(0, 1 - days_remaining / total_days) if total_days else 0
    bar = _bar(ratio, width)
    pct = ratio * 100
    lines = []
    if label:
        lines.append(label)
    lines.append(f"  📅 {event}")
    lines.append(f"  [{bar}] {pct:.0f}% elapsed")
    lines.append(f"  {days_remaining} days remaining")
    if days_remaining <= 0:
        lines.append("  🎉 TODAY!")
    return "\n".join(lines)


__all__ = [
    "render_sentiment_gauge",
    "render_word_count",
    "render_reading_progress",
    "render_mood_tracker",
    "render_habit_tracker",
    "render_task_priority",
    "render_meeting_agenda",
    "render_budget_tracker",
    "render_expense_breakdown",
    "render_weekly_schedule",
    "render_countdown",
    "render_star_rating",
    "render_poll_results",
    "render_survey_matrix",
    "render_decision_matrix",
    "render_pros_cons",
    "render_progress_wheel",
    "render_fitness_stats",
    "render_recipe_steps",
    "render_checklist",
    "render_travel_itinerary",
    "render_study_progress",
    "render_flashcard_scores",
    "render_quiz_results",
    "render_todo_board",
    "render_price_comparison",
    "render_review_summary",
    "render_mind_map",
    "render_contact_card",
    "render_gratitude_log",
    "render_water_intake",
    "render_sleep_tracker",
    "render_meditation_log",
    "render_mood_timeline",
    "render_life_balance",
    "render_savings_goal",
    "render_workout_plan",
    "render_reading_list",
    "render_wishlist",
    "render_date_countdown",
]

# Fail-open hardening: every render_* coerces hostile args and never raises.
harden(globals())
