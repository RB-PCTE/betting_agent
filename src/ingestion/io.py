from __future__ import annotations

import json
from pathlib import Path

from .models import EventRecord, MarketRecord, OddsRecord, ParticipantRecord, SourceSnapshot, parse_utc


def load_source_snapshots(path: str | Path) -> list[SourceSnapshot]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    snapshots: list[SourceSnapshot] = []

    for item in payload:
        event = EventRecord(
            event_id=item["event"]["event_id"],
            sport=item["event"]["sport"],
            tournament_name=item["event"]["tournament_name"],
            league_name=item["event"]["league_name"],
            start_time_utc=parse_utc(item["event"]["start_time_utc"]),
            status=item["event"]["status"],
        )
        participants = tuple(
            ParticipantRecord(
                participant_id=participant["participant_id"],
                event_id=participant["event_id"],
                participant_name=participant["participant_name"],
                role=participant["role"],
            )
            for participant in item["participants"]
        )
        market = MarketRecord(
            market_id=item["market"]["market_id"],
            event_id=item["market"]["event_id"],
            market_type=item["market"]["market_type"],
            selection_participant_id=item["market"]["selection_participant_id"],
            market_status=item["market"]["market_status"],
            is_uncertain=item["market"]["is_uncertain"],
        )
        odds = OddsRecord(
            decimal_odds=item["odds"]["decimal_odds"],
            is_suspended=item["odds"]["is_suspended"],
            is_missing=item["odds"]["is_missing"],
            is_uncertain=item["odds"]["is_uncertain"],
        )

        snapshots.append(
            SourceSnapshot(
                source_name=item["source_name"],
                snapshot_time_utc=parse_utc(item["snapshot_time_utc"]),
                event=event,
                participants=participants,
                market=market,
                odds=odds,
            )
        )

    return snapshots
