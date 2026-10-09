"""Tests for OpenCode plugin execution hooks (per-execution School visibility).

The hooks make School run and show itself on EVERY tool execution and prompt:
- ``tool.execute.before`` — budgeted recall keyed to what the agent is doing
- ``tool.execute.after``  — always-on visible marker + context injection
- ``chat.message``        — prompt-time recall stash
- ``experimental.chat.messages.transform`` — one-shot prompt context injection
- ``experimental.text.complete`` — always-visible ``[school]`` status footer
- ``experimental.session.compacting`` - budget-pressure nudge during auto-compaction
"""

from __future__ import annotations

import re

from school.plugin_source import TS_PLUGIN_SOURCE

#: Hooks the plugin must register (exact OpenCode hook names).
EXPECTED_HOOKS = (
    "tool.execute.before",
    "tool.execute.after",
    "chat.message",
    "experimental.chat.messages.transform",
    "experimental.text.complete",
    "experimental.session.compacting",
)


def _hook_block(name: str) -> str:
    """Return the full source block of one plugin hook."""
    pattern = rf'"{re.escape(name)}": async \([\s\S]*?\n    \}},'
    match = re.search(pattern, TS_PLUGIN_SOURCE)
    assert match is not None, f"hook not found: {name}"
    return match.group(0)


class TestExecutionHooksRegistered:
    """The plugin registers every execution/prompt hook."""

    def test_all_expected_hooks_registered(self) -> None:
        for hook in EXPECTED_HOOKS:
            assert f'"{hook}"' in TS_PLUGIN_SOURCE, f"missing hook: {hook}"

    def test_tool_surface_unchanged(self) -> None:
        """The tool surface: 26 approved tools + three S2 context mirrors."""
        names = re.findall(r"^\s+(school_\w+): tool\(", TS_PLUGIN_SOURCE, re.MULTILINE)
        assert len(names) == 40, f"tool surface changed: {names}"


class TestStatusFooterAndDashboard:
    """The status footer and dashboard tool always show School state."""

    def test_footer_hook_appends_marked_line(self) -> None:
        block = _hook_block("experimental.text.complete")
        # Always-show behavior: the [school] bracket appears even with no tool used.
        assert "ALWAYS show the [school] bracket" in block
        assert "schoolFooter()" in block
        assert "output.text =" in block
        assert '[school]' in block

    def test_footer_state_covers_all_chips(self) -> None:
        for chip in ("route: ", "next: ", "ctx: ", "recall: ", "learn: ", "diag: "):
            assert f'"{chip}"' in TS_PLUGIN_SOURCE, chip
        assert "function schoolFooter()" in TS_PLUGIN_SOURCE
        assert "function schoolStatusParts()" in TS_PLUGIN_SOURCE

    def test_dashboard_tool_registered(self) -> None:
        assert "school_dashboard: tool(" in TS_PLUGIN_SOURCE
        assert '"School Dashboard"' in TS_PLUGIN_SOURCE
        assert "call once per prompt" in TS_PLUGIN_SOURCE
        assert "schoolStatusParts().join" in TS_PLUGIN_SOURCE

    def test_subsystems_record_status(self) -> None:
        assert "recordCtxSavings(" in TS_PLUGIN_SOURCE
        assert "schoolStatus.learn" in TS_PLUGIN_SOURCE
        assert "schoolStatus.route" in TS_PLUGIN_SOURCE
        assert "schoolStatus.recall" in TS_PLUGIN_SOURCE


class TestBeforeHook:
    """tool.execute.before runs a budgeted recall keyed to the execution."""

    def test_stashes_recall_by_call_id(self) -> None:
        block = _hook_block("tool.execute.before")
        assert "executionRecalls.set(input.callID" in block

    def test_query_is_built_from_tool_and_args(self) -> None:
        block = _hook_block("tool.execute.before")
        assert "buildExecutionQuery(input.tool, output.args)" in block

    def test_uses_shared_recall_for_execution(self) -> None:
        block = _hook_block("tool.execute.before")
        assert "recallForExecution(input.sessionID" in block

    def test_never_throws(self) -> None:
        block = _hook_block("tool.execute.before")
        assert "try {" in block
        assert "catch" in block

    def test_kills_switch_is_honoured(self) -> None:
        block = _hook_block("tool.execute.before")
        assert "hooksEnabled()" in block


