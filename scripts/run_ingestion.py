#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import load_project_config
from src.ingestion import IngestionRepository, OddsIngestionService, load_source_snapshots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run odds ingestion foundation pipeline")
    parser.add_argument("--config", required=True, help="Path to project config JSON")
    parser.add_argument("--input", required=True, help="Path to normalized source snapshots JSON")
    parser.add_argument("--database", help="Database path/DSN for writing snapshots")
    parser.add_argument("--dry-run", action="store_true", help="Validate and normalize without writing to database")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    config = load_project_config(args.config)
    snapshots = load_source_snapshots(args.input)

    repository = None
    if not args.dry_run:
        if not args.database:
            raise ValueError("--database is required when --dry-run is not set")
        connection = sqlite3.connect(args.database)
        repository = IngestionRepository(connection)

    service = OddsIngestionService(config=config, repository=repository, dry_run=args.dry_run)
    result = service.ingest(snapshots=snapshots, ingested_at=datetime.now(tz=timezone.utc))

    logging.info(
        "ingestion_summary accepted_count=%s rejected_count=%s",
        result.accepted_count,
        result.rejected_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
