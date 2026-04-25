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
    fetch_snapshots_from_db,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step 4 leader-source line movement detection (dry-run capable)."
    )
    parser.add_argument("--db-path", required=True, help="Path to SQLite database file.")
    parser.add_argument(
        "--fallback-leader-source",
        required=True,
        help="Configurable fallback leader source from PROJECT_RULES.md Section 3.1.",
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
        "--as-of-utc",
        default=None,
        help="ISO UTC datetime for detection boundary. Defaults to now in UTC.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run mode: evaluate and print events only (no writes).",
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
    )

    connection = sqlite3.connect(args.db_path)
    try:
        snapshots = fetch_snapshots_from_db(connection)
    finally:
        connection.close()

    events = detect_leader_movement_events(
        snapshots=snapshots,
        config=config,
        as_of_utc=as_of_utc,
        dry_run=args.dry_run,
    )

    output = {
        "dry_run": args.dry_run,
        "as_of_utc": as_of_utc.isoformat(),
        "leader_movement_events": [event.to_dict() for event in events],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
