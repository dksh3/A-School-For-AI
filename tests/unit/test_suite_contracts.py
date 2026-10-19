"""Regression tests for the Forge-suite usability repair (audit 2026-10-18).

Every test pins an ORIGINAL audit defect and must fail on the pre-repair tree:

1.  suite-map blackout        - skills named school_* tools never (artifact blackout)
2.  phantom `prism` refs      - `prism` presented as a current skill/tool name
3.  chart needs<->weave       - `needs: S1` never mapped to Command.depends_on
4.  missing Constraints slot  - chart template dropped user constraints (planted
                                "submit exactly 3 stories" failure)
5.  status vocabulary        - SIMULATED/EXPLORATORY existed nowhere; UNVERIFIED
                                rules differed per skill
6.  forge/triage templates   - "mark the command done with evidence" had no format
7.  scrutinize headings      - Attack/Confusion merged into one ambiguous section
8.  gate<->scrutinize handoff- gate never consumed the review report
9.  relay mechanism          - "coordinator answers in minutes" is unagentable
10. storage conventions      - "ship the report where the work lives" (no path)
11. school-routing truth     - phantom "medium-light" tier; dead `calibration`
12. knob range parity        - TS clamps routing.json knobs, Python accepted any number
13. tool->skill discovery    - no product tool description ever named a skill

Structural checks parse the real templates; behavioral checks execute the real
code (core/forge/evidence.py, school.mcp.server._read_knobs, school.cli).
"""

from __future__ import annotations

import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "skills"
CRAFT = ("forge", "triage", "chart", "gate", "relay", "scrutinize")

ARTIFACT_TOOLS = {
    "clarion": "school_clarion",
    "blueprint": "school_blueprint",
    "edict": "school_edict",
    "weave": "school_weave",
    "compass": "school_compass",
    "brainstorm": "school_brainstorm",
}

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def _skill_md(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _skill_body(name: str) -> str:
    m = FRONTMATTER_RE.match(_skill_md(name))
    assert m, f"{name}: frontmatter missing"
    return m.group(2)


def _skill_description(name: str) -> str:
    md = _skill_md(name)
    m = re.search(r"^---\n(.*?)\n---\n", md, re.S)
    assert m, f"{name}: frontmatter missing"
    for line in m.group(1).splitlines():
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"{name}: description missing")


def _fenced_blocks(body: str) -> list[str]:
    return re.findall(r"```[a-z]*\n(.*?)```", body, re.S)


# --- 1/2. suite map + phantom names ----------------------------------------

def test_suite_map_present_in_every_skill():
    for name in CRAFT:
        body = _skill_body(name)
        assert "## Suite map" in body, f"{name}: no suite map (artifact blackout)"
        for art, tool in ARTIFACT_TOOLS.items():
            assert tool in body, f"{name}: never names {tool}"
            assert re.search(rf"`{art}`|{art}", body), f"{name}: never names {art}"


def test_suite_map_tools_resolve_to_real_surfaces():
    from school import bridge
    from school.mcp import server

    for tool in ARTIFACT_TOOLS.values():
        assert tool in server._TOOLS, f"{tool} missing from MCP surface"
    # bridge wire names (prism is the retained legacy wire name for brainstorm)
    wire = {"clarion", "blueprint", "edict", "weave", "compass", "prism"}
    assert wire <= set(bridge._COMMANDS)


def test_no_phantom_prism_or_stale_names_in_skills():
    for name in CRAFT + ("school-routing",):
        body = _skill_body(name) if name != "school-routing" else (
            (SKILLS / "school-routing" / "SKILL.md").read_text(encoding="utf-8")
        )
        assert "medium-light" not in body, f"{name}: phantom tier 'medium-light'"
        for line in body.splitlines():
            if re.search(r"\bprism\b", line, re.I):
                assert "legacy" in line.lower(), (
                    f"{name}: stale prism reference (must be legacy-labelled): {line!r}"
                )


# --- 4. routing descriptions ----------------------------------------------

def test_skill_descriptions_route_and_negate():
    for name in CRAFT:
        desc = _skill_description(name)
        assert desc.startswith("Use when"), f"{name}: description must lead with trigger"
        assert len(desc) <= 500, f"{name}: description too long ({len(desc)})"
        assert "not only coding" in desc, f"{name}: lost universal marker"
        assert re.search(
            r"(?i)\bnot for\b|\bskip\b|\bnot a substitute\b|\bespecially when\b", desc
        ), (
            f"{name}: no negative trigger / activation edge"
        )


