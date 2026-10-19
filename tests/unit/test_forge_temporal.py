"""Temporal reasoning tests (Mission 19B Part 3 + Part 10).

ALL DATA IN THIS FILE IS SYNTHETIC and invented for tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from core.forge.temporal import (
    DatePrecision,
    DateState,
    check_availability,
    check_staleness,
    parse_date,
    utc_today,
    validate_schedule,
)


def test_iso_date_supplied_day_precision() -> None:
    f = parse_date("2026-04-05", label="start")
    assert f.value == date(2026, 4, 5)
    assert f.precision is DatePrecision.DAY
    assert f.state is DateState.SUPPLIED


def test_explicit_historical_date_kept_as_given() -> None:
    f = parse_date("2016-07-01", label="event")
    assert f.value == date(2016, 7, 1)  # NOT shifted to the machine's year
    assert f.state is DateState.SUPPLIED


def test_no_date_supplied_is_unknown_not_invented() -> None:
    f = parse_date("", label="deadline")
    assert f.value is None
    assert f.state is DateState.UNKNOWN
    f2 = parse_date("next spring", label="deadline")
    assert f2.value is None
    assert f2.state is DateState.UNKNOWN
    assert "not invented" in f2.note


def test_ambiguous_date_needs_convention() -> None:
    f = parse_date("04/05/2026", label="deadline")
    assert f.value is None
    assert f.state is DateState.AMBIGUOUS
    assert "convention required" in f.note


def test_ambiguous_date_resolved_with_declared_convention() -> None:
    d_first = parse_date("04/05/2026", convention="day-first")
    m_first = parse_date("04/05/2026", convention="month-first")
    assert d_first.value == date(2026, 5, 4)
    assert m_first.value == date(2026, 4, 5)
    assert d_first.state is DateState.SUPPLIED
    assert d_first.convention == "day-first"


def test_unambiguous_numeric_date_inferred() -> None:
    f = parse_date("25/12/2026")  # 25 > 12 → day-first by construction
    assert f.value == date(2026, 12, 25)
    assert f.state is DateState.SUPPLIED
    assert "inferred day-first" in f.note


def test_impossible_date_is_conflicted() -> None:
    f = parse_date("2026-02-30")
    assert f.state is DateState.CONFLICTED
    assert f.value is None


def test_deadline_before_start_is_violation() -> None:
    check = validate_schedule(start="2026-05-01", deadline="2026-04-01")
    assert not check.ok
    assert any("precedes start" in v for v in check.violations)


def test_invalid_duration_is_violation() -> None:
    check = validate_schedule(duration_days=0)
    assert not check.ok
    assert any("invalid duration" in v for v in check.violations)


def test_conflicting_duration_versus_span() -> None:
    check = validate_schedule(start="2026-05-01", deadline="2026-05-03", duration_days=10)
    assert not check.ok
    assert any("conflicting schedule" in v for v in check.violations)


def test_missing_dates_are_unknowns_not_violations() -> None:
    check = validate_schedule()
    assert check.ok  # nothing contradicts anything
    assert len(check.unknowns) >= 2
    assert any("start: UNKNOWN" in u for u in check.unknowns)


def test_expired_deadline_vs_reference() -> None:
    check = validate_schedule(start="2026-01-01", deadline="2026-02-01", reference=date(2026, 6, 1))
    assert not check.ok
    assert any("expired" in v for v in check.violations)


def test_tool_unavailable_at_historical_date() -> None:
    # A tool released in 2020 could not be used in a 2016 plan.
    check = check_availability(
        as_of=date(2016, 6, 1), available_from=date(2020, 1, 1), item="tool-X"
    )
    assert not check.ok
    assert any("not available" in f for f in check.findings)


def test_tool_available_inside_window() -> None:
    check = check_availability(
        as_of=date(2021, 6, 1),
        available_from=date(2020, 1, 1),
        available_until=date(2022, 1, 1),
        item="tool-X",
    )
    assert check.ok


def test_expired_dependency_by_available_until() -> None:
    check = check_availability(
        as_of=date(2023, 1, 1), available_until=date(2022, 1, 1), item="API-v1"
    )
    assert not check.ok
    assert any("expired" in f for f in check.findings)


def test_stale_source_flagged() -> None:
    stale = check_staleness(date(2024, 1, 1), date(2026, 1, 1), 180, source_name="price list")
    assert not stale.ok
    assert any("stale" in f for f in stale.findings)
    fresh = check_staleness(date(2025, 12, 1), date(2026, 1, 1), 180)
    assert fresh.ok


def test_reference_date_is_utc_not_local() -> None:
    aware = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
    assert utc_today(aware) == date(2026, 1, 1)
    naive = datetime(2026, 1, 1, 23, 30)  # treated as UTC, not machine-local
    assert utc_today(naive) == date(2026, 1, 1)


def test_temporal_fact_round_trip() -> None:
    f = parse_date("2026-04-05", label="start", source="user")
    d = f.to_dict()
    assert d["value"] == "2026-04-05"
    from core.forge.temporal import TemporalFact

    f2 = TemporalFact.from_dict(d)
    assert f2.value == f.value and f2.state is DateState.SUPPLIED
    assert f2.source == "user"


# --- Regression: date-typed APIs must accept ISO strings (Mission 20 probe crash).
# SYNTHETIC inputs. Before the fix these raised TypeError/AttributeError.


def test_validate_schedule_accepts_iso_string_reference() -> None:
    check = validate_schedule(
        start="2026-03-15",
        deadline="2026-03-01",
        duration_days=None,
        reference="2026-04-01",
    )
    assert check.ok is False
    assert any("expired" in v or "past" in v for v in check.violations)


def test_validate_schedule_string_dates_all_round() -> None:
    check = validate_schedule(
        start="2026-03-15",
        deadline="2026-04-01",
        duration_days=None,
        reference="2026-01-01",
    )
    assert check.ok is True


def test_validate_schedule_unparseable_reference_is_unknown_not_crash() -> None:
    check = validate_schedule(
        start="2026-03-15",
        deadline="2026-04-01",
        duration_days=None,
        reference="next spring",
    )
    assert check.ok is True  # expiry simply not checked
    assert any("reference" in u.lower() for u in check.unknowns)


def test_check_availability_accepts_iso_strings() -> None:
    chk = check_availability(
        as_of="2016-06-01",
        available_from="2020-01-01",
        available_until=None,
        item="tool-v2",
    )
    assert any("not available" in f for f in chk.findings)


def test_check_staleness_accepts_iso_strings() -> None:
    out = check_staleness("2020-01-01", "2023-01-01", 365, source_name="dataset")
    assert any("stale" in f for f in out.findings)


def test_mixed_string_and_date_inputs_work() -> None:
    check = validate_schedule(
        start=date(2026, 3, 15),
        deadline="2026-03-01",
        duration_days=None,
        reference=date(2026, 1, 1),
    )
    assert check.ok is False


def test_schedule_contradictions_classify_self_contradictions() -> None:
    """SYNTHETIC: self-contradicting schedule facts land in `contradictions` (Mission 20.1)."""
    check = validate_schedule(start="2026-03-15", deadline="2026-03-01", duration_days=14)
    assert any("precedes start" in c for c in check.contradictions)
    assert any("precedes start" in v for v in check.violations)

    dur = validate_schedule(start="2026-03-01", deadline="2026-03-10", duration_days=0)
    assert any("must be positive" in c for c in dur.contradictions)

    span = validate_schedule(start="2026-03-01", deadline="2026-03-10", duration_days=99)
    assert any("does not match" in c for c in span.contradictions)

    bad = validate_schedule(duration_days="soon")
    assert any("not an integer" in c for c in bad.contradictions)

    impossible = validate_schedule(start="2026-02-30", deadline="2026-03-10")
    assert any("impossible date" in c for c in impossible.contradictions)


def test_expired_reference_is_time_relative_not_contradiction() -> None:
    """SYNTHETIC: expiry is a real violation but not a logical contradiction of the plan."""
    check = validate_schedule(start="2026-01-01", deadline="2026-02-01", reference="2026-04-01")
    assert any("expired dependency" in v for v in check.violations)
    assert not any("expired dependency" in c for c in check.contradictions)
    assert check.ok is False
