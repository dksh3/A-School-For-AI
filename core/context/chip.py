# core/context/chip.py
from __future__ import annotations

from typing import Any


def _int(v: Any) -> int:
    try:
        n = int(float(v))
        return max(-(10**9), min(10**9, n))
    except Exception:  # noqa: BLE001
        return 0


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def fmt_tokens(count: int) -> str:
    count = _int(count)
    if count >= 999_500:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)


def build_chip(
    *,
    blocks_added: int = 0,
    restores: int = 0,
    saved_tokens: int = 0,
    used_ratio: float | None = None,
    spend_usd: float | None = None,
) -> str:
    """Apple-grade status chip. Calm, sparse, middle-dot segments."""
    try:
        blocks_added = _int(blocks_added)
        restores = _int(restores)
        saved_tokens = _int(saved_tokens)
        used_ratio = _opt_float(used_ratio)
        spend_usd = _opt_float(spend_usd)
        if blocks_added > 0 or restores > 0:
            parts = []
            if blocks_added > 0:
                noun = "block" if blocks_added == 1 else "blocks"
                parts.append(f"[school] compacted {blocks_added} {noun}")
                parts.append("restorable")
            if restores > 0:
                noun = "block" if restores == 1 else "blocks"
                parts.append(f"{restores} restored")
            if used_ratio is not None:
                parts.append(f"ctx {round(used_ratio * 100)}%")
            if saved_tokens > 0:
                parts.append(f"−{fmt_tokens(saved_tokens)} tok")
            if spend_usd is not None:
                parts.append(f"${spend_usd:.2f}")
            return " · ".join(parts)
        if used_ratio is None:
            return ""
        parts = [f"[school] ctx {round(used_ratio * 100)}%"]
        if saved_tokens > 0:
            parts.append(f"−{fmt_tokens(saved_tokens)} tok")
        if spend_usd is not None:
            parts.append(f"${spend_usd:.2f}")
        return " · ".join(parts)
    except Exception:  # noqa: BLE001 — fail-open
        return ""


__all__ = ["build_chip", "fmt_tokens"]
