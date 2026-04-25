# Implementation Plan

This implementation plan follows `PROJECT_RULES.md` and is organized into the required phases.

## Phase 1: Database schema
- Define schema artifacts for the required tables and fields:
  - `events`
  - `participants`
  - `markets`
  - `odds_snapshots`
  - `detected_signals`
  - `bet_candidates`
  - `manual_bets`
  - `closing_lines`
  - `results`
- Enforce naming conventions:
  - `snake_case` table and field names
  - `<entity>_id` text UUID IDs
  - UTC timestamps with `_at` naming for instants
- Preserve field names and relationships exactly as specified.

## Phase 2: Odds ingestion
- Implement ingestion pipeline boundaries for approved/allowed odds sources only.
- Resolve leader source by priority:
  1. Betfair exchange (if available)
  2. Pinnacle (if available)
  3. Configurable fallback leader source
- Support configurable follower bookmaker list.
- Exclude suspended, stale, missing, or uncertain markets per source policy constraints.

## Phase 3: Odds snapshot storage
- Store snapshots into `odds_snapshots` with required status flags.
- Store decimal odds only.
- Compute and store `implied_probability` using:
  - `implied_probability = 1 / decimal_odds`

## Phase 4: Line movement detection
- Status: Implemented (foundation only: leader-source movement detection, dry-run output, unit tests).
- Detect leader movement within `LEADER_MOVE_WINDOW_MINUTES`.
- Compute movement metric using:
  - `odds_move_percent = (old_odds - new_odds) / old_odds`
- Apply threshold:
  - `odds_move_percent >= LEADER_MOVE_THRESHOLD_PERCENT`

## Phase 5: Follower-vs-leader comparison
- Compare follower stale prices to leader new odds.
- Compute edge metric using:
  - `follower_edge_percent = (follower_odds - leader_odds) / leader_odds`
- Apply threshold:
  - `follower_edge_percent >= FOLLOWER_EDGE_THRESHOLD_PERCENT`

## Phase 6: Signal logging
- Log only eligible signals in `detected_signals` when all eligibility rules are true.
- Enforce match start gating with:
  - `MINUTES_TO_START_BLOCK`
  - `ALLOW_WITHIN_60_MINUTES`
- Exclude invalid, stale, uncertain, suspended, or missing data.

## Phase 7: Closing line tracking
- Capture and store closing odds in `closing_lines` with required identifiers and timestamp.

## Phase 8: CLV review
- Compute candidate CLV:
  - `candidate_clv_percent = (candidate_odds - closing_odds) / closing_odds`
- Compute manual bet CLV:
  - `manual_bet_clv_percent = (placed_odds - closing_odds) / closing_odds`
- Interpret positive CLV when recorded odds are better than closing odds; for decimal odds on selected player, better means higher odds.

## Phase 9: Dashboard/reporting
- Implement minimum required views:
  - Current opportunities
  - Signal history
  - CLV review
  - Profit/loss review
  - Source performance
  - League/tournament performance

## Phase 10: Manual bet log
- Implement manual bet logging in `manual_bets`.
- Support candidate linkage when available (`candidate_id` nullable).
- Support later settlement linkage with `results` and profit/loss rules:
  - win: `stake_amount * (placed_odds - 1)`
  - loss: `-stake_amount`
  - void: `0`

## Required configuration values before Step 2
The following are explicitly configurable in `PROJECT_RULES.md` and must be set to concrete values before implementing ingestion and detection:
- `LEADER_MOVE_WINDOW_MINUTES`
- `STALE_SNAPSHOT_MAX_AGE_SECONDS`
- Configurable fallback leader source
- Configurable follower bookmaker list
