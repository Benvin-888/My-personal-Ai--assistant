from datetime import datetime, timezone

import pytest

from market.session import (
    DEFAULT_FOREX_SESSIONS,
    ForexSessionEngine,
    SessionContextError,
    SessionDefinition,
    SessionPhase,
    SessionStatus,
    assess_forex_session,
)


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_default_definitions_cover_four_major_sessions():
    names = [item.name for item in DEFAULT_FOREX_SESSIONS]
    assert names == ["SYDNEY", "TOKYO", "LONDON", "NEW_YORK"]


def test_london_is_active_during_local_session_hours():
    result = assess_forex_session(utc("2026-01-15T10:00:00"))
    assert result.status == SessionStatus.EVALUATED.value
    assert "LONDON" in result.active_sessions


def test_new_york_is_active_during_local_session_hours():
    result = assess_forex_session(utc("2026-01-15T14:00:00"))
    assert "NEW_YORK" in result.active_sessions


def test_london_new_york_overlap_is_reported():
    result = assess_forex_session(utc("2026-01-15T14:00:00"))
    assert result.phase == SessionPhase.OVERLAP.value
    assert result.overlap is True
    assert "LONDON" in result.active_sessions
    assert "NEW_YORK" in result.active_sessions


def test_dst_is_resolved_by_iana_timezone_data():
    winter = assess_forex_session(utc("2026-01-15T13:30:00"))
    summer = assess_forex_session(utc("2026-07-15T13:30:00"))
    assert winter.local_times["NEW_YORK"].startswith("2026-01-15T08:30:00")
    assert summer.local_times["NEW_YORK"].startswith("2026-07-15T09:30:00")


def test_tokyo_timezone_has_no_dst_shift():
    winter = assess_forex_session(utc("2026-01-15T00:30:00"))
    summer = assess_forex_session(utc("2026-07-15T00:30:00"))
    assert winter.local_times["TOKYO"].startswith("2026-01-15T09:30:00")
    assert summer.local_times["TOKYO"].startswith("2026-07-15T09:30:00")


def test_off_session_is_explicit():
    definitions = [SessionDefinition("TEST", "UTC", "08:00", "10:00")]
    result = assess_forex_session(utc("2026-01-15T21:30:00"), definitions=definitions)
    assert result.phase == SessionPhase.OFF_SESSION.value
    assert result.active_sessions == ()
    assert result.active_session_count == 0
    assert result.overlap is False


def test_single_session_is_explicit():
    result = assess_forex_session(utc("2026-01-15T11:00:00"))
    assert result.phase == SessionPhase.SINGLE_SESSION.value
    assert result.active_session_count == 1


def test_session_boundaries_are_start_inclusive_and_end_exclusive():
    definitions = [SessionDefinition("TEST", "UTC", "08:00", "10:00")]
    at_start = assess_forex_session(utc("2026-01-15T08:00:00"), definitions=definitions)
    at_end = assess_forex_session(utc("2026-01-15T10:00:00"), definitions=definitions)
    assert at_start.active_sessions == ("TEST",)
    assert at_end.active_sessions == ()


def test_overnight_custom_session_is_supported():
    definitions = [SessionDefinition("OVERNIGHT", "UTC", "22:00", "06:00")]
    late = assess_forex_session(utc("2026-01-15T23:30:00"), definitions=definitions)
    early = assess_forex_session(utc("2026-01-16T05:59:59"), definitions=definitions)
    end = assess_forex_session(utc("2026-01-16T06:00:00"), definitions=definitions)
    assert late.active_sessions == ("OVERNIGHT",)
    assert early.active_sessions == ("OVERNIGHT",)
    assert end.active_sessions == ()


def test_custom_session_timezone_is_supported():
    definitions = [SessionDefinition("CUSTOM", "Europe/London", "08:00", "09:00")]
    result = assess_forex_session(utc("2026-07-15T07:30:00"), definitions=definitions)
    assert result.active_sessions == ("CUSTOM",)


def test_duplicate_session_names_are_rejected():
    definitions = [
        SessionDefinition("A", "UTC", "08:00", "09:00"),
        SessionDefinition("a", "UTC", "10:00", "11:00"),
    ]
    with pytest.raises(SessionContextError):
        assess_forex_session(utc("2026-01-15T08:30:00"), definitions=definitions)


def test_empty_definitions_are_rejected():
    with pytest.raises(SessionContextError):
        assess_forex_session(utc("2026-01-15T08:30:00"), definitions=[])


def test_invalid_timezone_is_rejected():
    with pytest.raises(SessionContextError):
        SessionDefinition("BAD", "Not/AZone", "08:00", "09:00")


def test_equal_start_and_end_are_rejected():
    with pytest.raises(SessionContextError):
        SessionDefinition("BAD", "UTC", "08:00", "08:00")


def test_naive_timestamp_is_rejected():
    with pytest.raises(SessionContextError):
        assess_forex_session(datetime(2026, 1, 15, 8, 30))


def test_non_datetime_timestamp_is_rejected():
    with pytest.raises(SessionContextError):
        assess_forex_session("2026-01-15T08:30:00+00:00")


def test_timezone_aware_non_utc_input_is_normalized():
    result = assess_forex_session(datetime.fromisoformat("2026-01-15T09:30:00+01:00"))
    assert result.timestamp_utc == "2026-01-15T08:30:00+00:00"


def test_engine_uses_configured_definitions():
    definitions = [SessionDefinition("TEST", "UTC", "08:00", "09:00")]
    engine = ForexSessionEngine(definitions)
    result = engine.assess(utc("2026-01-15T08:30:00"))
    assert result.active_sessions == ("TEST",)


def test_engine_matches_function():
    timestamp = utc("2026-01-15T14:00:00")
    engine = ForexSessionEngine()
    assert engine.assess(timestamp).to_dict() == assess_forex_session(timestamp).to_dict()


def test_to_dict_is_serializable_and_explicit():
    result = assess_forex_session(utc("2026-01-15T14:00:00")).to_dict()
    assert result["success"] is True
    assert result["market"] == "forex"
    assert result["context"] == "session"
    assert result["phase"] == "OVERLAP"
    assert "LONDON" in result["active_sessions"]
    assert result["metadata"]["timezone_basis"] == "IANA"


def test_definitions_are_snapshot_copied_into_result():
    definitions = [SessionDefinition("TEST", "UTC", "08:00", "09:00")]
    result = assess_forex_session(utc("2026-01-15T08:30:00"), definitions=definitions)
    assert result.definitions == ({
        "name": "TEST",
        "timezone": "UTC",
        "start_local": "08:00",
        "end_local": "09:00",
    },)
