"""S6: Bar graph builder — horizontal bars sorted by value descending."""

from __future__ import annotations

from core.context.progress import EMPTY, FILL


def _compact(n: float) -> str:
    """Return ``'1.2k'`` / ``'3.4M'`` / ``'567'``."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(int(n))


def render_bar_graph(items: list[tuple[str, float]], width: int = 24) -> str:
    """Return a multi-line horizontal bar graph sorted by value descending.

    Each line: ``'label ▕████████░░░░░░░░░░░░░░░░▏ 1.2k'``
    """
    if not items:
        return "(no data)"
    sorted_items = sorted(items, key=lambda x: x[1], reverse=True)
    max_val = max(v for _, v in sorted_items) or 1.0
    label_w = max(len(label) for label, _ in sorted_items)
    lines = []
    for label, value in sorted_items:
        ratio = value / max_val if max_val else 0.0
        filled = round(ratio * width)
        bar = FILL * filled + EMPTY * (width - filled)
        lines.append(f"{label:<{label_w}} \u258d{bar}\u2591 {_compact(value)}")
    return "\n".join(lines)


__all__ = ["render_bar_graph"]
