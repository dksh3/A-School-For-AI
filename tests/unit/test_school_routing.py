"""TS-source contract tests for the adaptive routing loop (Phase 1)."""

import re

from school.plugin_source import TS_PLUGIN_SOURCE


class TestRoutingCoreHelpers:
    def test_constants_present(self):
        assert "const ROUTE_TIMEOUT_MS = 10000" in TS_PLUGIN_SOURCE
        assert "const ROUTE_STATS_MAX_LINES = 2000" in TS_PLUGIN_SOURCE

    def test_engage_mapping(self):
        match = re.search(
            r"function engageFor\(severity: string\): string \{\n(.*?)\n\}",
            TS_PLUGIN_SOURCE,
            re.S,
        )
        assert match, "engageFor missing"
        body = match.group(1)
        assert '"light" ? "skill" : "both"' in body.replace(" ", " ").replace(
            "  ", ""
        ) or ('"light"' in body and '"skill"' in body and '"both"' in body)

    def test_evidence_append_and_cap(self):
        assert "function appendEvidence(" in TS_PLUGIN_SOURCE
        assert "routing-stats.jsonl" in TS_PLUGIN_SOURCE
        assert "ROUTE_STATS_MAX_LINES" in TS_PLUGIN_SOURCE
        assert "appendFileSync" in TS_PLUGIN_SOURCE
        assert "mkdirSync" in TS_PLUGIN_SOURCE

    def test_knobs_reader(self):
        assert "function readKnobs(" in TS_PLUGIN_SOURCE
        assert "routing.json" in TS_PLUGIN_SOURCE
        assert "skip_tools" in TS_PLUGIN_SOURCE
        assert "force_tools" in TS_PLUGIN_SOURCE
        assert "statSync" in TS_PLUGIN_SOURCE  # mtime cache check

    def test_clamp_num_defaults_on_null_and_boolean(self):
        # Null/boolean knob values are invalid -> per-key default, never coerced
        # (Number(null) === 0 would silently override the default).
        match = re.search(
            r"function clampNum\([^)]*\): number \{\n(.*?)\n\}",
            TS_PLUGIN_SOURCE,
            re.S,
        )
        assert match, "clampNum missing"
        body = match.group(1)
        assert "v == null" in body
        assert 'typeof v === "boolean"' in body
        # Guard must run before Number(v), which would coerce null to 0.
        assert body.index("v == null") < body.index("Number(v)")
        # recall_threshold: null -> 0.2, hook_timeout_ms: null -> 1500.
        assert "recall_threshold: HOOK_THRESHOLD" in TS_PLUGIN_SOURCE
        assert "hook_timeout_ms: HOOK_TIMEOUT_MS" in TS_PLUGIN_SOURCE
        assert "HOOK_THRESHOLD = 0.2" in TS_PLUGIN_SOURCE
        assert "HOOK_TIMEOUT_MS = 1500" in TS_PLUGIN_SOURCE

    def test_knobs_used_in_recall_path(self):
        # recallForExecution reads knobs and applies them to the bridge call.
        idx = TS_PLUGIN_SOURCE.index("const recallForExecution")
        end = TS_PLUGIN_SOURCE.index("return {", idx)
        block = TS_PLUGIN_SOURCE[idx:end]
        assert "readKnobs" in block
        assert "confidence_threshold" in block
        assert "knobs.recall_threshold" in block

    def test_before_hook_skip_force(self):
        idx = TS_PLUGIN_SOURCE.index('"tool.execute.before"')
        block = TS_PLUGIN_SOURCE[idx : TS_PLUGIN_SOURCE.index('"tool.execute.after"')]
        assert "skip_tools" in block
        assert "force_tools" in block

    def test_after_hook_tracks_evidence_and_start_time(self):
        idx = TS_PLUGIN_SOURCE.index('"tool.execute.after"')
        end = TS_PLUGIN_SOURCE.index('"chat.message"', idx)
        block = TS_PLUGIN_SOURCE[idx:end]
        assert 'kind: "exec"' in block
        assert "executionStart" in block
        assert "Date.now()" in block

    def test_routing_marker_suffix(self):
        # After-hook appends the routing marker from metadata.engagement.
        idx = TS_PLUGIN_SOURCE.index('"tool.execute.after"')
        end = TS_PLUGIN_SOURCE.index('"chat.message"', idx)
        block = TS_PLUGIN_SOURCE[idx:end]
        assert "routing: " in block
        assert "metadata" in block

    def test_node_fs_imports_extended(self):
        match = re.search(r'import \{ ([^}]+) \} from "node:fs"', TS_PLUGIN_SOURCE)
        assert match, "node:fs import missing"
        names = {n.strip() for n in match.group(1).split(",")}
        assert {"existsSync", "appendFileSync", "readFileSync", "writeFileSync",
                "mkdirSync", "statSync"} <= names


