from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class ProjectConfig:
    approved_sources: tuple[str, ...]
    fallback_leader_source: str
    follower_sources: tuple[str, ...]
    stale_snapshot_max_age_seconds: int

    @property
    def leader_sources_priority(self) -> tuple[str, ...]:
        return (
            "betfair_exchange",
            "pinnacle",
            self.fallback_leader_source,
        )


def load_project_config(path: str | Path) -> ProjectConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    approved_sources = tuple(raw.get("approved_sources", []))
    fallback_leader_source = raw.get("fallback_leader_source", "")
    follower_sources = tuple(raw.get("follower_sources", []))
    stale_snapshot_max_age_seconds = raw.get("stale_snapshot_max_age_seconds")

    if not approved_sources:
        raise ValueError("project config must define approved_sources")
    if not fallback_leader_source:
        raise ValueError("project config must define fallback_leader_source")
    if fallback_leader_source not in approved_sources:
        raise ValueError("fallback_leader_source must be included in approved_sources")
    if not follower_sources:
        raise ValueError("project config must define follower_sources")
    if any(source not in approved_sources for source in follower_sources):
        raise ValueError("all follower_sources must be included in approved_sources")
    if not isinstance(stale_snapshot_max_age_seconds, int) or stale_snapshot_max_age_seconds < 0:
        raise ValueError("project config must define stale_snapshot_max_age_seconds as integer >= 0")

    return ProjectConfig(
        approved_sources=approved_sources,
        fallback_leader_source=fallback_leader_source,
        follower_sources=follower_sources,
        stale_snapshot_max_age_seconds=stale_snapshot_max_age_seconds,
    )
