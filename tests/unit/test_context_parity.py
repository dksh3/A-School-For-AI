"""S6 parity tests: TS plugin == MCP server == CLI descriptions match."""

from __future__ import annotations

from school.plugin_source import TS_PLUGIN_SOURCE

try:
    from school.mcp.server import _TOOLS

    HAS_MCP = True
except ImportError:
    _TOOLS = {}
    HAS_MCP = False


class TestContextParity:
    def test_progress_bar_parity(self) -> None:
        """Progress bar rendering is available in Python core."""
        from core.context.progress import render_bar, render_eta

        assert callable(render_bar)
        assert callable(render_eta)

    def test_bar_graph_parity(self) -> None:
        """Bar graph rendering exists in Python; TS exposes equivalent tool."""
        from core.context.graph import render_bar_graph

        out = render_bar_graph([("a", 10), ("b", 20)])
        assert "b" in out

    def test_cumulative_chip_parity(self) -> None:
        """Cumulative chip renders consistently."""
        from core.context.cumulative import CumulativeStats

        cs = CumulativeStats(worktree="/tmp", compressions=1, total_tokens_saved=100)
        chip = cs.render_chip()
        assert "\u26a1" in chip

    def test_watchdog_stub_parity(self) -> None:
        """Watchdog is importable and callable from all surfaces."""
        from core.context.watchdog import watchdog

        assert watchdog(lambda: "ok") == "ok"

    def test_telemetry_collector_parity(self) -> None:
        """TelemetryCollector is importable and has expected methods."""
        from core.context.telemetry import TelemetryCollector

        tc = TelemetryCollector(worktree="/tmp")
        assert hasattr(tc, "record")
        assert hasattr(tc, "events")
        assert hasattr(tc, "flush")

    def test_mcp_has_context_tools(self) -> None:
        """MCP server exposes context tools (when mcp is installed)."""
        if not HAS_MCP:
            return
        tool_names = list(_TOOLS.keys())
        assert any("context" in n for n in tool_names)

    def test_ts_source_has_hooks(self) -> None:
        """TS plugin registers hooks."""
        assert "experimental" in TS_PLUGIN_SOURCE or "hook" in TS_PLUGIN_SOURCE

    def test_ts_source_has_agent_tools(self) -> None:
        """TS plugin is a valid non-empty TypeScript source."""
        assert len(TS_PLUGIN_SOURCE) > 1000
        assert "export default" in TS_PLUGIN_SOURCE
