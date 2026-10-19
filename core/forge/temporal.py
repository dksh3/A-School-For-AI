"""Temporal intelligence — dates are first-class inputs and are never invented.

Mission 19B Part 3 rules, enforced here:

- A missing date is UNKNOWN, not "today", not "soon", and never a plausible
  fabrication. Distinguish a missing date from a date that is irrelevant.
- Ambiguous dates (``04/05/2026``) are flagged AMBIGUOUS until a convention is
  supplied. Where the ambiguity does not matter, callers may mark the fact
  ``NOT_APPLICABLE`` instead of asking.
- Deterministic validation of impossible sequences: deadline before start,
  invalid durations, conflicting schedules, expired dependencies, tools used
  before they existed, stale sources.
- Reference time is explicit. Pass ``now`` in; the default is UTC, never the
  machine's local timezone.

Date-state names map to the Stage-D vocabulary in :mod:`core.forge.requirements`
(``UNKNOWN``/``CONFLICTED``/``ASSUMED_WITH_AUTHORIZATION``/``DERIVED``/
``VERIFIED_EXTERNALLY``/``KNOWN_FROM_USER`` are the same concepts there);
``AMBIGUOUS`` is a date-specific refinement meaning "parsed, but the
convention is unknown".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

__all__ = [
    "AvailabilityCheck",
    "DatePrecision",
    "DateState",
    "ScheduleCheck",
    "TemporalFact",
    "check_availability",
    "check_staleness",
    "parse_date",
    "utc_today",
    "validate_schedule",
]


class DatePrecision(StrEnum):
    """How precise a date fact is."""

    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


class DateState(StrEnum):
    """Provenance state of a date fact (Stage-D vocabulary + AMBIGUOUS)."""

    SUPPLIED = "KNOWN_FROM_USER"
    DERIVED = "DERIVED"
    VERIFIED_EXTERNALLY = "VERIFIED_EXTERNALLY"
    ASSUMED = "ASSUMED_WITH_AUTHORIZATION"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTED = "CONFLICTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


_ISO_FULL = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_ISO_SLASH = re.compile(r"^(\d{4})/(\d{2})/(\d{2})$")
_NUMERIC = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_YEAR_ONLY = re.compile(r"^(\d{4})$")

CONVENTIONS = ("day-first", "month-first")


@dataclass
class TemporalFact:
    """One date fact with precision, provenance, and source."""

    label: str = ""
    value: date | None = None
    precision: DatePrecision = DatePrecision.UNKNOWN
    state: DateState = DateState.UNKNOWN
    source: str = ""
    timezone: str = "UTC"
    convention: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value.isoformat() if self.value else None,
            "precision": self.precision.value,
            "state": self.state.value,
            "source": self.source,
            "timezone": self.timezone,
            "convention": self.convention,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: Any) -> TemporalFact:
        d = d if isinstance(d, dict) else {}
        raw = d.get("value")
        parsed: date | None = None
        if isinstance(raw, date) and not isinstance(raw, datetime):
            parsed = raw
        elif isinstance(raw, str):
            try:
                parsed = date.fromisoformat(raw)
            except ValueError:
                parsed = None
        try:
            precision = DatePrecision(str(d.get("precision", "unknown")))
        except ValueError:
            precision = DatePrecision.UNKNOWN
        try:
            state = DateState(str(d.get("state", "UNKNOWN")))
        except ValueError:
            state = DateState.UNKNOWN
        return cls(
            label=str(d.get("label", "") or ""),
            value=parsed,
            precision=precision,
            state=state,
            source=str(d.get("source", "") or ""),
            timezone=str(d.get("timezone", "UTC") or "UTC"),
            convention=str(d.get("convention", "") or ""),
            note=str(d.get("note", "") or ""),
        )


def utc_today(now: datetime | None = None) -> date:
    """Reference date in UTC. Pass ``now`` to make the reference explicit."""
    if now is None:
        return datetime.now(UTC).date()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(UTC).date()


def parse_date(
    text: Any, *, convention: str = "", label: str = "", source: str = ""
) -> TemporalFact:
    """Parse a date string deterministically — or refuse to.

    - ``2026-04-05`` → day precision, supplied.
    - ``04/05/2026`` with both parts ≤ 12 → AMBIGUOUS unless ``convention`` is
      ``"day-first"`` or ``"month-first"``. Never silently assumed.
    - One part > 12 → unambiguous by construction; the note records the inference.
    - Unparseable text → UNKNOWN with value None (no invention).
    """
    if not isinstance(text, str) or not text.strip():
        return TemporalFact(
            label=label, state=DateState.UNKNOWN, source=source, note="no date supplied"
        )
    s = text.strip()
    for pattern, precision in ((_ISO_FULL, DatePrecision.DAY), (_ISO_SLASH, DatePrecision.DAY)):
        m = pattern.match(s)
        if m:
            try:
                value = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return TemporalFact(
                    label=label,
                    state=DateState.CONFLICTED,
                    source=source,
                    note=f"impossible date: {s!r}",
                )
            return TemporalFact(
                label=label,
                value=value,
                precision=precision,
                state=DateState.SUPPLIED,
                source=source,
            )
    m = _ISO_MONTH.match(s)
    if m:
        try:
            value = date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return TemporalFact(
                label=label,
                state=DateState.CONFLICTED,
                source=source,
                note=f"impossible month: {s!r}",
            )
        return TemporalFact(
            label=label,
            value=value,
            precision=DatePrecision.MONTH,
            state=DateState.SUPPLIED,
            source=source,
        )
    m = _YEAR_ONLY.match(s)
    if m:
        return TemporalFact(
            label=label,
            value=date(int(m.group(1)), 1, 1),
            precision=DatePrecision.YEAR,
            state=DateState.SUPPLIED,
            source=source,
        )
    m = _NUMERIC.match(s)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 and b <= 12:
            try:
                value = date(year, b, a)
            except ValueError:
                return TemporalFact(
                    label=label,
                    state=DateState.CONFLICTED,
                    source=source,
                    note=f"impossible date: {s!r}",
                )
            return TemporalFact(
                label=label,
                value=value,
                precision=DatePrecision.DAY,
                state=DateState.SUPPLIED,
                source=source,
                convention="day-first",
                note="inferred day-first (first part > 12)",
            )
        if b > 12 and a <= 12:
            try:
                value = date(year, a, b)
            except ValueError:
                return TemporalFact(
                    label=label,
                    state=DateState.CONFLICTED,
                    source=source,
                    note=f"impossible date: {s!r}",
                )
            return TemporalFact(
                label=label,
                value=value,
                precision=DatePrecision.DAY,
                state=DateState.SUPPLIED,
                source=source,
                convention="month-first",
                note="inferred month-first (second part > 12)",
            )
        if a <= 12 and b <= 12:
            if convention in CONVENTIONS:
                day, month = (a, b) if convention == "day-first" else (b, a)
                try:
                    value = date(year, month, day)
                except ValueError:
                    return TemporalFact(
                        label=label,
                        state=DateState.CONFLICTED,
                        source=source,
                        note=f"impossible date under {convention}: {s!r}",
                    )
                return TemporalFact(
                    label=label,
                    value=value,
                    precision=DatePrecision.DAY,
                    state=DateState.SUPPLIED,
                    source=source,
                    convention=convention,
                    note=f"resolved with declared convention {convention}",
                )
            return TemporalFact(
                label=label,
                state=DateState.AMBIGUOUS,
                source=source,
                note=(
                    f"{s!r} is ambiguous (day-first vs month-first) — convention required; "
                    "not interpreted"
                ),
            )
        return TemporalFact(
            label=label, state=DateState.CONFLICTED, source=source, note=f"impossible date: {s!r}"
        )
    return TemporalFact(
        label=label,
        state=DateState.UNKNOWN,
        source=source,
        note=f"unrecognized date text: {s!r} (not invented)",
    )


@dataclass
class ScheduleCheck:
    """Result of deterministic schedule validation."""

    ok: bool = True
    violations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "violations": list(self.violations),
            "unknowns": list(self.unknowns),
            "findings": list(self.findings),
            "contradictions": list(self.contradictions),
        }


def _as_fact(value: Any, label: str) -> TemporalFact:
    if isinstance(value, TemporalFact):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return TemporalFact(
            label=label, value=value, precision=DatePrecision.DAY, state=DateState.SUPPLIED
        )
    return parse_date(value, label=label)


def _coerce_date(value: Any) -> date | None:
    """Coerce a date-ish value (date, datetime, or parseable text) to a date.

    Returns ``None`` when the value cannot be interpreted — callers must treat
    that as unknown, never as a silent default.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return parse_date(value).value
    return None


