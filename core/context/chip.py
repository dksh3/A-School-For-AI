# core/context/chip.py
from __future__ import annotations


def fmt_tokens(count: int) -> str:
    if count >= 1_000_000:
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
    if blocks_added > 0:
        noun = "block" if blocks_added == 1 else "blocks"
        parts = [f"[school] compacted {blocks_added} {noun}", "restorable"]
        if restores > 0:
            parts.append(f"{restores} restored")
        return " · ".join(parts)
    if used_ratio is None:
        return ""
    parts = [f"[school] ctx {round(used_ratio * 100)}%"]
    if saved_tokens > 0:
        sign = "−" if saved_tokens > 0 else ""
        parts.append(f"{sign}{fmt_tokens(saved_tokens)} tok")
    if spend_usd is not None:
        parts.append(f"${spend_usd:.2f}")
    return " · ".join(parts)


__all__ = ["build_chip", "fmt_tokens"]
