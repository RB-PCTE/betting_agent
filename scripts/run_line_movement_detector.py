#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.detection.line_movement import (
    LeaderMovementConfig,
    detect_leader_movement_events,
    detect_open_signals,
    fetch_snapshots_from_db,
    persist_detected_signals,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step 4/5 detection (leader movement + follower stale-price comparison)."
    )
    parser.add_argument("--db-path", required=True, help="Path to SQLite database file.")
    parser.add_argument(
        "--fallback-leader-source",
        required=True,
        help="Configurable fallback leader source from PROJECT_RULES.md Section 3.1.",
    )
    parser.add_argument(
        "--follower-source",
        action="append",
        dest="follower_sources",
        default=[],
        help="Follower source name to evaluate (repeat per source).",
    )
    parser.add_argument(
        "--leader-move-window-minutes",
        required=True,
        type=int,
        help="Configurable LEADER_MOVE_WINDOW_MINUTES.",
    )
    parser.add_argument(
        "--stale-snapshot-max-age-seconds",
        required=True,
        type=int,
        help="Configurable STALE_SNAPSHOT_MAX_AGE_SECONDS.",
    )
    parser.add_argument(
        "--leader-move-threshold-percent",
        type=float,
        default=0.08,
        help="LEADER_MOVE_THRESHOLD_PERCENT (default 0.08).",
    )
    parser.add_argument(
        "--follower-edge-threshold-percent",
        type=float,
        default=0.08,
        help="FOLLOWER_EDGE_THRESHOLD_PERCENT (default 0.08).",
    )
    parser.add_argument(
        "--minutes-to-start-block",
        type=int,
        default=60,
        help="MINUTES_TO_START_BLOCK (default 60).",
    )
    parser.add_argument(
        "--allow-within-60-minutes",
        action="store_true",
        help="Set ALLOW_WITHIN_60_MINUTES=true.",
    )
    parser.add_argument(
        "--as-of-utc",
        default=None,
        help="ISO UTC datetime for detection boundary. Defaults to now in UTC.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run mode: evaluate and print events/signals only (no writes).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    as_of_utc = (
        datetime.now(timezone.utc)
        if args.as_of_utc is None
        else datetime.fromisoformat(args.as_of_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    )

    config = LeaderMovementConfig(
        leader_move_threshold_percent=args.leader_move_threshold_percent,
        leader_move_window_minutes=args.leader_move_window_minutes,
        stale_snapshot_max_age_seconds=args.stale_snapshot_max_age_seconds,
        fallback_leader_source=args.fallback_leader_source,
        follower_edge_threshold_percent=args.follower_edge_threshold_percent,
        minutes_to_start_block=args.minutes_to_start_block,
        allow_within_60_minutes=args.allow_within_60_minutes,
        follower_sources=tuple(args.follower_sources),
    )

    connection = sqlite3.connect(args.db_path)
    try:
        snapshots = fetch_snapshots_from_db(connection)

        events = detect_leader_movement_events(
            snapshots=snapshots,
            config=config,
            as_of_utc=as_of_utc,
            dry_run=True,
        )

        open_signals = detect_open_signals(
            snapshots=snapshots,
            leader_movement_events=events,
            config=config,
            as_of_utc=as_of_utc,
        )

        inserted_count = 0
        if not args.dry_run:
            inserted_count = persist_detected_signals(connection, open_signals)
    finally:
        connection.close()

    output = {
        "dry_run": args.dry_run,
        "as_of_utc": as_of_utc.isoformat(),
        "leader_movement_events": [event.to_dict() for event in events],
        "eligible_open_signals": [signal.to_dict() for signal in open_signals],
        "inserted_signals_count": inserted_count,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
