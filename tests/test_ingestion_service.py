from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from src.config import ProjectConfig
from src.ingestion.models import EventRecord, MarketRecord, OddsRecord, ParticipantRecord, SourceSnapshot
from src.ingestion.service import OddsIngestionService


class FakeRepository:
    def __init__(self) -> None:
        self.writes = 0

    def write_snapshot(self, normalized) -> None:
        self.writes += 1


class OddsIngestionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ProjectConfig(
            approved_sources=("betfair_exchange", "pinnacle", "book_a"),
            fallback_leader_source="pinnacle",
            follower_sources=("book_a",),
            stale_snapshot_max_age_seconds=120,
        )
        self.repository = FakeRepository()

    def _snapshot(self, **overrides) -> SourceSnapshot:
        now = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
        snapshot = SourceSnapshot(
            source_name="betfair_exchange",
            snapshot_time_utc=now,
            event=EventRecord(
                event_id="event-1",
                sport="tennis",
                tournament_name="Tournament",
                league_name="League",
                start_time_utc=now + timedelta(hours=2),
                status="scheduled",
            ),
            participants=(
                ParticipantRecord(
                    participant_id="participant-a",
                    event_id="event-1",
                    participant_name="Player A",
                    role="player_a",
                ),
                ParticipantRecord(
                    participant_id="participant-b",
                    event_id="event-1",
                    participant_name="Player B",
                    role="player_b",
                ),
            ),
            market=MarketRecord(
                market_id="market-1",
                event_id="event-1",
                market_type="match_winner",
                selection_participant_id="participant-a",
                market_status="active",
                is_uncertain=False,
            ),
            odds=OddsRecord(
                decimal_odds=2.1,
                is_suspended=False,
                is_missing=False,
                is_uncertain=False,
            ),
        )
        return SourceSnapshot(**{**snapshot.__dict__, **overrides})

    def test_ingest_accepts_valid_record(self) -> None:
        service = OddsIngestionService(config=self.config, repository=self.repository, dry_run=False)
        ingest_time = datetime(2026, 4, 25, 12, 1, tzinfo=timezone.utc)
        result = service.ingest([self._snapshot()], ingested_at=ingest_time)

        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.rejected_count, 0)
        self.assertEqual(self.repository.writes, 1)

    def test_ingest_rejects_stale_record(self) -> None:
        service = OddsIngestionService(config=self.config, repository=self.repository, dry_run=False)
        old_snapshot = self._snapshot(snapshot_time_utc=datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc))
        ingest_time = datetime(2026, 4, 25, 12, 1, tzinfo=timezone.utc)

        result = service.ingest([old_snapshot], ingested_at=ingest_time)

        self.assertEqual(result.accepted_count, 0)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.rejected_records[0].reason, "market_stale")
        self.assertEqual(self.repository.writes, 0)

    def test_ingest_dry_run_skips_database_writes(self) -> None:
        service = OddsIngestionService(config=self.config, repository=None, dry_run=True)
        ingest_time = datetime(2026, 4, 25, 12, 1, tzinfo=timezone.utc)

        result = service.ingest([self._snapshot()], ingested_at=ingest_time)

        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.rejected_count, 0)


if __name__ == "__main__":
    unittest.main()
