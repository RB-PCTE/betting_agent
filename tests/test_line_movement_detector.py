from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timezone

from src.detection.line_movement import (
    LeaderMovementConfig,
    detect_leader_movement_events,
    detect_open_signals,
    fetch_snapshots_from_db,
    persist_detected_signals,
)


class LineMovementDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = LeaderMovementConfig(
            leader_move_threshold_percent=0.08,
            leader_move_window_minutes=30,
            stale_snapshot_max_age_seconds=1800,
            fallback_leader_source="Fallback Leader",
            follower_edge_threshold_percent=0.08,
            minutes_to_start_block=60,
            allow_within_60_minutes=False,
            follower_sources=("Book A",),
        )
        self.as_of_utc = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)

    def _leader_pair(self, old_odds: float, new_odds: float) -> list[dict]:
        return [
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Betfair exchange",
                "source_role": "leader",
                "decimal_odds": old_odds,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 40, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": False,
                "start_time_utc": datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
            },
            {
                "event_id": "e1",
                "market_id": "m1",
                "selection_participant_id": "p1",
                "source_name": "Betfair exchange",
                "source_role": "leader",
                "decimal_odds": new_odds,
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 55, tzinfo=timezone.utc),
                "is_suspended": False,
                "is_stale": False,
                "is_missing": False,
                "is_uncertain": False,
                "sport": "tennis",
                "market_type": "match_winner",
                "market_is_uncertain": False,
                "start_time_utc": datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
            },
        ]

    def _follower_snapshot(self, odds: float, start_time: datetime | None = None) -> dict:
        return {
            "event_id": "e1",
            "market_id": "m1",
            "selection_participant_id": "p1",
            "source_name": "Book A",
            "source_role": "follower",
            "decimal_odds": odds,
            "snapshot_time_utc": datetime(2026, 4, 25, 11, 57, tzinfo=timezone.utc),
            "is_suspended": False,
            "is_stale": False,
            "is_missing": False,
            "is_uncertain": False,
            "sport": "tennis",
            "market_type": "match_winner",
            "market_is_uncertain": False,
            "start_time_utc": start_time or datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        }

    def test_detects_event_when_threshold_is_met(self) -> None:
        snapshots = self._leader_pair(old_odds=2.00, new_odds=1.80)
        events = detect_leader_movement_events(snapshots, self.config, self.as_of_utc, dry_run=True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].leader_source_name, "Betfair exchange")
        self.assertAlmostEqual(events[0].odds_move_percent, 0.1)

    def test_leader_move_exact_threshold_passes(self) -> None:
        snapshots = self._leader_pair(old_odds=2.50, new_odds=2.30)
        events = detect_leader_movement_events(snapshots, self.config, self.as_of_utc, dry_run=True)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].odds_move_percent, 0.08)

    def test_ignores_uncertain_or_suspended_or_stale_or_missing(self) -> None:
        snapshots = self._leader_pair(old_odds=2.00, new_odds=1.80)
        snapshots[0]["market_is_uncertain"] = True
        events = detect_leader_movement_events(snapshots, self.config, self.as_of_utc, dry_run=True)
        self.assertEqual(events, [])

    def test_uses_source_priority_with_fallback(self) -> None:
        snapshots = [
            {
                **self._leader_pair(old_odds=2.00, new_odds=1.90)[0],
                "source_name": "Pinnacle",
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 40, tzinfo=timezone.utc),
                "decimal_odds": 2.00,
            },
            {
                **self._leader_pair(old_odds=2.00, new_odds=1.90)[1],
                "source_name": "Pinnacle",
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 55, tzinfo=timezone.utc),
                "decimal_odds": 1.90,
            },
            {
                **self._leader_pair(old_odds=2.20, new_odds=1.50)[0],
                "source_name": "Fallback Leader",
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 42, tzinfo=timezone.utc),
                "decimal_odds": 2.20,
            },
            {
                **self._leader_pair(old_odds=2.20, new_odds=1.50)[1],
                "source_name": "Fallback Leader",
                "snapshot_time_utc": datetime(2026, 4, 25, 11, 58, tzinfo=timezone.utc),
                "decimal_odds": 1.50,
            },
        ]

        events = detect_leader_movement_events(snapshots, self.config, self.as_of_utc, dry_run=True)
        self.assertEqual(len(events), 0)

    def test_follower_edge_exact_threshold_passes(self) -> None:
        leader_snapshots = self._leader_pair(old_odds=2.50, new_odds=2.30)
        events = detect_leader_movement_events(leader_snapshots, self.config, self.as_of_utc, dry_run=True)
        snapshots = leader_snapshots + [self._follower_snapshot(odds=2.484)]

        signals = detect_open_signals(
            snapshots=snapshots,
            leader_movement_events=events,
            config=self.config,
            as_of_utc=self.as_of_utc,
        )

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].signal_status, "open")

    def test_follower_edge_below_threshold_fails(self) -> None:
        leader_snapshots = self._leader_pair(old_odds=2.00, new_odds=1.80)
        events = detect_leader_movement_events(leader_snapshots, self.config, self.as_of_utc, dry_run=True)
        snapshots = leader_snapshots + [self._follower_snapshot(odds=1.943)]

        signals = detect_open_signals(
            snapshots=snapshots,
            leader_movement_events=events,
            config=self.config,
            as_of_utc=self.as_of_utc,
        )

        self.assertEqual(signals, [])

    def test_match_start_gating_blocks_when_not_allowed(self) -> None:
        leader_snapshots = self._leader_pair(old_odds=2.00, new_odds=1.80)
        events = detect_leader_movement_events(leader_snapshots, self.config, self.as_of_utc, dry_run=True)
        near_start = datetime(2026, 4, 25, 12, 45, tzinfo=timezone.utc)
        snapshots = leader_snapshots + [self._follower_snapshot(odds=2.00, start_time=near_start)]

        signals = detect_open_signals(
            snapshots=snapshots,
            leader_movement_events=events,
            config=self.config,
            as_of_utc=self.as_of_utc,
        )

        self.assertEqual(signals, [])

    def test_match_start_gating_allows_when_configured(self) -> None:
        allow_config = LeaderMovementConfig(
            leader_move_threshold_percent=0.08,
            leader_move_window_minutes=30,
            stale_snapshot_max_age_seconds=1800,
            fallback_leader_source="Fallback Leader",
            follower_edge_threshold_percent=0.08,
            minutes_to_start_block=60,
            allow_within_60_minutes=True,
            follower_sources=("Book A",),
        )
        leader_snapshots = self._leader_pair(old_odds=2.00, new_odds=1.80)
        events = detect_leader_movement_events(leader_snapshots, allow_config, self.as_of_utc, dry_run=True)
        near_start = datetime(2026, 4, 25, 12, 45, tzinfo=timezone.utc)
        snapshots = leader_snapshots + [self._follower_snapshot(odds=2.00, start_time=near_start)]

        signals = detect_open_signals(
            snapshots=snapshots,
            leader_movement_events=events,
            config=allow_config,
            as_of_utc=self.as_of_utc,
        )

        self.assertEqual(len(signals), 1)

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

    def test_persist_detected_signals_writes_only_in_write_mode(self) -> None:
        connection = sqlite3.connect(":memory:")
        cur = connection.cursor()
        cur.executescript(
            """
            CREATE TABLE detected_signals (
                signal_id TEXT PRIMARY KEY,
                event_id TEXT,
                market_id TEXT,
                selection_participant_id TEXT,
                leader_source_name TEXT,
                follower_source_name TEXT,
                leader_old_odds REAL,
                leader_new_odds REAL,
                odds_move_percent REAL,
                follower_odds REAL,
                follower_edge_percent REAL,
                leader_move_window_minutes INTEGER,
                minutes_to_start_at_signal INTEGER,
                signal_status TEXT,
                signal_reason TEXT,
                detected_at TEXT
            );
            """
        )

        leader_snapshots = self._leader_pair(old_odds=2.00, new_odds=1.80)
        events = detect_leader_movement_events(leader_snapshots, self.config, self.as_of_utc, dry_run=True)
        snapshots = leader_snapshots + [self._follower_snapshot(odds=2.00)]
        signals = detect_open_signals(snapshots, events, self.config, self.as_of_utc)

        self.assertEqual(len(signals), 1)
        self.assertEqual(persist_detected_signals(connection, []), 0)
        self.assertEqual(persist_detected_signals(connection, signals), 1)

        cur.execute("SELECT signal_status, signal_reason FROM detected_signals")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "open")
        self.assertIn("follower_edge", rows[0][1])
        connection.close()


if __name__ == "__main__":
    unittest.main()
