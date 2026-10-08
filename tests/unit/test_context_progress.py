"""S6 tests: progress renderer."""

from __future__ import annotations

from core.context.progress import render_bar, render_eta


class TestRenderBar:
    def test_at_zero(self) -> None:
        assert render_bar(0.0, width=10) == "\u2591" * 10 + " 0%"

    def test_at_fifty(self) -> None:
        got = render_bar(0.5, width=10)
        assert got == "\u2588" * 5 + "\u2591" * 5 + " 50%"

    def test_at_full(self) -> None:
        got = render_bar(1.0, width=10)
        assert got == "\u2588" * 10 + " 100%"

    def test_clamps_over(self) -> None:
        assert render_bar(1.5, width=10) == "\u2588" * 10 + " 100%"

    def test_clamps_under(self) -> None:
        assert render_bar(-0.5, width=10) == "\u2591" * 10 + " 0%"

    def test_with_label(self) -> None:
        got = render_bar(0.5, width=10, label="ctx")
        assert got.startswith("ctx ")
        assert got.endswith(" 50%")


class TestRenderEta:
    def test_zero_ratio(self) -> None:
        assert render_eta(1000, 0.0) == "\u2014"

    def test_zero_elapsed(self) -> None:
        assert render_eta(0, 0.5) == "\u2014"

    def test_seconds(self) -> None:
        # 10s elapsed at 50% -> ~10s remaining
        assert render_eta(10_000, 0.5) == "~10s"

    def test_minutes(self) -> None:
        # 60s elapsed at 25% -> ~180s = ~3m 00s remaining
        assert render_eta(60_000, 0.25) == "~3m 00s"