class TestAfterHook:
    """tool.execute.after annotates EVERY execution and injects context."""

    def test_reads_and_clears_stash_by_call_id(self) -> None:
        block = _hook_block("tool.execute.after")
        assert "executionRecalls.get(input.callID" in block
        assert "executionRecalls.delete(input.callID" in block

    def test_title_marker_on_every_execution(self) -> None:
        """Marker is unconditional: hits, zero hits, and degraded all show."""
        assert "rec ? ` · school: ${rec.hits}`" in TS_PLUGIN_SOURCE
        assert '" · school: –"' in TS_PLUGIN_SOURCE

    def test_zero_hits_still_visible(self) -> None:
        """The marker expression keys on rec presence, not hit count."""
        block = _hook_block("tool.execute.after")
        marker_line = next(
            (ln for ln in block.splitlines() if "school: ${rec.hits}" in ln),
            "",
        )
        assert "rec ?" in marker_line, marker_line
        assert "rec.hits" not in marker_line.split("?")[0], "condition must not gate on hits"

    def test_context_block_injected_only_on_hits(self) -> None:
        block = _hook_block("tool.execute.after")
        assert "[school context]" in block
        assert "[/school]" in block
        assert "rec.hits > 0" in block

    def test_never_throws(self) -> None:
        block = _hook_block("tool.execute.after")
        assert "try {" in block
        assert "catch" in block


class TestPromptHooks:
    """chat.message recalls once per prompt; transform injects once."""

    def test_chat_message_stashes_by_session(self) -> None:
        block = _hook_block("chat.message")
        assert "promptRecalls.set(input.sessionID" in block
        assert "recallForExecution(input.sessionID" in block

    def test_chat_message_extracts_text_parts(self) -> None:
        block = _hook_block("chat.message")
        assert 'p.type === "text"' in block

    def test_transform_injects_only_after_user_turn(self) -> None:
        block = _hook_block("experimental.chat.messages.transform")
        assert 'info.role !== "user"' in block
        assert "promptRecalls.get(info.sessionID)" in block
        assert "promptRecalls.delete(info.sessionID)" in block

    def test_transform_pushes_marked_synthetic_text_part(self) -> None:
        block = _hook_block("experimental.chat.messages.transform")
        assert 'type: "text"' in block
        assert "synthetic: true" in block
        assert "[school context]" in block
        assert "[/school]" in block

    def test_both_prompt_hooks_never_throw(self) -> None:
        for hook in ("chat.message", "experimental.chat.messages.transform"):
            block = _hook_block(hook)
            assert "try {" in block, hook
            assert "catch" in block, hook


class TestRecallBudgetAndCostGuards:
    """Hook recalls are bounded: budgeted, thresholded, timeboxed, skippable."""

    def test_budget_constants_defined(self) -> None:
        assert "HOOK_LIMIT = 3" in TS_PLUGIN_SOURCE
        assert "HOOK_THRESHOLD = 0.2" in TS_PLUGIN_SOURCE
        assert "HOOK_BUDGET = 400" in TS_PLUGIN_SOURCE
        assert "HOOK_TIMEOUT_MS = 1500" in TS_PLUGIN_SOURCE

    def test_recall_uses_budget_constants(self) -> None:
        # Budget flows through knobs whose defaults are the HOOK_* consts.
        assert "confidence_threshold: knobs.recall_threshold" in TS_PLUGIN_SOURCE
        assert "context_budget: knobs.hook_budget" in TS_PLUGIN_SOURCE
        assert "limit: knobs.hook_limit" in TS_PLUGIN_SOURCE
        assert "recall_threshold: HOOK_THRESHOLD" in TS_PLUGIN_SOURCE
        assert "hook_budget: HOOK_BUDGET" in TS_PLUGIN_SOURCE
        assert "hook_limit: HOOK_LIMIT" in TS_PLUGIN_SOURCE
        assert "hook_timeout_ms: HOOK_TIMEOUT_MS" in TS_PLUGIN_SOURCE

    def test_recall_is_timeboxed_through_bridge(self) -> None:
        assert "timeoutMs = 30000" in TS_PLUGIN_SOURCE  # default unchanged
        assert "HOOK_TIMEOUT_MS" in TS_PLUGIN_SOURCE
        block = _hook_block("tool.execute.before")
        assert "recallForExecution" in block

    def test_fast_skip_when_no_memory(self) -> None:
        assert "hasMemoryRoot" in TS_PLUGIN_SOURCE
        for legacy in ('".school"', '".lerev"', '".evo"'):
            assert legacy in TS_PLUGIN_SOURCE, legacy

    def test_kill_switch_env_var(self) -> None:
        assert 'process.env.SCHOOL_HOOKS !== "0"' in TS_PLUGIN_SOURCE

    def test_no_npm_dependency_added(self) -> None:
        """Hooks use only existing imports — no new runtime dependencies."""
        imports = re.findall(r'^import .*from "([^"]+)"', TS_PLUGIN_SOURCE, re.MULTILINE)
        allowed = {
            "@opencode-ai/plugin/tool",
            "@opencode-ai/plugin",
            "node:child_process",
            "node:util",
            "node:path",
            "node:fs",
        }
        assert set(imports) <= allowed, f"unexpected imports: {set(imports) - allowed}"


