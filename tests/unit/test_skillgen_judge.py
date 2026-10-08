"""1A-2Z: strict structured model-judgment parsing (fail-closed).

Model output is untrusted: anything invalid must parse to
worth_creating=False with safety_ok=False so no skill can be created
from malformed/hostile output.
"""

from __future__ import annotations

import json

from core.routing.v26.experience import Experience, ExperienceOutcome
from core.routing.v26.identity import AgentIdentity
from core.skillgen.candidate import detect
from core.skillgen.judge import build_judgment_prompt, parse_judgment

VALID = {
    "worth_creating": True,
    "confidence": 0.9,
    "skill_type": "diagnostic",
    "reason": "Reusable diagnosis for build failures",
    "generalizable": True,
    "safety_ok": True,
    "proposed_scope": "global",
    "proposed_name": "diagnose-build-failures",
    "procedure_steps": ["Reproduce", "Inspect config", "Fix root cause"],
    "triggers": ["build failure", "module error"],
}


def _candidate():
    exp = Experience.create(
        agent=AgentIdentity(agent_id="a1"),
        observation=(
            "The build failed every time with module resolution errors "
            "after a config change"
        ),
        action="Diagnosed the root cause and fixed the configuration",
        outcome=ExperienceOutcome.SUCCESS,
        feedback="works, exactly what I needed, great",
    )
    return detect(exp)


class TestValidParsing:
    def test_valid_json(self) -> None:
        j = parse_judgment(json.dumps(VALID), model_id="m1")
        assert j.worth_creating is True
        assert j.confidence == 0.9
        assert j.skill_type == "diagnostic"
        assert j.generalizable is True
        assert j.safety_ok is True
        assert j.proposed_scope == "global"
        assert j.proposed_name == "diagnose-build-failures"
        assert j.procedure_steps == ["Reproduce", "Inspect config", "Fix root cause"]
        assert j.triggers == ["build failure", "module error"]
        assert j.model == "m1"

    def test_fenced_json_block(self) -> None:
        raw = f"```json\n{json.dumps(VALID)}\n```"
        j = parse_judgment(raw, model_id="m2")
        assert j.worth_creating is True
        assert j.skill_type == "diagnostic"

    def test_json_surrounded_by_prose(self) -> None:
        raw = f"Here you go: {json.dumps(VALID)} done."
        j = parse_judgment(raw)
        assert j.worth_creating is True
        assert j.proposed_name == "diagnose-build-failures"

    def test_to_dict_is_json_safe(self) -> None:
        j = parse_judgment(json.dumps(VALID))
        assert json.loads(json.dumps(j.to_dict()))["worth_creating"] is True


class TestFailClosed:
    def test_garbage(self) -> None:
        j = parse_judgment("this is not json at all", model_id="m3")
        assert j.worth_creating is False
        assert j.safety_ok is False
        assert j.confidence == 0.0
        assert j.reason == "unparseable_model_output"
        assert j.model == "m3"

    def test_empty_string(self) -> None:
        j = parse_judgment("")
        assert j.worth_creating is False
        assert j.safety_ok is False

    def test_json_array_is_not_a_verdict(self) -> None:
        j = parse_judgment("[1, 2, 3]")
        assert j.worth_creating is False

    def test_non_bool_worth_creating(self) -> None:
        raw = dict(VALID, worth_creating="yes")
        j = parse_judgment(json.dumps(raw))
        assert j.worth_creating is False
        assert j.safety_ok is False

    def test_truncated_json(self) -> None:
        j = parse_judgment('{"worth_creating": tru')
        assert j.worth_creating is False

    def test_safety_ok_defaults_false_when_missing(self) -> None:
        raw = dict(VALID)
        del raw["safety_ok"]
        j = parse_judgment(json.dumps(raw))
        assert j.worth_creating is True
        assert j.safety_ok is False  # explicit opt-in required


class TestClampingAndNormalization:
    def test_confidence_clamped_to_unit_interval(self) -> None:
        assert parse_judgment(json.dumps(dict(VALID, confidence=5.0))).confidence == 1.0
        assert parse_judgment(json.dumps(dict(VALID, confidence=-3))).confidence == 0.0
        assert parse_judgment(json.dumps(dict(VALID, confidence="abc"))).confidence == 0.0

    def test_invalid_skill_type_blanked(self) -> None:
        j = parse_judgment(json.dumps(dict(VALID, skill_type="banana")))
        assert j.skill_type == ""

    def test_invalid_scope_falls_back_to_session(self) -> None:
        j = parse_judgment(json.dumps(dict(VALID, proposed_scope="galaxy")))
        assert j.proposed_scope == "session"

    def test_missing_scope_defaults_session(self) -> None:
        raw = dict(VALID)
        del raw["proposed_scope"]
        j = parse_judgment(json.dumps(raw))
        assert j.proposed_scope == "session"

    def test_steps_capped_at_six(self) -> None:
        raw = dict(VALID, procedure_steps=[f"step {i}" for i in range(10)])
        j = parse_judgment(json.dumps(raw))
        assert len(j.procedure_steps) == 6

    def test_triggers_capped_at_four(self) -> None:
        raw = dict(VALID, triggers=[f"trigger {i}" for i in range(7)])
        j = parse_judgment(json.dumps(raw))
        assert len(j.triggers) == 4

    def test_non_list_steps_ignored(self) -> None:
        j = parse_judgment(json.dumps(dict(VALID, procedure_steps="do it")))
        assert j.procedure_steps == []


class TestPrompt:
    def test_prompt_contains_evidence_and_schema(self) -> None:
        candidate = _candidate()
        assert candidate is not None
        prompt = build_judgment_prompt(candidate)
        assert "EVIDENCE (JSON)" in prompt
        assert "worth_creating" in prompt
        assert "unsafe" in prompt
