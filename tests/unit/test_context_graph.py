"""S6 tests: bar graph builder."""

from __future__ import annotations

from core.context.graph import render_bar_graph


class TestBarGraph:
    def test_empty(self) -> None:
        assert render_bar_graph([]) == "(no data)"

    def test_sorted_descending(self) -> None:
        got = render_bar_graph([("a", 1), ("b", 3), ("c", 2)])
        lines = got.splitlines()
        assert lines[0].startswith("b")
        assert lines[1].startswith("c")
        assert lines[2].startswith("a")

    def test_compact_numbers(self) -> None:
        got = render_bar_graph([("x", 1500)])
        assert "1.5k" in got

    def test_single_item(self) -> None:
        got = render_bar_graph([("only", 42)])
        assert "only" in got
        assert "42" in got
