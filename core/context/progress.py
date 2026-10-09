"""S6: Progress renderer — Apple-grade Unicode bars and ETA strings."""

from __future__ import annotations

from typing import Any

FILL = "\u2588"  # █
EMPTY = "\u2591"  # ░


def _float(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else default
    except Exception:  # noqa: BLE001
        return default


def _int(v: Any, default: int = 0, lo: int = 0, hi: int = 10**6) -> int:
    try:
        n = int(_float(v, float(default)))
    except Exception:  # noqa: BLE001
        n = default
    return max(lo, min(hi, n))


def _str(v: Any) -> str:
    try:
        return v if isinstance(v, str) else ("" if v is None else str(v))
    except Exception:  # noqa: BLE001
        return ""


def render_bar(ratio: float, width: int = 20, label: str = "") -> str:
    """Return ``'label ████████░░░░░░░░░░░░ 40%'``.

    Ratio is clamped to 0–1.  Deterministic: no ANSI, no clock reads.
    """
    try:
        r = max(0.0, min(1.0, _float(ratio)))
        width = _int(width, 20, 0, 200)
        label = _str(label)
        filled = round(r * width) if width > 0 else 0
        bar = FILL * filled + EMPTY * max(0, width - filled)
        pct = f"{r * 100:.0f}%"
        if label:
            return f"{label} {bar} {pct}" if bar else f"{label} {pct}"
        return f"{bar} {pct}" if bar else pct
    except Exception:  # noqa: BLE001 — fail-open
        return "—"


def render_eta(elapsed_ms: int, ratio: float) -> str:
    """Return ``'~2m 14s'`` or ``'—'`` when ratio is 0.

    *elapsed_ms* is milliseconds so far; *ratio* is completion 0–1.
    """
    try:
        elapsed_ms = _int(elapsed_ms, 0, 0, 10**9)
        ratio = _float(ratio)
        if ratio <= 0 or elapsed_ms <= 0:
            return "\u2014"  # —
        r = min(1.0, ratio)
        total_ms = elapsed_ms / r
        remaining_s = max(0, int((total_ms - elapsed_ms) / 1000))
        if remaining_s < 60:
            return f"~{remaining_s}s"
        minutes, seconds = divmod(remaining_s, 60)
        if minutes >= 60:
            hours, minutes = divmod(minutes, 60)
            return f"~{hours}h {minutes:02d}m"
        return f"~{minutes}m {seconds:02d}s"
    except Exception:  # noqa: BLE001 — fail-open
        return "\u2014"


__all__ = ["render_bar", "render_eta"]