class TestExecutionQuery:
    """The recall query mirrors what the agent/model is doing."""

    def test_salient_argument_keys_covered(self) -> None:
        assert "buildExecutionQuery" in TS_PLUGIN_SOURCE
        for key in ("pattern", "query", "path", "filePath", "command", "content"):
            assert f'"{key}"' in TS_PLUGIN_SOURCE, key

    def test_query_bounded(self) -> None:
        assert ".slice(0, 500)" in TS_PLUGIN_SOURCE


class TestRecallForExecution:
    """Shared recall helper talks to the existing bridge — no new logic."""

    def test_defined_once_and_called_from_both_prompt_and_tool_paths(self) -> None:
        defs = len(re.findall(r"const recallForExecution = async", TS_PLUGIN_SOURCE))
        calls = len(re.findall(r"= await recallForExecution\(", TS_PLUGIN_SOURCE))
        assert defs == 1, f"expected one definition, got {defs}"
        assert calls == 2, f"expected before-hook + chat.message calls, got {calls}"

    def test_dispatches_bridge_recall_command(self) -> None:
        match = re.search(
            r"const recallForExecution = async[\s\S]*?command: \"recall\"[\s\S]*?\n  \}",
            TS_PLUGIN_SOURCE,
        )
        assert match is not None, "recallForExecution must send command: recall"

    def test_passes_scope_identity(self) -> None:
        match = re.search(
            r"const recallForExecution = async[\s\S]*?\n  \}",
            TS_PLUGIN_SOURCE,
        )
        assert match is not None
        body = match.group(0)
        assert 'agent: "opencode"' in body
        assert "project" in body
        assert "session" in body

    def test_degrades_to_null_not_error(self) -> None:
        match = re.search(
            r"const recallForExecution = async[\s\S]*?\n  \}",
            TS_PLUGIN_SOURCE,
        )
        assert match is not None
        body = match.group(0)
        assert "return null" in body
        assert "throw" not in body


def _fn_block(name: str) -> str:
    m = re.search(
        rf"(?:async )?function {name}\([\s\S]*?\n\}}",
        TS_PLUGIN_SOURCE,
    )
    assert m, f"function {name} not found in plugin source"
    return m.group(0)


class TestContextOptimizer:
    def test_constants(self):
        assert "const CTX_THRESHOLD = 1000" in TS_PLUGIN_SOURCE
        assert "const CTX_TIMEOUT_MS = 2000" in TS_PLUGIN_SOURCE

    def test_kill_switch(self):
        assert 'process.env.SCHOOL_CTX !== "0"' in TS_PLUGIN_SOURCE

    def test_footer_regex_literal(self):
        assert r"\[school ctx: \d+→\d+ tokens\]" in TS_PLUGIN_SOURCE

    def test_ctx_optimize_uses_bridge_with_timeout(self):
        block = _fn_block("ctxOptimize")
        assert 'command: "skeleton"' in block
        assert "CTX_TIMEOUT_MS" in block
        assert "ctxEnabled" in block
        assert "catch" in block

    def test_after_hook_wires_optimization(self):
        block = _hook_block("tool.execute.after")
        assert "ctxOptimize(" in block
        assert 'startsWith("Error")' in block
        assert "CTX_THRESHOLD" in block
        assert block.index("ctxOptimize(") < block.index(
            "rec && rec.hits > 0"
        ), "compression must run before the recall block append"

    def test_helper_functions_present(self):
        for name in ("ctxEnabled", "ctxEstimate", "ctxHeuristic", "ctxPayload"):
            _fn_block(name)