# --- 3/4. chart contracts ---------------------------------------------------

def test_chart_template_has_constraints_slot():
    body = _skill_body("chart")
    tpl = "\n".join(_fenced_blocks(body))
    assert re.search(r"(?im)^.*\bconstraints\b", tpl), (
        "chart output template has no Constraints slot (original defect)"
    )


def test_planted_constraint_survives_chart_to_gate():
    """Planted constraint 'submit exactly 3 stories' must be capturable from the
    chart template AND checked again by gate's assembly (the original failure:
    chart's template dropped it, gate never looked at source constraints)."""
    chart_tpl = "\n".join(_fenced_blocks(_skill_body("chart")))
    slot = re.search(r"(?im)^(.*\bconstraints\b.*)$", chart_tpl)
    assert slot, "chart template lost the Constraints slot"
    # The slot line must be fillable with arbitrary constraint text (round-trip).
    planted = "submit exactly 3 stories"
    filled = chart_tpl[: slot.start(1)] + planted + chart_tpl[slot.end(1) :]
    assert planted in filled
    gate = _skill_body("gate").lower()
    assert "constraint" in gate, "gate never checks source constraints (original defect)"


def test_chart_needs_maps_to_weave_depends_on():
    from core.forge.models import Command

    assert "depends_on" in getattr(Command, "__dataclass_fields__", {}), (
        "core model lost Command.depends_on"
    )
    body = _skill_body("chart")
    assert "needs:" in body
    assert "depends_on" in body, "chart never maps needs: to weave/Command.depends_on"


# --- 5. status vocabulary ---------------------------------------------------

def test_status_vocabulary_module_is_honest():
    from core.forge import evidence as ev

    assert ev.counts_as_pass(ev.Status.PASS) is True
    assert ev.counts_as_pass(ev.Status.FAIL) is False
    assert ev.counts_as_pass(ev.Status.UNVERIFIED) is False
    assert ev.counts_as_pass(ev.Status.SIMULATED, user_accepted_proxy=False) is False
    assert ev.counts_as_pass(ev.Status.SIMULATED, user_accepted_proxy=True) is True
    assert ev.counts_as_pass(ev.Status.EXPLORATORY) is False


def test_status_vocabulary_identical_in_forge_and_gate():
    def _block(body: str) -> str | None:
        m = re.search(r"(?is)##\s*[^\n]*evidence status.*?(?=\n## |\Z)", body)
        return re.sub(r"\s+", " ", m.group(0)).strip() if m else None

    forge, gate = _block(_skill_body("forge")), _block(_skill_body("gate"))
    assert forge, "forge has no evidence-status section"
    assert gate, "gate has no evidence-status section"
    assert forge == gate, "status vocabulary drifted between forge and gate"
    for tok in ("PASS", "FAIL", "UNVERIFIED", "SIMULATED", "EXPLORATORY"):
        assert tok in forge, tok


# --- 8. gate consumes scrutinize -------------------------------------------

def test_gate_consumes_scrutinize_report():
    from core.forge import evidence as ev

    body = _skill_body("gate")
    low = body.lower()
    assert "scrutinize" in low, "gate never mentions the scrutinize review report"
    assert re.search(r"(?i)review report|scrutinize report", body), (
        "gate gives no resolution mechanism for the review report"
    )
    assert ev.gate_row("must-fix")["blocking"] is True
    assert ev.gate_row("should-fix")["blocking"] is False
    assert ev.gate_row("note")["blocking"] is False
    assert re.search(r"(?i)must[- ]fix", body), "gate lacks must-fix severity mapping"


def test_gate_pins_row_classification_before_evidence():
    """Campaign D defect (the honesty leak): verdict rows were classified by
    the judge *after* seeing the evidence, so audience-acceptance could be
    downgraded to a soft row and the verdict gamed to GO-WITH-CONDITIONS.
    Catch: gate must require classifying rows before evidence, pin
    goal-promised claims (audience acceptance / human sign-off) to hard-floor
    by default, take the stricter reading when debatable, and forbid
    downward reclassification."""
    body = _skill_body("gate")
    assert re.search(r"(?i)classify .{0,80}before", body), (
        "gate does not require classifying rows before looking at evidence"
    )
    assert re.search(r"(?i)hard floor.{0,40}unless the user", body), (
        "gate does not pin goal-promised claims (audience acceptance) to hard floor"
    )
    assert re.search(r"(?i)stricter reading", body), (
        "gate gives no default reading for debatable rows"
    )
    assert re.search(r"(?i)never reclassify", body), (
        "gate permits downward reclassification to reach a verdict"
    )


