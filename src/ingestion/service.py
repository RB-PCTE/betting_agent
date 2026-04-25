from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
from typing import Iterable

from src.config import ProjectConfig

from .models import (
    NormalizedSnapshot,
    SourceSnapshot,
)
from .repository import IngestionRepository


@dataclass(frozen=True)
class RejectedRecord:
    source_name: str
    event_id: str
    market_id: str
    reason: str


@dataclass(frozen=True)
class IngestionResult:
    accepted_count: int
    rejected_count: int
    rejected_records: tuple[RejectedRecord, ...]


class OddsIngestionService:
    def __init__(
        self,
        config: ProjectConfig,
        repository: IngestionRepository | None,
        dry_run: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._repository = repository
        self._dry_run = dry_run
        self._logger = logger or logging.getLogger(__name__)

    def ingest(self, snapshots: Iterable[SourceSnapshot], ingested_at: datetime | None = None) -> IngestionResult:
        now = (ingested_at or datetime.now(tz=timezone.utc)).astimezone(timezone.utc)
        accepted_count = 0
        rejected: list[RejectedRecord] = []

        for snapshot in snapshots:
            normalized, rejection_reason = self._normalize_snapshot(snapshot, now)
            if rejection_reason:
                rejected_record = RejectedRecord(
                    source_name=snapshot.source_name,
                    event_id=snapshot.event.event_id,
                    market_id=snapshot.market.market_id,
                    reason=rejection_reason,
                )
                rejected.append(rejected_record)
                self._logger.info(
                    "ingestion_rejected source_name=%s event_id=%s market_id=%s reason=%s",
                    rejected_record.source_name,
                    rejected_record.event_id,
                    rejected_record.market_id,
                    rejected_record.reason,
                )
                continue

            accepted_count += 1
            self._logger.info(
                "ingestion_accepted source_name=%s source_role=%s event_id=%s market_id=%s dry_run=%s",
                normalized.source_name,
                normalized.source_role,
                normalized.event.event_id,
                normalized.market.market_id,
                self._dry_run,
            )
            if not self._dry_run:
                if self._repository is None:
                    raise ValueError("repository is required when dry_run is false")
                self._repository.write_snapshot(normalized)

        self._logger.info(
            "ingestion_run_complete accepted_count=%s rejected_count=%s dry_run=%s",
            accepted_count,
            len(rejected),
            self._dry_run,
        )

        return IngestionResult(
            accepted_count=accepted_count,
            rejected_count=len(rejected),
            rejected_records=tuple(rejected),
        )

    def _normalize_snapshot(
        self,
        snapshot: SourceSnapshot,
        ingested_at: datetime,
    ) -> tuple[NormalizedSnapshot, None] | tuple[None, str]:
        if snapshot.source_name not in self._config.approved_sources:
            return None, "source_not_approved"

        source_role = self._resolve_source_role(snapshot.source_name)
        if source_role is None:
            return None, "source_role_not_resolved"

        if snapshot.event.sport != "tennis":
            return None, "event_sport_not_tennis"

        if snapshot.market.market_type != "match_winner":
            return None, "market_type_not_match_winner"

        is_missing = snapshot.odds.is_missing or snapshot.odds.decimal_odds is None
        is_suspended = snapshot.odds.is_suspended
        is_uncertain = snapshot.market.is_uncertain or snapshot.odds.is_uncertain

        snapshot_age_seconds = (ingested_at - snapshot.snapshot_time_utc).total_seconds()
        is_stale = snapshot_age_seconds > self._config.stale_snapshot_max_age_seconds

        if is_missing:
            return None, "market_missing"
        if is_stale:
            return None, "market_stale"
        if is_suspended:
            return None, "market_suspended"
        if is_uncertain:
            return None, "market_uncertain"

        decimal_odds = snapshot.odds.decimal_odds
        if decimal_odds is None or decimal_odds <= 1:
            return None, "decimal_odds_invalid"

        implied_probability = 1 / decimal_odds

        unique_input = (
            f"{snapshot.event.event_id}|{snapshot.market.market_id}|{snapshot.source_name}|"
            f"{snapshot.snapshot_time_utc.isoformat()}|{decimal_odds}"
        )
        odds_snapshot_id = hashlib.sha256(unique_input.encode("utf-8")).hexdigest()

        return (
            NormalizedSnapshot(
                odds_snapshot_id=odds_snapshot_id,
                event=snapshot.event,
                participants=snapshot.participants,
                market=snapshot.market,
                source_name=snapshot.source_name,
                source_role=source_role,
                decimal_odds=decimal_odds,
                implied_probability=implied_probability,
                snapshot_time_utc=snapshot.snapshot_time_utc,
                is_suspended=is_suspended,
                is_stale=is_stale,
                is_missing=is_missing,
                is_uncertain=is_uncertain,
                ingested_at=ingested_at,
            ),
            None,
        )

    def _resolve_source_role(self, source_name: str) -> str | None:
        leader_source = self._resolve_leader_source()
        if source_name == leader_source:
            return "leader"
        if source_name in self._config.follower_sources:
            return "follower"
        return None

    def _resolve_leader_source(self) -> str:
        for candidate in self._config.leader_sources_priority:
            if candidate in self._config.approved_sources:
                return candidate
        raise ValueError("no leader source can be resolved from approved_sources")
