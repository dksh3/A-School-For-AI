"""Security and structural validation for generated skills (1A-2Z).

A skill is an instructional procedure, not executable code. Validation
enforces schema completeness, size limits, name format, and the existing
instruction/data boundary (reuses core.routing.v26.security.detect_injection
plus a forbidden-pattern list). Failures keep the skill out of retrieval.
"""

from __future__ import annotations

import re

from core.routing.v26.security import detect_injection
from core.skillgen.types import MAX_FIELD, MAX_PROCEDURE_STEPS, NAME_RE, Skill

# Content a skill must never contain (instruction-boundary enforcement).
_FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", "instruction_override"),
    (r"\brm\s+-[rf]*\s+[~/]", "destructive_command"),
    (r"curl\s+[^\n|]*\|\s*(ba)?sh", "pipe_to_shell"),
    (r"wget\s+[^\n|]*\|\s*(ba)?sh", "pipe_to_shell"),
    (r"\bsudo\s+\b", "privilege_escalation"),
    (r"(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9]{12,}", "embedded_secret"),
    (r"\b(exfiltrat|send\s+to\s+https?://\S+\s+(credentials|tokens|files))", "exfiltration"),
    (r"\bdisable\s+(the\s+)?(security|firewall|antivirus|audit)\b", "security_bypass"),
)


def validate_skill(skill: Skill) -> tuple[bool, str]:
    """Structural + safety validation. Returns (ok, reason)."""
    if not NAME_RE.match(skill.name or ""):
        return False, "name must be kebab-case [a-z0-9-], 2-64 chars"
    if not skill.description or len(skill.description) > MAX_FIELD:
        return False, "description required and within size limit"
    if not skill.purpose or len(skill.purpose) > MAX_FIELD:
        return False, "purpose required and within size limit"
    if not skill.procedure:
        return False, "procedure required"
    if len(skill.procedure) > MAX_PROCEDURE_STEPS:
        return False, "procedure too long"
    if not (0.0 <= skill.confidence <= 1.0):
        return False, "confidence must be in [0, 1]"

    joined = "\n".join(
        [skill.description, skill.purpose, skill.expected_output]
        + skill.procedure
        + skill.constraints
        + skill.triggers
        + skill.inputs
        + skill.examples
    )
    if len(joined) > 60_000:
        return False, "skill content exceeds size limit"

    is_injection, kind = detect_injection(joined)
    if is_injection:
        return False, f"content rejected by security policy: {kind}"

    for pattern, reason in _FORBIDDEN_PATTERNS:
        if re.search(pattern, joined, re.IGNORECASE):
            return False, f"content rejected: {reason}"

    # Procedure steps must be text instructions, not shell/code payloads.
    for step in skill.procedure:
        if step.strip().startswith("```"):
            return False, "procedure steps must be plain instructions, not code blocks"
    return True, "ok"


def validate_for_creation(skill: Skill) -> tuple[bool, str]:
    """Extra gates applied on every new registration."""
    return validate_skill(skill)