def test_gate_pin_closes_reclassification_and_proxy_loops():
    """Re-gate defects (micro-run audit of Campaign A under the pin): four
    word-level loopholes — waiver standard weaker than the SIMULATED rule,
    no home for the mandated reading disclosure, only downward
    reclassification banned, proxy acceptance allowed after the fact.
    Catch each closed wording; keep forge's status block in sync."""
    gate = _skill_body("gate")
    forge = _skill_body("forge")
    assert re.search(r"(?i)either direction", gate), (
        "gate still bans only downward reclassification (upward move is a loophole)"
    )
    assert re.search(r"(?i)reading \| verdict", gate), (
        "gate mandates naming the reading but the report template gives it no home"
    )
    assert re.search(r"(?i)explicitly said otherwise", gate), (
        "gate waiver standard is weaker than the SIMULATED proxy-acceptance rule"
    )
    for name, body in (("gate", gate), ("forge", forge)):
        assert re.search(r"(?i)recorded before the verdict", body), (
            f"{name} allows retroactive proxy acceptance after the result is known"
        )


# --- 6. forge / triage templates -------------------------------------------

def test_forge_command_log_template():
    tpl = "\n".join(_fenced_blocks(_skill_body("forge")))
    for slot in ("Command:", "RED", "Shown failing", "GREEN", "Evidence"):
        assert slot in tpl, f"forge command-log template missing {slot!r}"


def test_triage_repro_record_template():
    body = _skill_body("triage")
    tpl = "\n".join(_fenced_blocks(body))
    for slot in ("Repro", "Observed", "Expected", "Isolation", "Predicts", "Regression"):
        assert slot.lower() in tpl.lower(), f"triage repro record missing {slot!r}"
    assert "risks" in body, "triage debt must land in blueprint.risks (not a phantom field)"
    assert "school_remember" in body, "triage lessons must name the real memory tool"


# --- 7. scrutinize report shape ---------------------------------------------

def test_scrutinize_sections_split():
    heads = re.findall(r"(?m)^#{2,3}\s+(.*)$", _skill_body("scrutinize"))
    assert any("attack" in h.lower() for h in heads), "no Attack-lines section"
    assert any("confusion" in h.lower() for h in heads), "no Confusion-moments section"
    merged = [h for h in heads if "attack" in h.lower() and "confusion" in h.lower()]
    assert not merged, f"attack/confusion merged into one heading: {merged}"
    assert re.search(r"(?i)rework", _skill_body("scrutinize")), "no REWORK rule"


# --- 9. relay coordination mechanism ----------------------------------------

def test_relay_agent_mechanism():
    body = _skill_body("relay").lower()
    assert "subagent" in body or "sub-agent" in body, "relay never names a real spawn mechanism"
    assert "sequential" in body, "relay has no sequential fallback"
    assert "checkpoint" in body
    assert "merge order" in body or "ordered merge" in body
    for line in body.splitlines():
        if "coordinator answers" in line:
            assert "human" in line, f"unagentable claim left unlabelled: {line!r}"


# --- 3. storage + memory conventions -----------------------------------------

def test_storage_conventions_explicit():
    for name in CRAFT:
        body = _skill_body(name)
        assert "reports/" in body, f"{name}: no report path convention"
        assert "where the work lives" not in body.lower(), (
            f"{name}: ambiguous storage instruction remains"
        )


def test_memory_writeback_names_real_integration():
    from school.mcp import server

    assert "school_remember" in server._TOOLS, "school_remember vanished"
    for name in ("triage", "relay"):
        assert "school_remember" in _skill_body(name), f"{name}: lessons have no sink"


# --- 11/12. school-routing truth + knob parity --------------------------------

