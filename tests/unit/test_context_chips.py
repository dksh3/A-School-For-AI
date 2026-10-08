from __future__ import annotations

from core.context.chip import build_chip, fmt_tokens


def test_fmt_tokens() -> None:
    assert fmt_tokens(0) == "0"
    assert fmt_tokens(900) == "900"
    assert fmt_tokens(18400) == "18.4k"
    assert fmt_tokens(1840000) == "1.8M"


def test_compaction_chip() -> None:
    assert build_chip(blocks_added=2) == "[school] compacted 2 blocks · restorable"


def test_compaction_chip_single_and_restored() -> None:
    assert build_chip(blocks_added=1) == "[school] compacted 1 block · restorable"
    assert (
        build_chip(blocks_added=2, restores=1)
        == "[school] compacted 2 blocks · restorable · 1 restored"
    )


def test_usage_chip_with_savings_and_spend() -> None:
    assert (
        build_chip(used_ratio=0.62, saved_tokens=18400, spend_usd=0.07)
        == "[school] ctx 62% · −18.4k tok · $0.07"
    )


def test_usage_chip_minimal() -> None:
    assert build_chip(used_ratio=0.31) == "[school] ctx 31%"
    assert build_chip(used_ratio=0.31, saved_tokens=900) == "[school] ctx 31% · −900 tok"


def test_compaction_wins_when_both_given() -> None:
    out = build_chip(blocks_added=3, used_ratio=0.9)
    assert out.startswith("[school] compacted 3 blocks")
