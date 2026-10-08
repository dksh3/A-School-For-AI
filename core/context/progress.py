"""S6: Progress renderer — Apple-grade Unicode bars and ETA strings."""

from __future__ import annotations

FILL = "\u2588"  # █
EMPTY = "\u2591"  # ░


def render_bar(ratio: float, width: int = 20, label: str = "") -> str:
    """Return ``'label ████████░░░░░░░░░░░░ 40%'``.

    Ratio is clamped to 0–1.  Deterministic: no ANSI, no clock reads.
    """
    r = max(0.0, min(1.0, ratio))
    filled = round(r * width)
    bar = FILL * filled + EMPTY * (width - filled)
    pct = f"{r * 100:.0f}%"
    if label:
        return f"{label} {bar} {pct}"
    return f"{bar} {pct}"


def render_eta(elapsed_ms: int, ratio: float) -> str:
    """Return ``'~2m 14s'`` or ``'—'`` when ratio is 0.

    *elapsed_ms* is milliseconds so far; *ratio* is completion 0–1.
    """
    if ratio <= 0 or elapsed_ms <= 0:
        return "\u2014"  # —
    total_ms = elapsed_ms / ratio
    remaining_s = max(0, int((total_ms - elapsed_ms) / 1000))
    if remaining_s < 60:
        return f"~{remaining_s}s"
    minutes, seconds = divmod(remaining_s, 60)
    return f"~{minutes}m {seconds:02d}s"


__all__ = ["render_bar", "render_eta"]
