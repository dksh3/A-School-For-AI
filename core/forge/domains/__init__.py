"""Domain question banks for Forge discovery interviews.

One module per domain (11 in total) plus a universal ``general`` fallback so
*any* work item is first-class — this suite is not coding-only. Each module
exposes ``QUESTIONS(domain) -> list[Question]`` returning 10-14 discovery
questions spanning the 12 interview dimensions.

Followup convention: a followup ``Question`` whose ``domain_hint`` starts with
``when:`` fires only when its parent's answer matches one of the triggers, e.g.
``when:Yes`` or ``when:Option A|Option B`` (``when:*`` always fires). The
engine in ``core.forge.clarion`` parses this convention.

Every public function here is fail-open: hostile input degrades to the GENERAL
bank (or an empty list) and never raises.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.forge.models import Domain, Question

from . import (
    business,
    coding,
    creative,
    data,
    education,
    general,
    life,
    ops,
    planning,
    research,
    writing,
)

#: domain name -> builder returning a fresh list of questions (fail-open).
DOMAIN_QUESTIONBANKS: dict[str, Callable[..., list[Question]]] = {
    Domain.CODING.value: coding.QUESTIONS,
    Domain.WRITING.value: writing.QUESTIONS,
    Domain.RESEARCH.value: research.QUESTIONS,
    Domain.BUSINESS.value: business.QUESTIONS,
    Domain.PLANNING.value: planning.QUESTIONS,
    Domain.EDUCATION.value: education.QUESTIONS,
    Domain.CREATIVE.value: creative.QUESTIONS,
    Domain.OPS.value: ops.QUESTIONS,
    Domain.DATA.value: data.QUESTIONS,
    Domain.LIFE.value: life.QUESTIONS,
    Domain.GENERAL.value: general.QUESTIONS,
}

#: Every first-class domain name, in canonical order.
ALL_DOMAINS: list[str] = list(DOMAIN_QUESTIONBANKS.keys())


def _copy_questions(raw: Any) -> list[Question]:
    """Return validated deep copies of ``raw`` questions. Never raises."""
    out: list[Question] = []
    try:
        items = raw if isinstance(raw, (list, tuple)) else []
    except Exception:  # noqa: BLE001
        return out
    for item in items:
        try:
            if isinstance(item, Question):
                out.append(Question.from_dict(item.to_dict()))
            elif isinstance(item, dict):
                out.append(Question.from_dict(item))
        except Exception:  # noqa: BLE001
            continue
    return out


def get_questionbank(domain: Any = Domain.GENERAL) -> list[Question]:
    """Return a fresh copy of the question bank for ``domain``.

    Unknown or hostile domains fall back to the ``general`` bank, and any
    failure at all returns the general bank (or an empty list). Never raises.
    """
    try:
        key = Domain.coerce(domain).value
    except Exception:  # noqa: BLE001
        key = Domain.GENERAL.value
    loader = DOMAIN_QUESTIONBANKS.get(key) or DOMAIN_QUESTIONBANKS[Domain.GENERAL.value]
    result: list[Question] = []
    try:
        if callable(loader):
            result = _copy_questions(loader(domain))
    except Exception:  # noqa: BLE001
        result = []
    if result:
        return result
    try:
        fallback = DOMAIN_QUESTIONBANKS[Domain.GENERAL.value]
        return _copy_questions(fallback(domain))
    except Exception:  # noqa: BLE001
        return []
