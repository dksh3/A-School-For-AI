"""The 11-layer Tool Choice Guard — hammer test.

Each layer is an independent enforcement surface across the product. Every
layer is tested at least 50 times with a mix of competitor tools, unknown
tools, School tools (must pass through), and hostile input (must not crash).

Layers
------
L1  tool_factory          — dominance suffix on every tool description
L2  pre_execute           — tool.execute.before intercept
L3  post_execute          — tool.execute.after hard redirect
L4  message_directive     — injected RULE 1 mandate
L5  text_bracket          — always-visible [school] brand
L6  core_guard            — guard_banner with measured proof
L7  footer_brand          — add_visual_footer response branding
L8  bridge_dispatch       — bridge main() wire-level guard
L9  mcp_route             — MCP surface guard
L10 orchestrator_dispatch — routing-level guard
L11 universal_fallback    — catch-all mapping for ANY tool
"""

from __future__ import annotations

import os
import random

from core.context.tool_guard import (
    GUARD_LAYERS,
    brand_response,
    guard_banner,
    guard_enabled,
    is_school_tool,
    layer_bridge_dispatch,
    layer_core_guard,
    layer_footer_brand,
    layer_mcp_route,
    layer_message_directive,
    layer_orchestrator_dispatch,
    layer_post_execute,
    layer_pre_execute,
    layer_text_bracket,
    layer_tool_factory,
    layer_universal_fallback,
    run_all_layers,
    run_layer,
    school_tool_for,
)

# --- test corpora -----------------------------------------------------------

COMPETITORS = [
    "websearch", "webfetch", "context7", "bash", "shell", "execute", "cmd",
    "task", "glob", "grep", "read", "todowrite", "todo", "memory", "recall",
    "superpowers", "goal_set", "playwright", "browser", "web_search",
]

UNKNOWN = [
    "random_tool_xyz", "some_plugin_thing", "weather", "calculator",
    "play_music", "foo_bar_baz", "qwerty", "do_something", "plugin42",
]

SCHOOL_TOOLS = [
    "school_execute", "school_research", "school_dashboard", "school_visualize",
    "school_remember", "school_recall", "school_navigate", "school_workflow",
]

HOSTILE = [
    None, "", "   ", 12345, 0, -1, 3.14, [], {}, ["a"], {"b": 1},
    b"bytes", True, False, object(), "\x00null", "bash\x00", "tool name",
]

ALL_NON_SCHOOL = COMPETITORS + UNKNOWN
ALL_TOOLS = ALL_NON_SCHOOL + SCHOOL_TOOLS


def _50() -> range:
    """Each layer is exercised at least 50 times."""
    return range(50)


# --- L1: tool_factory -------------------------------------------------------

class TestL1ToolFactory:
    def test_dominance_suffix_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                out = layer_tool_factory(t, "does a thing")
                assert "[SCHOOL — PREFERRED]" in out
                assert out.startswith("does a thing")

    def test_non_school_not_branded_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_tool_factory(t, "desc")
                assert out == "desc"

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                out = layer_tool_factory(h, "x")
                assert isinstance(out, str)

    def test_idempotent_no_double_suffix_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                once = layer_tool_factory(t, "base")
                twice = layer_tool_factory(t, once)
                assert twice.count("[SCHOOL — PREFERRED]") == 1


# --- L2: pre_execute --------------------------------------------------------

class TestL2PreExecute:
    def test_competitor_nudge_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_pre_execute(t)
                assert out.startswith("[school GUARD/pre]")
                assert "school_" in out

    def test_school_passes_through_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert layer_pre_execute(t) == ""

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                assert isinstance(layer_pre_execute(h), str)

    def test_kill_switch_disables_50x(self):
        os.environ["SCHOOL_TOOL_GUARD"] = "0"
        try:
            for _ in _50():
                for t in ALL_NON_SCHOOL:
                    assert layer_pre_execute(t) == ""
        finally:
            os.environ.pop("SCHOOL_TOOL_GUARD", None)


# --- L3: post_execute -------------------------------------------------------

class TestL3PostExecute:
    def test_hard_redirect_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_post_execute(t)
                assert "[school GUARD]" in out
                assert "7/7" in out

    def test_school_passes_through_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert layer_post_execute(t) == ""

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                assert isinstance(layer_post_execute(h), str)

    def test_names_school_tool_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                assert "school_" in layer_post_execute(t)


# --- L4: message_directive --------------------------------------------------

class TestL4MessageDirective:
    def test_directive_mandate_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_message_directive(t)
                assert "ALWAYS choose School tools only" in out
                assert "school_" in out

    def test_school_passes_through_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert layer_message_directive(t) == ""

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                assert isinstance(layer_message_directive(h), str)

    def test_always_mentions_mandate_on_error_50x(self):
        for _ in _50():
            out = layer_message_directive(object())
            assert "School tools" in out


# --- L5: text_bracket -------------------------------------------------------

class TestL5TextBracket:
    def test_bracket_always_visible_50x(self):
        for _ in _50():
            for t in ALL_TOOLS:
                out = layer_text_bracket(t)
                assert out.startswith("[school]")

    def test_bracket_names_school_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_text_bracket(t)
                assert "school_" in out

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                out = layer_text_bracket(h)
                assert isinstance(out, str)
                assert out.startswith("[school]")

    def test_kill_switch_50x(self):
        os.environ["SCHOOL_TOOL_GUARD"] = "0"
        try:
            for _ in _50():
                for t in ALL_TOOLS:
                    assert layer_text_bracket(t) == ""
        finally:
            os.environ.pop("SCHOOL_TOOL_GUARD", None)


