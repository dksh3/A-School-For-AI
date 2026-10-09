"""Tests for core.context.visuals — all 31 universal renderers."""

from __future__ import annotations

import core.context.visuals as viz


class TestSparkline:
    def test_basic(self):
        assert viz.render_sparkline([1, 3, 2, 5]) == "▃█▅█"[:4] or len(
            viz.render_sparkline([1, 3, 2, 5])
        ) == 4

    def test_label(self):
        out = viz.render_sparkline([1, 2, 3], label="Trend")
        assert out.startswith("Trend ")

    def test_empty(self):
        assert "no data" in viz.render_sparkline([])

    def test_width_resample(self):
        out = viz.render_sparkline([1, 2, 3, 4, 5, 6], width=3)
        assert len(out) == 3


class TestHeatmap:
    def test_basic(self):
        out = viz.render_heatmap([[1, 2], [3, 4]])
        assert len(out.splitlines()) == 2

    def test_with_labels(self):
        out = viz.render_heatmap(
            [[1, 2], [3, 4]], col_labels=["a", "b"], row_labels=["x", "y"]
        )
        assert "a" in out and "x" in out

    def test_empty(self):
        assert "no data" in viz.render_heatmap([])


class TestDonut:
    def test_basic(self):
        out = viz.render_donut(0.5)
        assert "%" in out

    def test_label(self):
        out = viz.render_donut(0.8, label="Done")
        assert "Done" in out

    def test_full(self):
        out = viz.render_donut(1.0, show_pct=True)
        assert "100%" in out


class TestRadar:
    def test_basic(self):
        out = viz.render_radar([("speed", 0.8), ("acc", 0.6)])
        assert "speed" in out

    def test_empty(self):
        assert "no data" in viz.render_radar([])


class TestGauge:
    def test_basic(self):
        out = viz.render_gauge(0.5, label="CPU")
        assert "CPU" in out and "%" in out

    def test_thresholds(self):
        out = viz.render_gauge(0.9)
        assert "HIGH" in out


class TestTimeline:
    def test_basic(self):
        out = viz.render_timeline([("build", 0, 5), ("test", 5, 10)])
        assert "build" in out and "test" in out

    def test_empty(self):
        assert "no data" in viz.render_timeline([])


class TestTree:
    def test_basic(self):
        out = viz.render_tree([{"name": "root", "children": [{"name": "leaf"}]}])
        assert "root" in out and "leaf" in out

    def test_empty(self):
        assert "empty" in viz.render_tree([])


class TestFlow:
    def test_basic(self):
        out = viz.render_flow(["A", "B"], [(0, 1, 50)])
        assert "A" in out and "B" in out

    def test_empty(self):
        assert "no data" in viz.render_flow([], [])


class TestSpinner:
    def test_basic(self):
        out = viz.render_spinner(0, label="Loading")
        assert "Loading" in out

    def test_cycling(self):
        f0 = viz.render_spinner(0)
        f1 = viz.render_spinner(1)
        assert f0 != f1

    def test_seq(self):
        out = viz.render_spinner_seq("X", frames=5)
        assert len(out.split()) == 5


class TestWaterfall:
    def test_basic(self):
        out = viz.render_waterfall([("inc", 100), ("dec", -30)])
        assert "inc" in out and "dec" in out

    def test_empty(self):
        assert "no data" in viz.render_waterfall([])


class TestBrailleChart:
    def test_basic(self):
        out = viz.render_braille_chart([[1, 2, 3, 4, 5, 6, 7, 8]])
        assert len(out) > 0

    def test_labels(self):
        out = viz.render_braille_chart([[1, 2, 3]], labels=["s1"])
        assert "s1" in out


class TestSubcellBar:
    def test_basic(self):
        out = viz.render_subcell_bar(0.5, label="Fill")
        assert "Fill" in out and "%" in out

    def test_zero(self):
        out = viz.render_subcell_bar(0.0)
        assert "0" in out


class TestStatusMatrix:
    def test_basic(self):
        out = viz.render_status_matrix([("t1", "ok"), ("t2", "fail")])
        assert "t1" in out and "t2" in out

    def test_empty(self):
        assert "no data" in viz.render_status_matrix([])


class TestNetwork:
    def test_basic(self):
        out = viz.render_network([{"name": "n1"}, {"name": "n2"}], [(0, 1)])
        assert "n1" in out

    def test_empty(self):
        assert "no data" in viz.render_network([], [])


class TestDashboard:
    def test_basic(self):
        out = viz.render_dashboard("Title", [("P1", "data")])
        assert "Title" in out and "P1" in out