def validate_schedule(
    *,
    start: Any = None,
    deadline: Any = None,
    duration_days: Any = None,
    reference: Any = None,
) -> ScheduleCheck:
    """Validate a start/deadline/duration triple deterministically.

    Violations: deadline before start, non-positive duration, declared duration
    contradicting the start→deadline span. Missing or ambiguous facts become
    ``unknowns`` — they are never resolved by guessing.

    ``contradictions`` classifies the self-regarding violations — impossible
    dates, malformed or non-positive durations, deadline-before-start, span
    mismatch — findings that could never be satisfied. Time-relative findings
    (an expired deadline versus a reference date) stay in ``violations`` only:
    real schedule violations, but not logical contradictions of the plan.
    """
    check = ScheduleCheck()
    ref = _coerce_date(reference) if reference is not None else None
    start_f = _as_fact(start, "start") if start is not None else None
    dead_f = _as_fact(deadline, "deadline") if deadline is not None else None

    for fact in (start_f, dead_f):
        if fact is None:
            continue
        if fact.state in (DateState.UNKNOWN, DateState.AMBIGUOUS, DateState.CONFLICTED):
            check.unknowns.append(f"{fact.label or 'date'}: {fact.state.value} — {fact.note}")
            if fact.state == DateState.CONFLICTED:
                msg = f"{fact.label or 'date'} is an impossible date: {fact.note}"
                check.violations.append(msg)
                check.contradictions.append(msg)

    days: int | None = None
    if duration_days is not None:
        try:
            days = int(duration_days)
        except (TypeError, ValueError):
            msg = f"duration_days is not an integer: {duration_days!r}"
            check.violations.append(msg)
            check.contradictions.append(msg)
        else:
            if days <= 0:
                msg = f"invalid duration: {days} days (must be positive)"
                check.violations.append(msg)
                check.contradictions.append(msg)

    if (
        start_f
        and dead_f
        and start_f.value is not None
        and dead_f.value is not None
    ):
        if dead_f.value < start_f.value:
            msg = (
                f"deadline {dead_f.value.isoformat()} precedes start {start_f.value.isoformat()}"
            )
            check.violations.append(msg)
            check.contradictions.append(msg)
        elif days is not None:
            span = (dead_f.value - start_f.value).days + 1
            if span != days:
                msg = (
                    f"conflicting schedule: declared duration {days} days does not match "
                    f"start→deadline span {span} days"
                )
                check.violations.append(msg)
                check.contradictions.append(msg)

    if (
        reference is not None
        and dead_f
        and dead_f.value is not None
        and ref is not None
        and dead_f.value < ref
    ):
        check.violations.append(
            f"deadline {dead_f.value.isoformat()} is already past the reference date "
            f"{ref.isoformat()} (expired dependency)"
        )
    elif reference is not None and ref is None:
        check.unknowns.append(
            f"reference date {reference!r} could not be interpreted — expiry not checked"
        )

    if start_f is None:
        check.unknowns.append("start: UNKNOWN — supply, derive, or mark not applicable")
    if dead_f is None:
        check.unknowns.append("deadline: UNKNOWN — supply, derive, or mark not applicable")

    check.ok = not check.violations
    check.findings = [*check.violations, *check.unknowns]
    return check


