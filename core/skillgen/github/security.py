"""Deterministic security classification of UNTRUSTED GitHub content.

Everything retrieved from GitHub is data to analyze, never instructions to
follow. Reuses Phase 1's detect_injection and _FORBIDDEN_PATTERNS so there
is only ONE security policy. Model output can never make a candidate safer
than the deterministic classification says it is.
"""

from __future__ import annotations

import re

from core.routing.v26.security import detect_injection
from core.skillgen.github.models import SecurityLevel
from core.skillgen.validate import _FORBIDDEN_PATTERNS  # noqa: PLC2701 - single shared policy

# Additional Phase 2 patterns: credential/env theft, encoded payloads,
# privilege escalation, sandbox bypass, download-then-execute.
_PHASE2_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bprocess\.env\.(GITHUB_TOKEN|AWS_SECRET|API_KEY|PASSWORD)\b", "env_theft"),
    (r"\bgetenv\s*\(\s*['\"](GITHUB_TOKEN|AWS_SECRET|API_KEY)", "env_theft"),
    (r"eval\s*\(\s*(atob|Buffer\.from\s*\([^)]*base64)", "encoded_payload"),
    (r"-EncodedCommand|FromBase64String", "encoded_payload"),
    (r"\bchmod\s+[0-7]{3,4}\s|setuid|setgid\b", "privilege_escalation"),
    (
        r"disable\s+(the\s+)?(security|sandbox|guard)s?|bypass\s+(security|auth|sandbox)",
        "security_bypass",
    ),
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts)", "instruction_override"),
    (r"\.ssh/|id_rsa|\.aws/credentials|\.netrc", "credential_access"),
    (r"Invoke-Expression\s*\(\s*(New-Object|IWR|Invoke-WebRequest)", "ps_download_execute"),
)

# Reviewable but not automatically fatal (legit skills often shell out).
_REVIEW_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"```\s*(bash|sh|shell|powershell|console)\b", "executable_code_block"),
    (r"\b(npm|pip|pip3|brew|apt|choco|docker)\s+install\b", "package_install"),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|Remove-Item\s+.*-Recurse\b", "destructive_command"),
    (r"\bsudo\b|\bwinget\s+install\b", "elevated_command"),
    (r"git\s+clone\s+https?://", "remote_clone"),
)

_SPAM_NAME = re.compile(
    r"free-?followers|giveaway|clickbait|100-?stars|seo-?spam|crypto-?airdrop", re.IGNORECASE
)


def classify_content(text: str) -> tuple[SecurityLevel, list[str]]:
    """Deterministic classification of untrusted content. Fail closed."""
    reasons: list[str] = []
    level = SecurityLevel.SAFE
    if not text or not text.strip():
        return SecurityLevel.SAFE, reasons

    injected, why = detect_injection(text)
    if injected:
        return SecurityLevel.REJECTED, [f"injection:{why}"]

    for pattern, reason in _FORBIDDEN_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            level = level.stricter_than(SecurityLevel.HIGH_RISK)
            reasons.append(f"forbidden:{reason}")
    for pattern, reason in _PHASE2_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if reason in ("instruction_override", "credential_access"):
                level = level.stricter_than(SecurityLevel.REJECTED)
            else:
                level = level.stricter_than(SecurityLevel.HIGH_RISK)
            reasons.append(reason)
    for pattern, reason in _REVIEW_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            level = level.stricter_than(SecurityLevel.REVIEW_REQUIRED)
            reasons.append(reason)
    return level, reasons


def classify_repository(name: str, description: str = "") -> tuple[SecurityLevel, list[str]]:
    """Cheap pre-content signals (spam names etc.)."""
    if _SPAM_NAME.search(name) or _SPAM_NAME.search(description or ""):
        return SecurityLevel.REJECTED, ["spam_name"]
    return SecurityLevel.SAFE, []


def effective_level(
    deterministic: SecurityLevel,
    model_claim: str = "",
) -> SecurityLevel:
    """The model can never relax the deterministic classification."""
    try:
        claimed = SecurityLevel(str(model_claim or "").strip().upper())
    except ValueError:
        return deterministic
    return claimed.stricter_than(deterministic)


__all__ = ["classify_content", "classify_repository", "effective_level"]
