"""S6: Bar graph builder — horizontal bars sorted by value descending."""

from __future__ import annotations

from typing import Any

from core.context.progress import EMPTY, FILL


def _float(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else default
    except Exception:  # noqa: BLE001
        return default


def _str(v: Any) -> str:
    try:
        return v if isinstance(v, str) else ("" if v is None else str(v))
    except Exception:  # noqa: BLE001
        return ""


def _compact(n: float) -> str:
    """Return ``'1.2k'`` / ``'3.4M'`` / ``'567'`` / ``'1.5'``."""
    try:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}k"
        if n == int(n):
            return str(int(n))
        return f"{n:.1f}"
    except Exception:  # noqa: BLE001
        return "0"


def render_bar_graph(items: list[tuple[str, float]], width: int = 24) -> str:
    """Return a multi-line horizontal bar graph sorted by value descending.

    Each line: ``'label ▕████████░░░░░░░░░░░░░░░░▏ 1.2k'``
    """
    try:
        width = max(0, min(200, int(width) if isinstance(width, (int, float)) else 24))
    except Exception:  # noqa: BLE001
        width = 24
    try:
        if not items:
            return "(no data)"
        pairs: list[tuple[str, float]] = []
        for it in items:
            try:
                seq = list(it)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                seq = [it]
            name = _str(seq[0]) if seq else ""
            value = _float(seq[1]) if len(seq) > 1 else 0.0
            pairs.append((name, value))
        if not pairs:
            return "(no data)"
        sorted_items = sorted(pairs, key=lambda x: x[1], reverse=True)
        max_val = max(v for _, v in sorted_items) or 1.0
        label_w = max(len(label) for label, _ in sorted_items)
        lines = []
        for label, value in sorted_items:
            ratio = max(0.0, value / max_val) if max_val else 0.0
            filled = round(ratio * width)
            bar = FILL * filled + EMPTY * max(0, width - filled)
            lines.append(f"{label:<{label_w}} \u258d{bar}\u2591 {_compact(value)}")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 — fail-open
        return "(no data)"


__all__ = ["render_bar_graph"]