@dataclass
class AvailabilityCheck:
    """Was a tool/product/standard available at the relevant date?"""

    ok: bool = True
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "findings": list(self.findings)}


def check_availability(
    *,
    as_of: Any,
    available_from: Any = None,
    available_until: Any = None,
    item: str = "item",
) -> AvailabilityCheck:
    """Check an item's availability window against the date a plan relies on it.

    A tool released after the target date was NOT available then — historical
    tasks must not assume later releases existed. Dates may be ``date`` objects
    or parseable text; anything uninterpretable is reported, never guessed.
    """
    check = AvailabilityCheck()
    as_of_d = _coerce_date(as_of) if as_of is not None else None
    from_d = _coerce_date(available_from) if available_from is not None else None
    until_d = _coerce_date(available_until) if available_until is not None else None
    if as_of is None:
        check.ok = False
        check.findings.append("as_of date is required — availability needs a reference date")
        return check
    if as_of_d is None:
        check.ok = False
        check.findings.append(
            f"as_of {as_of!r} could not be interpreted — availability not checked"
        )
        return check
    if available_from is not None and from_d is None:
        check.ok = False
        check.findings.append(
            f"available_from {available_from!r} could not be interpreted — availability not checked"
        )
    if available_until is not None and until_d is None:
        check.ok = False
        check.findings.append(
            f"available_until {available_until!r} could not be interpreted — "
            "availability not checked"
        )
    if from_d is not None and as_of_d < from_d:
        check.ok = False
        check.findings.append(
            f"{item!r} was not available at {as_of_d.isoformat()} "
            f"(available from {from_d.isoformat()})"
        )
    if until_d is not None and as_of_d > until_d:
        check.ok = False
        check.findings.append(
            f"{item!r} had expired/retired by {as_of_d.isoformat()} "
            f"(available until {until_d.isoformat()})"
        )
    if check.ok:
        check.findings.append(f"{item!r} availability window covers {as_of_d.isoformat()}")
    return check


def check_staleness(
    source_date: Any,
    reference_date: Any,
    max_age_days: int,
    *,
    source_name: str = "source",
) -> AvailabilityCheck:
    """Flag stale external data: older than ``max_age_days`` at the reference date.

    Dates may be ``date`` objects or parseable text; anything uninterpretable is
    reported as unchecked, never guessed.
    """
    if max_age_days < 0:
        return AvailabilityCheck(ok=False, findings=["max_age_days must be >= 0"])
    src = _coerce_date(source_date)
    ref = _coerce_date(reference_date)
    if src is None or ref is None:
        which = "source_date" if src is None else "reference_date"
        return AvailabilityCheck(
            ok=False,
            findings=[f"{which} could not be interpreted — staleness not checked"],
        )
    age = (ref - src).days
    if age > max_age_days:
        return AvailabilityCheck(
            ok=False,
            findings=[
                f"{source_name} is stale: {age} days old at {ref.isoformat()} "
                f"(max {max_age_days})"
            ],
        )
    return AvailabilityCheck(ok=True, findings=[f"{source_name} is fresh: {age} days old"])
