from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timezone

from src.detection.line_movement import (
    LeaderMovementConfig,
    detect_leader_movement_events,
    fetch_snapshots_from_db,
)


class LineMovementDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = LeaderMovementConfig(
            leader_move_threshold_percent=0.08,
            leader_move_window_minutes=30,
            stale_snapshot_max_age_seconds=1800,
            fallback_leader_source="Fallback Leader",
        )
        self.as_of_utc = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)

    def test_detects_event_when_threshold_is_met(self) -> None:
        snapshots = [
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Betfair exchange",
                "source_role": "leader",
                "decimal_odds": 2.00,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 40, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": False,
            },
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Betfair exchange",
                "source_role": "leader",
                "decimal_odds": 1.80,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 55, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": False,
            },
        ]

        events = detect_leader_movement_events(snapshots, self.config, self.as_of_utc, dry_run=True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].leader_source_name, "Betfair exchange")
        self.assertAlmostEqual(events[0].odds_move_percent, 0.1)

    def test_ignores_uncertain_or_suspended_or_stale_or_missing(self) -> None:
        snapshots = [
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Betfair exchange",
                "source_role": "leader",
                "decimal_odds": 2.00,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 40, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": True,
            },
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Betfair exchange",
                "source_role": "leader",
                "decimal_odds": 1.80,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 55, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": False,
            },
        ]

        events = detect_leader_movement_events(snapshots, self.config, self.as_of_utc, dry_run=True)
        self.assertEqual(events, [])

    def test_uses_source_priority_with_fallback(self) -> None:
        snapshots = [
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Pinnacle",
                "source_role": "leader",
                "decimal_odds": 2.00,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 40, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": False,
            },
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Pinnacle",
                "source_role": "leader",
                "decimal_odds": 1.90,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 55, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": False,
            },
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Fallback Leader",
                "source_role": "leader",
                "decimal_odds": 2.20,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 42, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": False,
            },
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Fallback Leader",
                "source_role": "leader",
                "decimal_odds": 1.50,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 58, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": False,
            },
        ]

        events = detect_leader_movement_events(snapshots, self.config, self.as_of_utc, dry_run=True)
        self.assertEqual(len(events), 0)

    def test_fetch_snapshots_from_db_reads_approved_schema(self) -> None:
        connection = sqlite3.connect(":memory:")
        cur = connection.cursor()
        cur.executescript(
            """
            CREATE TABLE events (
                event_id TEXT PRIMARY KEY,
                sport TEXT,
                tournament_name TEXT,
                league_name TEXT,
                start_time_utc TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE markets (
                market_id TEXT PRIMARY KEY,
                event_id TEXT,
                market_type TEXT,
                selection_participant_id TEXT,
                market_status TEXT,
                is_uncertain BOOLEAN,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE odds_snapshots (
                odds_snapshot_id TEXT PRIMARY KEY,
                event_id TEXT,
                market_id TEXT,
                source_name TEXT,
                source_role TEXT,
                decimal_odds REAL,
                implied_probability REAL,
                snapshot_time_utc TEXT,
                is_suspended BOOLEAN,
                is_stale BOOLEAN,
                is_missing BOOLEAN,
                is_uncertain BOOLEAN,
                ingested_at TEXT
            );
            """
        )
        cur.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("e1", "tennis", "t", "l", "2026-04-25T14:00:00+00:00", "open", "x", "x"),
        )
        cur.execute(
            "INSERT INTO markets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("m1", "e1", "match_winner", "p1", "open", 0, "x", "x"),
        )
        cur.execute(
            "INSERT INTO odds_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "s1",
                "e1",
                "m1",
                "Betfair exchange",
                "leader",
                2.0,
                0.5,
                "2026-04-25T11:55:00+00:00",
                0,
                0,
                0,
                0,
                "2026-04-25T11:55:10+00:00",
            ),
        )
        connection.commit()

        snapshots = fetch_snapshots_from_db(connection)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["event_id"], "e1")

        connection.close()


if __name__ == "__main__":
    unittest.main()
