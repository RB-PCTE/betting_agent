from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import uuid4


@dataclass(frozen=True)
class LeaderMovementConfig:
    """Configuration values defined by PROJECT_RULES.md for Step 4 and Phase 5/6."""

    leader_move_threshold_percent: float
    leader_move_window_minutes: int
    stale_snapshot_max_age_seconds: int
    fallback_leader_source: str
    follower_edge_threshold_percent: float = 0.08
    minutes_to_start_block: int = 60
    allow_within_60_minutes: bool = False
    follower_sources: tuple[str, ...] = ()

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


@dataclass(frozen=True)
class DetectedSignal:
    """Eligible follower-vs-leader stale-price signal for detected_signals persistence."""

    event_id: str
    market_id: str
    selection_participant_id: str
    leader_source_name: str
    follower_source_name: str
    leader_old_odds: float
    leader_new_odds: float
    odds_move_percent: float
    follower_odds: float
    follower_edge_percent: float
    leader_move_window_minutes: int
    minutes_to_start_at_signal: int
    signal_status: str
    signal_reason: str
    detected_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "market_id": self.market_id,
            "selection_participant_id": self.selection_participant_id,
            "leader_source_name": self.leader_source_name,
            "follower_source_name": self.follower_source_name,
            "leader_old_odds": self.leader_old_odds,
            "leader_new_odds": self.leader_new_odds,
            "odds_move_percent": self.odds_move_percent,
            "follower_odds": self.follower_odds,
            "follower_edge_percent": self.follower_edge_percent,
            "leader_move_window_minutes": self.leader_move_window_minutes,
            "minutes_to_start_at_signal": self.minutes_to_start_at_signal,
            "signal_status": self.signal_status,
            "signal_reason": self.signal_reason,
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
    Read odds snapshots from the approved schema for Step 4 and Phase 5/6 logic.
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
        m.is_uncertain AS market_is_uncertain,
        e.start_time_utc
    FROM odds_snapshots AS os
    JOIN events AS e ON e.event_id = os.event_id
    JOIN markets AS m ON m.market_id = os.market_id
    WHERE e.sport = 'tennis'
      AND m.market_type = 'match_winner'
      AND os.source_role IN ('leader', 'follower')
    """

    cursor = connection.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [column[0] for column in cursor.description]

    snapshots: list[dict[str, Any]] = []
    for row in rows:
        snap = dict(zip(columns, row))
        snap["snapshot_time_utc"] = _parse_utc(snap["snapshot_time_utc"])
        snap["start_time_utc"] = _parse_utc(snap["start_time_utc"])
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
        if copied["source_role"] != "leader":
            continue
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


def detect_open_signals(
    snapshots: Iterable[dict[str, Any]],
    leader_movement_events: Iterable[LeaderMovementEvent],
    config: LeaderMovementConfig,
    as_of_utc: datetime,
) -> list[DetectedSignal]:
    if as_of_utc.tzinfo is None:
        as_of_utc = as_of_utc.replace(tzinfo=timezone.utc)
    else:
        as_of_utc = as_of_utc.astimezone(timezone.utc)

    follower_sources = set(config.follower_sources)
    usable_followers: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    event_start_times: dict[tuple[str, str, str], datetime] = {}

    for snapshot in snapshots:
        copied = dict(snapshot)
        copied["snapshot_time_utc"] = _parse_utc(copied["snapshot_time_utc"])
        copied["start_time_utc"] = _parse_utc(copied["start_time_utc"])

        if copied["source_role"] != "follower":
            continue
        if follower_sources and copied["source_name"] not in follower_sources:
            continue
        if not _is_snapshot_usable(
            copied,
            as_of_utc=as_of_utc,
            stale_snapshot_max_age_seconds=config.stale_snapshot_max_age_seconds,
        ):
            continue

        base_key = (
            copied["event_id"],
            copied["market_id"],
            copied["selection_participant_id"],
        )
        event_start_times[base_key] = copied["start_time_utc"]

        key = (*base_key, copied["source_name"])
        usable_followers.setdefault(key, []).append(copied)

    signals: list[DetectedSignal] = []

    for movement in leader_movement_events:
        base_key = (
            movement.event_id,
            movement.market_id,
            movement.selection_participant_id,
        )
        start_time_utc = event_start_times.get(base_key)
        if start_time_utc is None:
            continue

        minutes_to_start = int((start_time_utc - as_of_utc).total_seconds() // 60)
        if not config.allow_within_60_minutes and minutes_to_start < config.minutes_to_start_block:
            continue

        for follower_source in config.follower_sources:
            follower_key = (*base_key, follower_source)
            follower_rows = usable_followers.get(follower_key, [])
            if not follower_rows:
                continue

            newest_follower = max(follower_rows, key=lambda row: row["snapshot_time_utc"])
            follower_odds = float(newest_follower["decimal_odds"])
            follower_edge_percent = (follower_odds - movement.leader_new_odds) / movement.leader_new_odds

            if follower_edge_percent < config.follower_edge_threshold_percent:
                continue

            signal_reason = (
                "leader_move_and_follower_edge_threshold_met; "
                f"leader_move={movement.odds_move_percent:.6f}; "
                f"follower_edge={follower_edge_percent:.6f}"
            )

            signals.append(
                DetectedSignal(
                    event_id=movement.event_id,
                    market_id=movement.market_id,
                    selection_participant_id=movement.selection_participant_id,
                    leader_source_name=movement.leader_source_name,
                    follower_source_name=follower_source,
                    leader_old_odds=movement.leader_old_odds,
                    leader_new_odds=movement.leader_new_odds,
                    odds_move_percent=movement.odds_move_percent,
                    follower_odds=follower_odds,
                    follower_edge_percent=follower_edge_percent,
                    leader_move_window_minutes=movement.leader_move_window_minutes,
                    minutes_to_start_at_signal=minutes_to_start,
                    signal_status="open",
                    signal_reason=signal_reason,
                    detected_at=as_of_utc,
                )
            )

    return signals


def persist_detected_signals(connection: Any, signals: Iterable[DetectedSignal]) -> int:
    rows = list(signals)
    if not rows:
        return 0

    query = """
    INSERT INTO detected_signals (
        signal_id,
        event_id,
        market_id,
        selection_participant_id,
        leader_source_name,
        follower_source_name,
        leader_old_odds,
        leader_new_odds,
        odds_move_percent,
        follower_odds,
        follower_edge_percent,
        leader_move_window_minutes,
        minutes_to_start_at_signal,
        signal_status,
        signal_reason,
        detected_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    cursor = connection.cursor()
    cursor.executemany(
        query,
        [
            (
                str(uuid4()),
                signal.event_id,
                signal.market_id,
                signal.selection_participant_id,
                signal.leader_source_name,
                signal.follower_source_name,
                signal.leader_old_odds,
                signal.leader_new_odds,
                signal.odds_move_percent,
                signal.follower_odds,
                signal.follower_edge_percent,
                signal.leader_move_window_minutes,
                signal.minutes_to_start_at_signal,
                signal.signal_status,
                signal.signal_reason,
                signal.detected_at.isoformat(),
            )
            for signal in rows
        ],
    )
    connection.commit()
    return len(rows)