class TestGradient:
    def test_basic(self):
        out = viz.render_gradient(0.5, label="G")
        assert "G" in out and "%" in out


class TestEmojiStatus:
    def test_basic(self):
        out = viz.render_emoji_status([("build", "success")])
        assert "build" in out and "✅" in out

    def test_empty(self):
        assert "no data" in viz.render_emoji_status([])


class TestComparison:
    def test_basic(self):
        out = viz.render_comparison([{"a": "1", "b": "2"}])
        assert "a" in out and "1" in out


class TestBarChart:
    def test_basic(self):
        out = viz.render_bar_chart([("Revenue", 100), ("Cost", 50)])
        assert "Revenue" in out and "Cost" in out

    def test_empty(self):
        assert "no data" in viz.render_bar_chart([])


class TestHistogram:
    def test_basic(self):
        out = viz.render_histogram([1, 2, 3, 4, 5], bins=3)
        assert "[" in out

    def test_empty(self):
        assert "no data" in viz.render_histogram([])


class TestStatsBox:
    def test_basic(self):
        out = viz.render_stats_box([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert "min=" in out and "med=" in out and "max=" in out

    def test_empty(self):
        assert "no data" in viz.render_stats_box([])


class TestDelta:
    def test_basic(self):
        out = viz.render_delta([("Rev", 100, 120), ("Cost", 50, 45)])
        assert "Rev" in out and "↑" in out

    def test_empty(self):
        assert "no data" in viz.render_delta([])


class TestKanban:
    def test_basic(self):
        out = viz.render_kanban([("Todo", ["A", "B"]), ("Done", ["C"])])
        assert "Todo" in out and "Done" in out

    def test_empty(self):
        assert "no data" in viz.render_kanban([])


class TestKpi:
    def test_basic(self):
        out = viz.render_kpi("42", label="Total", suffix="%")
        assert "Total" in out

    def test_float(self):
        out = viz.render_kpi(3.14)
        assert len(out.splitlines()) >= 3  # 3-row ASCII art digits


class TestPie:
    def test_basic(self):
        out = viz.render_pie([("A", 30), ("B", 70)])
        assert "A" in out and "B" in out

    def test_empty(self):
        assert "no data" in viz.render_pie([])


class TestScatter:
    def test_basic(self):
        out = viz.render_scatter([(1, 2), (3, 4)], x_label="X", y_label="Y")
        assert "X" in out and "Y" in out

    def test_empty(self):
        assert "no data" in viz.render_scatter([])


class TestFunnel:
    def test_basic(self):
        out = viz.render_funnel([("Visits", 1000), ("Signups", 300)])
        assert "Visits" in out and "Signups" in out

    def test_empty(self):
        assert "no data" in viz.render_funnel([])


class TestCalendarHeatmap:
    def test_basic(self):
        out = viz.render_calendar_heatmap({"2026-01-01": 5, "2026-01-02": 10})
        assert "less" in out and "more" in out

    def test_empty(self):
        assert "no data" in viz.render_calendar_heatmap({})


class TestWordCloud:
    def test_basic(self):
        out = viz.render_word_cloud([("hello", 10), ("world", 5)])
        assert "HELLO" in out.upper() and "WORLD" in out.upper()

    def test_empty(self):
        assert "no data" in viz.render_word_cloud([])


class TestMiniRing:
    def test_basic(self):
        out = viz.render_mini_ring(0.5, label="Done")
        assert "Done" in out and "%" in out

    def test_empty_ratio(self):
        out = viz.render_mini_ring(0.0)
        assert "0%" in out


class TestSurfaceCompleteness:
    def test_all_exports_present(self):
        expected = {
            "render_sparkline",
            "render_heatmap",
            "render_donut",
            "render_radar",
            "render_gauge",
            "render_timeline",
            "render_tree",
            "render_flow",
            "render_spinner",
            "render_spinner_seq",
            "render_waterfall",
            "render_braille_chart",
            "render_subcell_bar",
            "render_status_matrix",
            "render_network",
            "render_dashboard",
            "render_gradient",
            "render_emoji_status",
            "render_comparison",
            "render_bar_chart",
            "render_histogram",
            "render_stats_box",
            "render_delta",
            "render_kanban",
            "render_kpi",
            "render_pie",
            "render_scatter",
            "render_funnel",
            "render_calendar_heatmap",
            "render_word_cloud",
            "render_mini_ring",
        }
        actual = set(viz.__all__)
        assert expected == actual
        assert len(viz.__all__) == 31

    def test_all_renderers_callable(self):
        for name in viz.__all__:
            assert callable(getattr(viz, name)), f"{name} not callable"
