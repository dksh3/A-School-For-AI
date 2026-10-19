"""Shared evidence vocabulary for the Forge suite (skills + product).

One place defines what PASS / FAIL / UNVERIFIED / SIMULATED / EXPLORATORY mean
and whether a status counts as proof of done. The ``forge`` and ``gate`` skills
state the same rules in prose (``tests/unit/test_suite_contracts.py`` asserts
the two copies stay identical).

Minimal on purpose: statuses are plain vocabulary, not a framework.
"""

from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    """Evidence status for a single checked claim."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"
    SIMULATED = "SIMULATED"
    EXPLORATORY = "EXPLORATORY"


def counts_as_pass(status: Status | str, *, user_accepted_proxy: bool = False) -> bool:
    """Does this status prove the claim is done?

    - PASS: yes - the check ran and its evidence is recorded.
    - SIMULATED: only when the user explicitly accepted the proxy for the
      stated purpose. Three simulated readers are not three readers.
    - UNVERIFIED / EXPLORATORY / FAIL: never.
    """
    s = Status(status)
    if s is Status.PASS:
        return True
    if s is Status.SIMULATED:
        return bool(user_accepted_proxy)
    return False


def gate_row(severity: str) -> dict[str, object]:
    """Map a scrutinize finding severity to gate evidence-row policy.

    must-fix  -> blocking: gate cannot pass while it is open.
    should-fix -> non-blocking: becomes a GO-WITH-CONDITIONS condition with an
                  owner; unresolved at verdict time stays a condition, never a GO.
    note      -> non-blocking: recorded, never decides the verdict.
    """
    sev = str(severity).strip().lower().replace("_", "-")
    if sev in ("must-fix", "must fix", "mustfix"):
        return {"severity": "must-fix", "blocking": True, "gate_type": "hard-floor"}
    if sev in ("should-fix", "should fix", "shouldfix"):
        return {"severity": "should-fix", "blocking": False, "gate_type": "condition"}
    return {"severity": "note", "blocking": False, "gate_type": "note"}
