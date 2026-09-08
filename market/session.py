"""
APEX / BENVIN Forex Session Context

Phase 2.6.12 prerequisite

Provides deterministic, provider-neutral Forex trading-session context from
an explicit UTC timestamp. Session definitions are configurable and use IANA
zoneinfo time zones so daylight-saving changes are handled by the standard
library rather than by fixed UTC offsets.

This module does NOT:
    - generate trading signals
    - rank sessions by profitability
    - recommend an entry
    - calculate stop-loss/take-profit
    - size a position
    - authorize or execute trades

The default definitions are market-convention starting points only. They are
not assertions that any session is more profitable than another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from math import isfinite
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class SessionContextError(ValueError):
    """Raised when session configuration or timestamp input is invalid."""


class SessionStatus(str, Enum):
    EVALUATED = "EVALUATED"
    INVALID_INPUT = "INVALID_INPUT"
    ERROR = "ERROR"


class SessionPhase(str, Enum):
    OFF_SESSION = "OFF_SESSION"
    SINGLE_SESSION = "SINGLE_SESSION"
    OVERLAP = "OVERLAP"


def _parse_local_time(value: str, field_name: str) -> time:
    if not isinstance(value, str):
        raise SessionContextError(f"{field_name} must use HH:MM format")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise SessionContextError(f"{field_name} must use HH:MM format") from exc
    if parsed.second != 0 or parsed.microsecond != 0 or parsed.tzinfo is not None:
        raise SessionContextError(f"{field_name} must use HH:MM format")
    return parsed


@dataclass(frozen=True)
class SessionDefinition:
    """One configurable Forex session expressed in local market time."""

    name: str
    timezone: str
    start_local: str
    end_local: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise SessionContextError("session name must be a non-empty string")
        if not isinstance(self.timezone, str) or not self.timezone.strip():
            raise SessionContextError("session timezone must be a non-empty string")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise SessionContextError(
                f"unknown IANA timezone: {self.timezone!r}"
            ) from exc
        _parse_local_time(self.start_local, "start_local")
        _parse_local_time(self.end_local, "end_local")
        if self.start_local == self.end_local:
            raise SessionContextError("session start_local and end_local must differ")

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "timezone": self.timezone,
            "start_local": self.start_local,
            "end_local": self.end_local,
        }


DEFAULT_FOREX_SESSIONS: tuple[SessionDefinition, ...] = (
    SessionDefinition("SYDNEY", "Australia/Sydney", "08:00", "17:00"),
    SessionDefinition("TOKYO", "Asia/Tokyo", "09:00", "18:00"),
    SessionDefinition("LONDON", "Europe/London", "08:00", "17:00"),
    SessionDefinition("NEW_YORK", "America/New_York", "08:00", "17:00"),
)


def _ensure_utc(timestamp: datetime) -> datetime:
    if not isinstance(timestamp, datetime):
        raise SessionContextError("timestamp must be a datetime")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise SessionContextError("timestamp must be timezone-aware")
    return timestamp.astimezone(timezone.utc)


def _in_local_window(local_time: time, start: time, end: time) -> bool:
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


def _active(definition: SessionDefinition, timestamp_utc: datetime) -> bool:
    zone = ZoneInfo(definition.timezone)
    local = timestamp_utc.astimezone(zone)
    local_time = local.timetz().replace(tzinfo=None)
    start = _parse_local_time(definition.start_local, "start_local")
    end = _parse_local_time(definition.end_local, "end_local")
    return _in_local_window(local_time, start, end)


def _validate_definitions(
    definitions: Iterable[SessionDefinition],
) -> tuple[SessionDefinition, ...]:
    try:
        values = tuple(definitions)
    except TypeError as exc:
        raise SessionContextError("session definitions must be iterable") from exc
    if not values:
        raise SessionContextError("at least one session definition is required")
    if any(not isinstance(item, SessionDefinition) for item in values):
        raise SessionContextError("all session definitions must be SessionDefinition instances")
    names = [item.name.strip().upper() for item in values]
    if len(set(names)) != len(names):
        raise SessionContextError("session definition names must be unique")
    return values


@dataclass(frozen=True)
class ForexSessionContext:
    """Immutable point-in-time description of active Forex sessions."""

    timestamp_utc: str
    status: str
    phase: str
    active_sessions: tuple[str, ...]
    active_session_count: int
    overlap: bool
    local_times: dict[str, str] = field(default_factory=dict)
    definitions: tuple[dict[str, str], ...] = ()
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.status == SessionStatus.EVALUATED.value,
            "market": "forex",
            "context": "session",
            "status": self.status,
            "timestamp_utc": self.timestamp_utc,
            "phase": self.phase,
            "active_sessions": list(self.active_sessions),
            "active_session_count": self.active_session_count,
            "overlap": self.overlap,
            "local_times": dict(self.local_times),
            "definitions": [dict(item) for item in self.definitions],
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }
        if self.error is not None:
            result["error"] = self.error
        return result


def assess_forex_session(
    timestamp: datetime,
    *,
    definitions: Iterable[SessionDefinition] | None = None,
) -> ForexSessionContext:
    """Evaluate active Forex sessions for one explicit point in time."""
    try:
        timestamp_utc = _ensure_utc(timestamp)
        configured = _validate_definitions(
            DEFAULT_FOREX_SESSIONS if definitions is None else definitions
        )
    except SessionContextError:
        raise
    except Exception as exc:
        raise SessionContextError(str(exc)) from exc

    active = tuple(
        definition.name.strip().upper()
        for definition in configured
        if _active(definition, timestamp_utc)
    )

    if not active:
        phase = SessionPhase.OFF_SESSION.value
    elif len(active) == 1:
        phase = SessionPhase.SINGLE_SESSION.value
    else:
        phase = SessionPhase.OVERLAP.value

    local_times = {
        definition.name.strip().upper(): timestamp_utc.astimezone(
            ZoneInfo(definition.timezone)
        ).isoformat()
        for definition in configured
    }

    return ForexSessionContext(
        timestamp_utc=timestamp_utc.isoformat(),
        status=SessionStatus.EVALUATED.value,
        phase=phase,
        active_sessions=active,
        active_session_count=len(active),
        overlap=len(active) > 1,
        local_times=local_times,
        definitions=tuple(item.to_dict() for item in configured),
        reasons=(),
        warnings=(
            "session classification describes timing only; it does not imply profitability"
        ,),
        metadata={
            "calculation": "deterministic_python_zoneinfo",
            "timezone_basis": "IANA",
            "timestamp_basis": "UTC",
        },
    )


class ForexSessionEngine:
    """Reusable facade for deterministic Forex session assessment."""

    def __init__(
        self,
        definitions: Iterable[SessionDefinition] | None = None,
    ) -> None:
        self.definitions = _validate_definitions(
            DEFAULT_FOREX_SESSIONS if definitions is None else definitions
        )

    def assess(self, timestamp: datetime) -> ForexSessionContext:
        return assess_forex_session(timestamp, definitions=self.definitions)


__all__ = [
    "DEFAULT_FOREX_SESSIONS",
    "ForexSessionContext",
    "ForexSessionEngine",
    "SessionContextError",
    "SessionDefinition",
    "SessionPhase",
    "SessionStatus",
    "assess_forex_session",
]