class TestApplyView:
    """apply-view: request-time compressed view via context_view segments."""

    def _block(self, name: str) -> str:
        match = re.search(
            rf"const {name} = async \([\s\S]*?\n  \}}", TS_PLUGIN_SOURCE
        )
        assert match is not None, f"const {name} not found"
        return match.group(0)

    def test_transform_calls_apply_view_first(self) -> None:
        block = _hook_block("experimental.chat.messages.transform")
        assert "await applyView(output)" in block
        assert block.index("await applyView(output)") < block.index(
            'info.role !== "user"'
        )

    def test_apply_view_defined_in_school_scope(self) -> None:
        source = TS_PLUGIN_SOURCE
        assert "const applyView = async" in source
        assert source.index("const recallForExecution = async") < source.index(
            "const applyView = async"
        )

    def test_apply_view_gates_kill_switches(self) -> None:
        block = self._block("applyView")
        assert "hooksEnabled()" in block
        assert "ctxEnabled()" in block
        assert 'process.env.SCHOOL_COMPRESS === "0"' in block

    def test_apply_view_is_timeboxed(self) -> None:
        assert "const VIEW_TIMEOUT_MS = 4000" in TS_PLUGIN_SOURCE
        block = self._block("applyView")
        assert "VIEW_TIMEOUT_MS" in block

    def test_apply_view_sends_context_view_command(self) -> None:
        block = self._block("applyView")
        assert 'command: "context_view"' in block
        assert "messages: plain" in block
        assert 'session: String(messages[0]?.info?.sessionID ?? "")' in block

    def test_apply_view_fails_open(self) -> None:
        block = self._block("applyView")
        assert "try {" in block
        assert "catch" in block
        assert "if (!resp.ok) return" in block
        assert "if (!bridge" in block

    def test_apply_view_rebuilds_from_originals(self) -> None:
        block = self._block("applyView")
        assert "if (edit && edit.content == null) continue" in block
        assert "rebuilt.push(src)" in block
        assert "synthetic: true" in block
        assert "output.messages = rebuilt" in block

    def test_apply_view_stores_footer_chip(self) -> None:
        block = self._block("applyView")
        assert "schoolStatus.chip = String(" in block

    def test_view_text_of_prefers_text_parts(self) -> None:
        match = re.search(
            r"function viewTextOf\([\s\S]*?\n\}", TS_PLUGIN_SOURCE
        )
        assert match is not None
        assert 'p.type === "text"' in match.group(0)
        assert "info?.content" in match.group(0)

    def test_mode_gate_skips_when_not_school(self) -> None:
        block = self._block("applyView")
        assert 'if (mode !== "school") return' in block


class TestDcpCoexist:
    """DCP coexistence in the plugin: detect, one quiet offer, ownership gate."""

    def _block(self, name: str) -> str:
        match = re.search(
            rf"const {name} = async \([\s\S]*?\n  \}}", TS_PLUGIN_SOURCE
        )
        assert match is not None, f"const {name} not found"
        return match.group(0)

    def test_dcp_token_constant(self) -> None:
        assert 'const DCP_TOKEN = "@tarquinen/opencode-dcp"' in TS_PLUGIN_SOURCE

    def test_check_coexist_talks_to_bridge(self) -> None:
        block = self._block("checkCoexist")
        assert 'command: "context_coexist"' in block
        assert 'action: "get"' in block
        assert 'action: "set_offer"' in block

    def test_check_coexist_gates_kill_switches(self) -> None:
        block = self._block("checkCoexist")
        assert "hooksEnabled()" in block
        assert "ctxEnabled()" in block
        assert 'process.env.SCHOOL_COMPRESS === "0"' in block

    def test_check_coexist_runs_once_and_fails_open(self) -> None:
        block = self._block("checkCoexist")
        assert "coexistDone = true" in block
        assert "try {" in block
        assert "catch" in block

    def test_dcp_hint_probed_from_client_config(self) -> None:
        block = self._block("checkCoexist")
        assert "client?.config?.get?.()" in block
        assert "dcpHinted = plugins.some(" in block
        assert "DCP_TOKEN" in block

    def test_offer_is_one_quiet_toast(self) -> None:
        block = self._block("checkCoexist")
        assert "showToast" in block
        assert "offer_shown" in block

    def test_apply_view_runs_gate_before_view_request(self) -> None:
        block = self._block("applyView")
        assert "await checkCoexist()" in block
        assert block.index("await checkCoexist()") < block.index(
            'command: "context_view"'
        )

    def test_apply_view_forwards_dcp_hint(self) -> None:
        block = self._block("applyView")
        assert "dcp: dcpHinted" in block


class TestCompactingNudge:
    """experimental.session.compacting: quiet budget-pressure nudge (S2)."""

    def _block(self) -> str:
        return _hook_block("experimental.session.compacting")

    def test_gates_kill_switches(self) -> None:
        block = self._block()
        assert "hooksEnabled()" in block
        assert "ctxEnabled()" in block
        assert 'process.env.SCHOOL_COMPRESS === "0"' in block

    def test_nudges_only_above_threshold(self) -> None:
        block = self._block()
        assert "Array.isArray" in block
        assert "ctxEstimate(" in block
        assert "CTX_THRESHOLD" in block
        assert "context.push(" in block

    def test_nudge_is_school_voice(self) -> None:
        block = self._block()
        assert "[school] compaction ·" in block
        assert "school_context_compress" in block

    def test_fails_open(self) -> None:
        block = self._block()
        assert "try {" in block
        assert "catch" in block