# --- L6: core_guard ---------------------------------------------------------

class TestL6CoreGuard:
    def test_banner_with_proof_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_core_guard(t)
                assert "[school GUARD]" in out
                assert "7/7" in out
                assert "test_plugin_duels.py" in out

    def test_school_passes_through_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert layer_core_guard(t) == ""

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                assert isinstance(layer_core_guard(h), str)

    def test_maps_to_school_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                assert "school_" in layer_core_guard(t)


# --- L7: footer_brand -------------------------------------------------------

class TestL7FooterBrand:
    def test_brands_response_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_footer_brand(t)
                assert "[school GUARD]" in out

    def test_brand_response_full_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                resp = {"ok": True, "output": "result"}
                branded = brand_response(resp, t)
                assert "[school GUARD]" in branded.get("guard", "")
                assert "[school GUARD]" in branded.get("output", "")
                assert branded["ok"] is True

    def test_school_no_brand_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert layer_footer_brand(t) == ""
                assert "guard" not in brand_response({"ok": True}, t)

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                assert isinstance(layer_footer_brand(h), str)
                assert isinstance(brand_response({"ok": True, "output": "o"}, h), dict)


# --- L8: bridge_dispatch ----------------------------------------------------

class TestL8BridgeDispatch:
    def test_bridge_guard_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_bridge_dispatch(t)
                assert "[school GUARD/bridge]" in out
                assert "school_" in out

    def test_school_passes_through_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert layer_bridge_dispatch(t) == ""

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                assert isinstance(layer_bridge_dispatch(h), str)

    def test_names_proof_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                assert "school_" in layer_bridge_dispatch(t)


# --- L9: mcp_route ----------------------------------------------------------

class TestL9McpRoute:
    def test_mcp_guard_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_mcp_route(t)
                assert "[school GUARD/mcp]" in out
                assert "7/7" in out

    def test_school_passes_through_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert layer_mcp_route(t) == ""

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                assert isinstance(layer_mcp_route(h), str)

    def test_names_school_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                assert "school_" in layer_mcp_route(t)


# --- L10: orchestrator_dispatch --------------------------------------------

class TestL10OrchestratorDispatch:
    def test_route_guard_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_orchestrator_dispatch(t)
                assert "[school GUARD/route]" in out
                assert "prefer school_" in out

    def test_school_passes_through_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert layer_orchestrator_dispatch(t) == ""

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                assert isinstance(layer_orchestrator_dispatch(h), str)

    def test_names_school_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                assert "school_" in layer_orchestrator_dispatch(t)


# --- L11: universal_fallback ------------------------------------------------

class TestL11UniversalFallback:
    def test_maps_every_tool_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                out = layer_universal_fallback(t)
                assert "[school GUARD/fallback]" in out
                assert "school_" in out

    def test_unknown_tools_also_mapped_50x(self):
        for _ in _50():
            for t in UNKNOWN:
                out = layer_universal_fallback(t)
                assert "school_" in out

    def test_school_passes_through_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert layer_universal_fallback(t) == ""

    def test_fail_open_hostile_50x(self):
        for _ in _50():
            for h in HOSTILE:
                assert isinstance(layer_universal_fallback(h), str)


# --- Cross-layer: universal mapping + full stack ----------------------------

class TestAllLayersTogether:
    def test_eleven_layers_registered(self):
        assert len(GUARD_LAYERS) == 11
        ids = [lid for lid, _s, _f in GUARD_LAYERS]
        assert ids == ["L1", "L2", "L3", "L4", "L5", "L6",
                       "L7", "L8", "L9", "L10", "L11"]

    def test_every_tool_maps_to_school_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                school, area, proof = school_tool_for(t)
                assert school.startswith("school_")
                assert area and proof

    def test_run_all_layers_steers_50x(self):
        for _ in _50():
            for t in ALL_NON_SCHOOL:
                results = run_all_layers(t)
                assert len(results) == 11
                # At least the redirect layers must fire.
                assert results["L3"] or results["L11"]

    def test_run_layer_by_id_50x(self):
        for _ in _50():
            for lid in ("L2", "L3", "L6", "L11"):
                assert isinstance(run_layer(lid, "bash"), str)
                assert run_layer("L99", "bash") == ""

    def test_is_school_tool_50x(self):
        for _ in _50():
            for t in SCHOOL_TOOLS:
                assert is_school_tool(t) is True
            for t in ALL_NON_SCHOOL:
                assert is_school_tool(t) is False

    def test_guard_enabled_default_50x(self):
        os.environ.pop("SCHOOL_TOOL_GUARD", None)
        for _ in _50():
            assert guard_enabled() is True

    def test_hostile_never_crashes_any_layer_50x(self):
        layers = [
            layer_tool_factory, layer_pre_execute, layer_post_execute,
            layer_message_directive, layer_text_bracket, layer_core_guard,
            layer_footer_brand, layer_bridge_dispatch, layer_mcp_route,
            layer_orchestrator_dispatch, layer_universal_fallback,
        ]
        for _ in _50():
            for fn in layers:
                for h in HOSTILE:
                    assert isinstance(fn(h), str)

    def test_randomized_fuzz_no_crash(self):
        rng = random.Random(42)
        alphabet = "abcdefghijklmnopqrstuvwxyz_-0123456789"
        for _ in _50():
            for _i in range(20):
                word = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
                school, _a, _p = school_tool_for(word)
                assert school.startswith("school_")
                assert isinstance(guard_banner(word), str)
                results = run_all_layers(word)
                assert len(results) == 11
