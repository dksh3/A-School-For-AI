"""Small-model judgment for 1A-2Z (Phase 1).

The model provides structured judgment only - it never writes files or
executes code. Output must be strict JSON parsed by parse_judgment; invalid
output is treated as "do not create" (fail closed). Judge is pluggable:
tests inject a mock, real runs may set SCHOOL_SKILLGEN_JUDGE_CMD to a
command that reads the prompt on stdin and prints JSON on stdout.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.skillgen.candidate import Candidate
from core.skillgen.types import safe_float, safe_list_str, safe_str


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


JUDGE_TIMEOUT_S = _env_float("SCHOOL_SKILLGEN_JUDGE_TIMEOUT", 60.0)

SKILL_TYPES = frozenset({"workflow", "procedure", "tool_strategy", "shortcut", "diagnostic"})
SCOPES = frozenset({"session", "project", "agent", "global"})


@dataclass(slots=True)
class Judgment:
    """Structured model verdict on a candidate."""

    worth_creating: bool
    confidence: float
    skill_type: str
    reason: str
    generalizable: bool
    safety_ok: bool = True
    proposed_scope: str = "session"
    proposed_name: str = ""
    procedure_steps: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    model: str = "unknown"
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        try:
            worth = bool(self.worth_creating)
        except Exception:  # noqa: BLE001 - hostile value
            worth = False
        try:
            generalizable = bool(self.generalizable)
        except Exception:  # noqa: BLE001 - hostile value
            generalizable = False
        try:
            safety_ok = bool(self.safety_ok)
        except Exception:  # noqa: BLE001 - hostile value
            safety_ok = False
        return {
            "worth_creating": worth,
            "confidence": max(0.0, min(1.0, safe_float(self.confidence, 0.0))),
            "skill_type": safe_str(self.skill_type, 32),
            "reason": safe_str(self.reason, 400),
            "generalizable": generalizable,
            "safety_ok": safety_ok,
            "proposed_scope": safe_str(self.proposed_scope, 32),
            "proposed_name": safe_str(self.proposed_name, 64),
            "model": safe_str(self.model, 100),
        }


class ModelJudge(Protocol):
    """Anything that turns a prompt into raw model text."""

    def __call__(self, prompt: str) -> tuple[str, str]:
        """Return (raw_text, model_id)."""
        ...


def build_judgment_prompt(candidate: Candidate) -> str:
    """Compose the single judgment question for the small model. Never raises."""
    try:
        exp = candidate.experience
        evidence = {
            "observation": safe_str(exp.observation, 2000),
            "action": safe_str(exp.action, 2000),
            "outcome": safe_str(getattr(exp.outcome, "name", ""), 32),
            "feedback": safe_str(exp.feedback, 500),
            "signals": {k: v for k, v in candidate.signals.items() if v},
            "factors": candidate.factors,
            "score": candidate.score,
        }
        return (
            "You are a strict skill-curation judge for an agent memory system.\n"
            "Decide whether this experience contains a genuinely reusable capability\n"
            "worth turning into a skill. Reject one-off actions, trivial steps, and\n"
            "anything unsafe (credential theft, exfiltration, disabling security,\n"
            "executing untrusted code, ignoring safety instructions).\n\n"
            f"EVIDENCE (JSON):\n{json.dumps(evidence, ensure_ascii=False, default=str)}\n\n"
            "Existing skills for duplicate check (name: description):\n"
            f"{candidate.merge_hint or '(none similar)'}\n\n"
            "Respond with ONLY a JSON object, no prose, exactly these keys:\n"
            '{"worth_creating": true, "confidence": 0.0-1.0, "skill_type": '
            '"workflow|procedure|tool_strategy|shortcut|diagnostic", "reason": '
            '"<=200 chars", "generalizable": true, "safety_ok": true, '
            '"proposed_scope": "session|project|agent|global", "proposed_name": '
            '"kebab-case-name", "procedure_steps": ["<=6 short steps"], '
            '"triggers": ["<=4 when-to-use phrases"]}'
        )
    except Exception:  # noqa: BLE001 - hostile candidate: minimal prompt
        return "Judge this experience. Respond with ONLY a JSON object."


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def parse_judgment(raw: Any, model_id: Any = "unknown") -> Judgment:
    """Strictly parse model JSON. Invalid output => worth_creating=False.

    Never raises: any hostile/unparseable input yields the fail-closed verdict.
    """
    text_raw = safe_str(raw, 20_000)
    model = safe_str(model_id, 100)
    fail = Judgment(
        worth_creating=False,
        confidence=0.0,
        skill_type="",
        reason="unparseable_model_output",
        generalizable=False,
        safety_ok=False,
        model=model,
        raw=text_raw[:2000],
    )
    try:
        text = text_raw.strip()
        if not text:
            return fail
        # Tolerate surrounding prose fences, but the payload must be an object.
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{") and part.endswith("}"):
                    text = part
                    break
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return fail
        try:
            data = json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return fail
        if not isinstance(data, dict):
            return fail
        worth = data.get("worth_creating")
        if not isinstance(worth, bool):
            return fail
        confidence = _f(data.get("confidence"), 0.0)
        skill_type = safe_str(data.get("skill_type", ""), 32)
        if skill_type and skill_type not in SKILL_TYPES:
            skill_type = ""
        scope = safe_str(data.get("proposed_scope", "session"), 32)
        if scope not in SCOPES:
            scope = "session"
        steps = data.get("procedure_steps")
        triggers = data.get("triggers")
        return Judgment(
            worth_creating=worth,
            confidence=confidence,
            skill_type=skill_type,
            reason=safe_str(data.get("reason", ""), 400),
            generalizable=bool(data.get("generalizable", False)),
            safety_ok=bool(data.get("safety_ok", False)),
            proposed_scope=scope,
            proposed_name=safe_str(data.get("proposed_name", ""), 64),
            procedure_steps=safe_list_str(steps, 6, 300) if isinstance(steps, list) else [],
            triggers=safe_list_str(triggers, 4, 120) if isinstance(triggers, list) else [],
            model=model,
            raw=text_raw[:2000],
        )
    except Exception:  # noqa: BLE001 - never propagate parse failures
        return fail


class SubprocessModelJudge:
    """Real judge: run a configured command, prompt on stdin, JSON on stdout."""

    def __init__(self, command: str | None = None, timeout: float | None = None) -> None:
        self.command = command or os.environ.get("SCHOOL_SKILLGEN_JUDGE_CMD", "")
        self.timeout = timeout or JUDGE_TIMEOUT_S
        self.model_id = (
            os.environ.get("SCHOOL_SKILLGEN_JUDGE_MODEL", "") or "subprocess"
        )

    @property
    def available(self) -> bool:
        return bool(self.command.strip())

    def __call__(self, prompt: str) -> tuple[str, str]:
        if not self.available:
            raise RuntimeError("no judge command configured")
        proc = subprocess.run(  # noqa: S603 - operator-configured command
            self.command,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            shell=True,  # noqa: S602 - command string from local config env
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"judge failed rc={proc.returncode}")
        return proc.stdout.strip(), self.model_id


def default_judge() -> ModelJudge | None:
    """Judge from environment; None means automatic creation is disabled."""
    judge = SubprocessModelJudge()
    return judge if judge.available else None
