from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class LeaderMovementConfig:
    """Configuration values defined by PROJECT_RULES.md for Step 4."""

    leader_move_threshold_percent: float
    leader_move_window_minutes: int
    stale_snapshot_max_age_seconds: int
    fallback_leader_source: str

    @property
    def leader_sources_priority(self) -> tuple[str, str, str]:
        return ("Betfair exchange", "Pinnacle", self.fallback_leader_source)


@dataclass(frozen=True)
class LeaderMovementEvent:
    """Testable output record for detected leader movement."""

    event_id: str
    market_id: str
    selection_participant_id: str
    leader_source_name: str
    leader_old_odds: float
    leader_new_odds: float
    odds_move_percent: float
    leader_move_window_minutes: int
    detected_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "market_id": self.market_id,
            "selection_participant_id": self.selection_participant_id,
            "leader_source_name": self.leader_source_name,
            "leader_old_odds": self.leader_old_odds,
            "leader_new_odds": self.leader_new_odds,
            "odds_move_percent": self.odds_move_percent,
            "leader_move_window_minutes": self.leader_move_window_minutes,
            "detected_at": self.detected_at.isoformat(),
        }


def _parse_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_snapshot_usable(
    snapshot: dict[str, Any],
    as_of_utc: datetime,
    stale_snapshot_max_age_seconds: int,
) -> bool:
    if snapshot["sport"] != "tennis":
        return False
    if snapshot["market_type"] != "match_winner":
        return False
    if bool(snapshot["market_is_uncertain"]):
        return False
    if bool(snapshot["is_suspended"]):
        return False
    if bool(snapshot["is_stale"]):
        return False
    if bool(snapshot["is_missing"]):
        return False
    if bool(snapshot["is_uncertain"]):
        return False

    age_seconds = (as_of_utc - snapshot["snapshot_time_utc"]).total_seconds()
    if age_seconds < 0:
        return False
    if age_seconds > stale_snapshot_max_age_seconds:
        return False
    return True


def fetch_snapshots_from_db(connection: Any) -> list[dict[str, Any]]:
    """
    Read odds snapshots from the approved schema for Step 4 foundation logic.
    """

    query = """
    SELECT
        os.event_id,
        os.market_id,
        m.selection_participant_id,
        os.source_name,
        os.source_role,
        os.decimal_odds,
        os.snapshot_time_utc,
        os.is_suspended,
        os.is_stale,
        os.is_missing,
        os.is_uncertain,
        e.sport,
        m.market_type,
        m.is_uncertain AS market_is_uncertain
    FROM odds_snapshots AS os
    JOIN events AS e ON e.event_id = os.event_id
    JOIN markets AS m ON m.market_id = os.market_id
    WHERE os.source_role = 'leader'
      AND e.sport = 'tennis'
      AND m.market_type = 'match_winner'
    """

    cursor = connection.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [column[0] for column in cursor.description]

    snapshots: list[dict[str, Any]] = []
    for row in rows:
        snap = dict(zip(columns, row))
        snap["snapshot_time_utc"] = _parse_utc(snap["snapshot_time_utc"])
        snap["decimal_odds"] = float(snap["decimal_odds"])
        snapshots.append(snap)
    return snapshots


def detect_leader_movement_events(
    snapshots: Iterable[dict[str, Any]],
    config: LeaderMovementConfig,
    as_of_utc: datetime,
    dry_run: bool = True,
) -> list[LeaderMovementEvent]:
    """
    Detect leader-source line movement events for tennis match-winner markets.
    """

    if as_of_utc.tzinfo is None:
        as_of_utc = as_of_utc.replace(tzinfo=timezone.utc)
    else:
        as_of_utc = as_of_utc.astimezone(timezone.utc)

    window_start = as_of_utc - timedelta(minutes=config.leader_move_window_minutes)
    filtered: list[dict[str, Any]] = []

    for snapshot in snapshots:
        copied = dict(snapshot)
        copied["snapshot_time_utc"] = _parse_utc(copied["snapshot_time_utc"])
        if copied["snapshot_time_utc"] < window_start:
            continue
        if copied["source_name"] not in config.leader_sources_priority:
            continue
        if not _is_snapshot_usable(
            copied,
            as_of_utc=as_of_utc,
            stale_snapshot_max_age_seconds=config.stale_snapshot_max_age_seconds,
        ):
            continue
        filtered.append(copied)

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for snapshot in filtered:
        key = (
            snapshot["event_id"],
            snapshot["market_id"],
            snapshot["selection_participant_id"],
        )
        grouped.setdefault(key, []).append(snapshot)

    events: list[LeaderMovementEvent] = []

    for (event_id, market_id, selection_participant_id), group_snapshots in grouped.items():
        chosen_source_snapshots: list[dict[str, Any]] | None = None

        for source_name in config.leader_sources_priority:
            source_rows = [row for row in group_snapshots if row["source_name"] == source_name]
            if source_rows:
                chosen_source_snapshots = sorted(
                    source_rows,
                    key=lambda row: row["snapshot_time_utc"],
                )
                break

        if not chosen_source_snapshots or len(chosen_source_snapshots) < 2:
            continue

        oldest = chosen_source_snapshots[0]
        newest = chosen_source_snapshots[-1]

        old_odds = float(oldest["decimal_odds"])
        new_odds = float(newest["decimal_odds"])
        odds_move_percent = (old_odds - new_odds) / old_odds

        if odds_move_percent < config.leader_move_threshold_percent:
            continue

        events.append(
            LeaderMovementEvent(
                event_id=event_id,
                market_id=market_id,
                selection_participant_id=selection_participant_id,
                leader_source_name=str(newest["source_name"]),
                leader_old_odds=old_odds,
                leader_new_odds=new_odds,
                odds_move_percent=odds_move_percent,
                leader_move_window_minutes=config.leader_move_window_minutes,
                detected_at=as_of_utc,
            )
        )

    if dry_run:
        return events

    return events
