from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from .models import EventRecord, MarketRecord, NormalizedSnapshot, ParticipantRecord


class ConnectionLike(Protocol):
    def execute(self, sql: str, params: tuple | list) -> object: ...
    def executemany(self, sql: str, params: list[tuple]) -> object: ...
    def commit(self) -> None: ...


class IngestionRepository:
    def __init__(self, connection: ConnectionLike) -> None:
        self._connection = connection

    def write_snapshot(self, normalized: NormalizedSnapshot) -> None:
        now = normalized.ingested_at.astimezone(timezone.utc)
        self._upsert_event(normalized.event, now)
        self._upsert_participants(normalized.participants, now)
        self._upsert_market(normalized.market, now)
        self._insert_odds_snapshot(normalized)
        self._connection.commit()

    def _upsert_event(self, event: EventRecord, now: datetime) -> None:
        self._connection.execute(
            """
            INSERT INTO events (
                event_id, sport, tournament_name, league_name, start_time_utc, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                sport=excluded.sport,
                tournament_name=excluded.tournament_name,
                league_name=excluded.league_name,
                start_time_utc=excluded.start_time_utc,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                event.event_id,
                event.sport,
                event.tournament_name,
                event.league_name,
                event.start_time_utc.isoformat(),
                event.status,
                now.isoformat(),
                now.isoformat(),
            ),
        )

    def _upsert_participants(self, participants: tuple[ParticipantRecord, ...], now: datetime) -> None:
        for participant in participants:
            self._connection.execute(
                """
                INSERT INTO participants (
                    participant_id, event_id, participant_name, role, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(participant_id) DO UPDATE SET
                    event_id=excluded.event_id,
                    participant_name=excluded.participant_name,
                    role=excluded.role,
                    updated_at=excluded.updated_at
                """,
                (
                    participant.participant_id,
                    participant.event_id,
                    participant.participant_name,
                    participant.role,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

    def _upsert_market(self, market: MarketRecord, now: datetime) -> None:
        self._connection.execute(
            """
            INSERT INTO markets (
                market_id, event_id, market_type, selection_participant_id, market_status, is_uncertain, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id) DO UPDATE SET
                event_id=excluded.event_id,
                market_type=excluded.market_type,
                selection_participant_id=excluded.selection_participant_id,
                market_status=excluded.market_status,
                is_uncertain=excluded.is_uncertain,
                updated_at=excluded.updated_at
            """,
            (
                market.market_id,
                market.event_id,
                market.market_type,
                market.selection_participant_id,
                market.market_status,
                market.is_uncertain,
                now.isoformat(),
                now.isoformat(),
            ),
        )

    def _insert_odds_snapshot(self, normalized: NormalizedSnapshot) -> None:
        self._connection.execute(
            """
            INSERT INTO odds_snapshots (
                odds_snapshot_id,
                event_id,
                market_id,
                source_name,
                source_role,
                decimal_odds,
                implied_probability,
                snapshot_time_utc,
                is_suspended,
                is_stale,
                is_missing,
                is_uncertain,
                ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized.odds_snapshot_id,
                normalized.event.event_id,
                normalized.market.market_id,
                normalized.source_name,
                normalized.source_role,
                normalized.decimal_odds,
                normalized.implied_probability,
                normalized.snapshot_time_utc.isoformat(),
                normalized.is_suspended,
                normalized.is_stale,
                normalized.is_missing,
                normalized.is_uncertain,
                normalized.ingested_at.isoformat(),
            ),
        )