class TestRouteTools:
    def test_tools_registered(self):
        names = re.findall(r"^\s+(school_\w+): tool\(", TS_PLUGIN_SOURCE, re.MULTILINE)
        assert "school_route" in names
        assert "school_route_stats" in names

    def test_descriptions_are_routing_guided(self):
        for name in ("school_route", "school_route_stats"):
            match = re.search(
                rf"{name}: tool\(.*?description:\s*\n(.*?),\n\s*args:",
                TS_PLUGIN_SOURCE,
                re.S,
            )
            assert match, name
            text = " ".join(re.findall(r'"([^"]*)"', match.group(1)))
            assert "Use" in text
            assert "coding" in text  # domain-general framing present

    def test_micro_assess_contract(self):
        assert "function microAssess(" in TS_PLUGIN_SOURCE
        assert "session.create" in TS_PLUGIN_SOURCE
        assert "session.prompt" in TS_PLUGIN_SOURCE
        assert "session.delete" in TS_PLUGIN_SOURCE
        assert "small_model" in TS_PLUGIN_SOURCE  # config.get → small model
        assert "Promise.race" in TS_PLUGIN_SOURCE
        assert "ROUTE_TIMEOUT_MS" in TS_PLUGIN_SOURCE

    def test_prompt_is_json_only(self):
        assert "Respond ONLY with JSON" in TS_PLUGIN_SOURCE
        assert (
            "never choose engage none" in TS_PLUGIN_SOURCE.lower()
            or "Never choose engage none" in TS_PLUGIN_SOURCE
        )

    def test_route_prompt_truncates_situation_within_budget(self):
        # Micro-call contract: prompt <= 150 tokens. routePrompt must slice
        # the situation itself — the tool's 500-char cap alone still busts
        # the token budget once the fixed template is added.
        match = re.search(
            r"function routePrompt\(situation: string\): string \{\n(.*?)\n  \}",
            TS_PLUGIN_SOURCE,
            re.S,
        )
        assert match, "routePrompt missing"
        body = match.group(1)
        assert " + situation.slice(0, 200)" in body
        assert not re.search(r"\+ situation(?!\.slice)", body)
        # Worst-case bound: fixed template literals + 200-char situation.
        literals = re.findall(r"'([^']*)'|\"([^\"]*)\"", body)
        template = sum(len(a or b) for a, b in literals)
        assert template + 200 <= 700

    def test_parse_route_decision(self):
        assert "function parseRouteDecision(" in TS_PLUGIN_SOURCE
        assert 'raw.engage === "none"' in TS_PLUGIN_SOURCE

    def test_route_picks_tools_and_skills(self):
        # The micro-model decides which tools and skills fit the situation.
        body_match = re.search(
            r"function routePrompt\(situation: string\): string \{\n(.*?)\n  \}",
            TS_PLUGIN_SOURCE,
            re.S,
        )
        assert body_match, "routePrompt missing"
        body = body_match.group(1)
        assert "up to 3 tools" in body
        assert "up to 2 skills" in body
        assert '"tools":["..."]' in body
        assert '"skills":["..."]' in body
        assert "slice(0, 3)" in TS_PLUGIN_SOURCE  # tools cap
        assert "slice(0, 2)" in TS_PLUGIN_SOURCE  # skills cap
        assert "defaultPicks" in TS_PLUGIN_SOURCE  # fallback engagement picks
        assert "schoolStatus.next" in TS_PLUGIN_SOURCE  # picks surface in footer

    def test_kill_switch(self):
        assert 'process.env.SCHOOL_ROUTE === "0"' in TS_PLUGIN_SOURCE

    def test_report_stores_tagged_lesson(self):
        idx = TS_PLUGIN_SOURCE.index("school_route: tool(")
        block = TS_PLUGIN_SOURCE[idx : TS_PLUGIN_SOURCE.index("school_route_stats: tool(")]
        assert '"routing"' in block
        assert '"helpful"' in block and '"useless"' in block and '"neutral"' in block
        assert '"SUCCESS"' in block and '"FAILURE"' in block and '"NEUTRAL"' in block
        assert 'command: "remember"' in block
        # The bridge persists only observation/action/outcome into memory
        # content (observation falls back to content). A situation-bearing
        # observation alone drops the lesson text, so the lesson must also
        # ride in `action` — same field the MCP report uses.
        assert "observation: situation" in block
        assert "action: lesson" in block

    def test_assess_appends_evidence_and_metadata(self):
        idx = TS_PLUGIN_SOURCE.index("school_route: tool(")
        block = TS_PLUGIN_SOURCE[idx : TS_PLUGIN_SOURCE.index("school_route_stats: tool(")]
        assert 'kind: "assess"' in block
        assert "engagement:" in block

    def test_stats_aggregates(self):
        idx = TS_PLUGIN_SOURCE.index("school_route_stats: tool(")
        block = TS_PLUGIN_SOURCE[idx : TS_PLUGIN_SOURCE.index('"tool.execute.before"')]
        assert "aggregates" in block
        assert "avg_ms" in block
        assert "last_activity" in block
        assert 'kind: "report"' in TS_PLUGIN_SOURCE
        assert "routing lesson" in TS_PLUGIN_SOURCE  # recall query for lessons