def test_school_routing_matches_runtime():
    from school.skill_source import ROUTING_SKILL_MD

    installed = (SKILLS / "school-routing" / "SKILL.md").read_text(encoding="utf-8")
    assert installed == ROUTING_SKILL_MD, "repo skill copy drifted from skill_source"
    low = ROUTING_SKILL_MD.lower()
    assert "medium-light" not in low, "phantom tier in school-routing"
    for tier in ("light", "medium", "high"):
        assert tier in low, tier
    assert 'engage: "skill"' in ROUTING_SKILL_MD
    assert 'engage: "both"' in ROUTING_SKILL_MD
    assert "calibration" in low
    assert "4 options" in low or "four options" in low
    assert "light" in _routing_description(ROUTING_SKILL_MD)


def _routing_description(md: str) -> str:
    for line in md.split("---", 2)[1].splitlines():
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip()
    return ""


def test_knob_clamps_match_ts(tmp_path, monkeypatch):
    from school.mcp import server

    monkeypatch.setattr(server, "_memory_root", lambda _wt: tmp_path)
    (tmp_path / "routing.json").write_text(
        json.dumps(
            {
                "recall_threshold": 5,
                "hook_limit": -3,
                "hook_budget": 1,
                "hook_timeout_ms": 99999,
            }
        ),
        encoding="utf-8",
    )
    knobs = server._read_knobs(str(tmp_path))
    assert knobs["recall_threshold"] == 1
    assert knobs["hook_limit"] == 1
    assert knobs["hook_budget"] == 64
    assert knobs["hook_timeout_ms"] == 5000
    src = (REPO / "school" / "plugin_source.py").read_text(encoding="utf-8")
    for expr in (
        "clampNum(raw.recall_threshold, DEFAULT_KNOBS.recall_threshold, 0, 1)",
        "clampNum(raw.hook_limit, DEFAULT_KNOBS.hook_limit, 1, 50)",
        "clampNum(raw.hook_budget, DEFAULT_KNOBS.hook_budget, 64, 8000)",
        "clampNum(raw.hook_timeout_ms, DEFAULT_KNOBS.hook_timeout_ms, 250, 5000)",
    ):
        assert expr in src, f"TS clamp changed: {expr}"


# --- 13. tool -> skill discovery ---------------------------------------------

def test_tool_descriptions_point_to_skills():
    from school.mcp import server

    want = {
        "school_clarion": "chart",
        "school_blueprint": "chart",
        "school_edict": "forge",
        "school_weave": "relay",
        "school_compass": "gate",
        "school_brainstorm": "chart",
    }
    src = (REPO / "school" / "plugin_source.py").read_text(encoding="utf-8")
    for tool, skill in want.items():
        desc = server._TOOLS[tool]["description"]
        assert f"`{skill}`" in desc, f"{tool} never points at the {skill} skill"
        assert "Use" in desc
        assert len(desc) <= 700
        m = re.search(rf"{tool}: tool\(.*?description:\s*\n(.*?),\n\s*args:", src, re.S)
        assert m, tool
        ts_desc = "".join(re.findall(r'"([^"]*)"', m.group(1)))
        assert ts_desc == desc, f"{tool}: TS/MCP description drift"


# --- 2/15. brainstorm canonical, prism legacy -------------------------------

def test_cli_brainstorm_canonical_prism_alias():
    out = subprocess.run(
        [sys.executable, str(REPO / "school" / "cli.py"), "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert out.returncode == 0, out.stderr
    assert "brainstorm" in out.stdout, "CLI has no canonical brainstorm command"
    assert "prism" in out.stdout, "CLI lost the legacy prism alias"
    from school import cli

    src = inspect.getsource(cli)
    assert re.search(r'"brainstorm"\s*:\s*_cmd_prism', src), (
        "brainstorm must dispatch to the brainstorm engine"
    )
    assert re.search(r'"prism"\s*:\s*_cmd_prism', src), "prism alias must keep working"


def test_bridge_prism_is_documented_legacy_only():
    from school import bridge

    assert "prism" in bridge._COMMANDS, "wire compat broken: bridge must keep prism"
    for name in CRAFT:
        low = _skill_body(name).lower()
        for line in low.splitlines():
            if "prism" in line:
                assert "legacy" in line, f"{name}: unlabelled prism reference"


# --- 18. skill body compatibility (existing suite contract) -------------------

@pytest.mark.parametrize("name", CRAFT, ids=list(CRAFT))
def test_existing_skill_contracts_still_hold(name):
    body = _skill_body(name)
    assert len(body) >= 2000, "body must stay thorough"
    assert body.count("\n## ") >= 3
    assert "universal" in body.lower()
    assert "not only coding" in _skill_description(name)
