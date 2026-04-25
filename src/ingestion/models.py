from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    sport: str
    tournament_name: str
    league_name: str
    start_time_utc: datetime
    status: str


@dataclass(frozen=True)
class ParticipantRecord:
    participant_id: str
    event_id: str
    participant_name: str
    role: str


@dataclass(frozen=True)
class MarketRecord:
    market_id: str
    event_id: str
    market_type: str
    selection_participant_id: str
    market_status: str
    is_uncertain: bool


@dataclass(frozen=True)
class OddsRecord:
    decimal_odds: float | None
    is_suspended: bool
    is_missing: bool
    is_uncertain: bool


@dataclass(frozen=True)
class SourceSnapshot:
    source_name: str
    snapshot_time_utc: datetime
    event: EventRecord
    participants: tuple[ParticipantRecord, ...]
    market: MarketRecord
    odds: OddsRecord


@dataclass(frozen=True)
class NormalizedSnapshot:
    odds_snapshot_id: str
    event: EventRecord
    participants: tuple[ParticipantRecord, ...]
    market: MarketRecord
    source_name: str
    source_role: str
    decimal_odds: float
    implied_probability: float
    snapshot_time_utc: datetime
    is_suspended: bool
    is_stale: bool
    is_missing: bool
    is_uncertain: bool
    ingested_at: datetime


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
