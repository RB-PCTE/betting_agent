from __future__ import annotations

import json
import tempfile
import unittest

from src.config import load_project_config


class ProjectConfigTests(unittest.TestCase):
    def test_load_project_config_requires_core_ingestion_values(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".json") as handle:
            json.dump(
                {
                    "approved_sources": ["betfair_exchange", "book_a"],
                    "fallback_leader_source": "book_a",
                    "follower_sources": ["book_a"],
                    "stale_snapshot_max_age_seconds": 30,
                },
                handle,
            )
            handle.flush()

            config = load_project_config(handle.name)

        self.assertEqual(config.leader_sources_priority, ("betfair_exchange", "pinnacle", "book_a"))


if __name__ == "__main__":
    unittest.main()
