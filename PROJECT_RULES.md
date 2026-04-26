# PROJECT_RULES.md

## 1) Project Identity and Purpose
- **Project name**: Personal Odds-Analysis App
- **Primary purpose**: Betting research, signal generation, and alerting only.
- **Automation boundary**: This agent is a research/alerting tool only and must never execute betting actions.
- **Human oversight**: The user manually reviews every signal/alert/candidate/recommendation and manually places any bet.

### 1.1 Prohibited actions (hard safety boundary)
The agent must never:
- place bets
- submit bets
- automate bookmaker interaction
- log in to bookmaker accounts
- transfer money
- bypass human approval

### 1.2 Terminology policy
- Preferred terms: **signal**, **alert**, **candidate**, **recommendation**.
- Avoid terms implying automatic execution, including: **trade execution**, **bet execution**, **auto-betting**, **order placement**.

## 2) Scope (v1)
- **Sport**: Tennis only.
- **Market**: Match winner only.
- **Strategy**: Tennis Early Line Drift.
- **Product mode**: Alert/research only.
- **Workflow**: No temporary spreadsheet workflow.

## 3) Source Assumptions and Roles
### 3.1 Leader sources priority
1. Betfair exchange (if available)
2. Pinnacle (if available)
3. Configurable fallback leader source

### 3.2 Follower sources
- Configurable bookmaker list.

### 3.3 Source policy constraints
- Odds ingestion must use approved/allowed odds sources only.
- Ignore suspended, stale, missing, or uncertain markets.

## 4) Global Variables and Strategy Thresholds
- `LEADER_MOVE_THRESHOLD_PERCENT = 0.08` (8%)
- `FOLLOWER_EDGE_THRESHOLD_PERCENT = 0.08` (8%)
- `MINUTES_TO_START_BLOCK = 60`
- `ALLOW_WITHIN_60_MINUTES = false` (default; configurable)
- `LEADER_MOVE_WINDOW_MINUTES` = configurable integer (time window for movement detection)
- `STALE_SNAPSHOT_MAX_AGE_SECONDS` = configurable integer

## 5) Naming Conventions
- Tables: `snake_case`, plural nouns.
- Fields: `snake_case`.
- IDs: `<entity>_id` as text UUID.
- Timestamps: UTC, field names end with `_at` for instants.
- Odds format: decimal only.
- Percent fields: fractional representation (e.g., `0.08` for 8%).

## 6) Calculation Rules (single source of truth)
- `implied_probability = 1 / decimal_odds`
- `odds_move_percent = (old_odds - new_odds) / old_odds`
- `follower_edge_percent = (follower_odds - leader_odds) / leader_odds`
- CLV is positive when recorded bet/candidate odds are better than closing odds.
- For decimal odds on the selected player, **better = higher odds**.

## 7) Signal Eligibility Rules
A signal is eligible only if all are true:
1. Event sport is tennis.
2. Market is match winner.
3. Leader source is resolved by Section 3.1 priority.
4. Leader movement satisfies:
   - movement window = `LEADER_MOVE_WINDOW_MINUTES`
   - `odds_move_percent >= LEADER_MOVE_THRESHOLD_PERCENT`
5. Follower stale-price condition satisfies:
   - `follower_edge_percent >= FOLLOWER_EDGE_THRESHOLD_PERCENT`
6. Match start constraint:
   - if `ALLOW_WITHIN_60_MINUTES = false`, then `minutes_to_start >= MINUTES_TO_START_BLOCK`
7. Market and snapshots are not suspended, stale, missing, or uncertain.

## 8) Database Tables and Field Names

### 8.1 `events`
- `event_id` (PK)
- `sport`
- `tournament_name`
- `league_name`
- `start_time_utc`
- `status`
- `created_at`
- `updated_at`

### 8.2 `participants`
- `participant_id` (PK)
- `event_id` (FK -> events.event_id)
- `participant_name`
- `role` (e.g., player_a, player_b)
- `created_at`
- `updated_at`

### 8.3 `markets`
- `market_id` (PK)
- `event_id` (FK -> events.event_id)
- `market_type` (must be `match_winner` in v1)
- `selection_participant_id` (FK -> participants.participant_id)
- `market_status`
- `is_uncertain`
- `created_at`
- `updated_at`

### 8.4 `odds_snapshots`
- `odds_snapshot_id` (PK)
- `event_id` (FK -> events.event_id)
- `market_id` (FK -> markets.market_id)
- `source_name`
- `source_role` (`leader` or `follower` at snapshot time)
- `decimal_odds`
- `implied_probability`
- `snapshot_time_utc`
- `is_suspended`
- `is_stale`
- `is_missing`
- `is_uncertain`
- `ingested_at`

### 8.5 `detected_signals`
- `signal_id` (PK)
- `event_id` (FK -> events.event_id)
- `market_id` (FK -> markets.market_id)
- `selection_participant_id` (FK -> participants.participant_id)
- `leader_source_name`
- `follower_source_name`
- `leader_old_odds`
- `leader_new_odds`
- `odds_move_percent`
- `follower_odds`
- `follower_edge_percent`
- `leader_move_window_minutes`
- `minutes_to_start_at_signal`
- `signal_status` (`open`, `expired`, `resolved`, `dismissed`)
- `signal_reason`
- `detected_at`

### 8.6 `bet_candidates`
- `candidate_id` (PK)
- `signal_id` (FK -> detected_signals.signal_id)
- `event_id` (FK -> events.event_id)
- `market_id` (FK -> markets.market_id)
- `selection_participant_id` (FK -> participants.participant_id)
- `recommended_source_name`
- `candidate_odds`
- `candidate_implied_probability`
- `candidate_status` (`shortlisted`, `ignored`, `bet_logged`, `expired`)
- `created_at`
- `updated_at`

### 8.7 `manual_bets`
- `manual_bet_id` (PK)
- `candidate_id` (FK -> bet_candidates.candidate_id, nullable)
- `event_id` (FK -> events.event_id)
- `market_id` (FK -> markets.market_id)
- `selection_participant_id` (FK -> participants.participant_id)
- `bookmaker_source_name`
- `placed_odds`
- `stake_amount`
- `placed_at`
- `notes`
- `created_at`
- `updated_at`

### 8.8 `closing_lines`
- `closing_line_id` (PK)
- `event_id` (FK -> events.event_id)
- `market_id` (FK -> markets.market_id)
- `selection_participant_id` (FK -> participants.participant_id)
- `source_name`
- `closing_odds`
- `closing_time_utc`
- `created_at`

### 8.9 `results`
- `result_id` (PK)
- `event_id` (FK -> events.event_id)
- `market_id` (FK -> markets.market_id)
- `selection_participant_id` (FK -> participants.participant_id)
- `outcome` (`win`, `loss`, `void`, `pending`)
- `settled_at`
- `created_at`

## 9) Derived Metrics and Storage Rules
- `odds_snapshots.implied_probability` must use Section 6 formula.
- `detected_signals.odds_move_percent` must use Section 6 formula.
- `detected_signals.follower_edge_percent` must use Section 6 formula.
- Candidate CLV:
  - `candidate_clv_percent = (candidate_odds - closing_odds) / closing_odds`
  - positive when `candidate_odds > closing_odds`
- Manual bet CLV:
  - `manual_bet_clv_percent = (placed_odds - closing_odds) / closing_odds`
  - positive when `placed_odds > closing_odds`
- Manual bet P/L (decimal odds):
  - if win: `profit_loss = stake_amount * (placed_odds - 1)`
  - if loss: `profit_loss = -stake_amount`
  - if void: `profit_loss = 0`

## 10) Shortlist Production Rules
- Output must be low-volume shortlist.
- Prioritize candidates with highest `follower_edge_percent` among eligible signals.
- Exclude candidates when signal status is not `open`.
- Exclude candidates with invalid/stale/uncertain/suspended data.

## 11) Dashboard Requirements (minimum)
- Current opportunities
- Signal history
- CLV review
- Profit/loss review
- Source performance
- League/tournament performance

## 12) Change Control Rules
- This file is the single source of truth for variables, naming, thresholds, strategy, schema, and calculations.
- Before any code or schema change, read this file.
- Do not invent table names, field names, thresholds, or strategy logic outside this file.
- If a new variable/rule is needed:
  1. update `PROJECT_RULES.md`
  2. then apply code/schema changes
- If implementation conflicts with this file, this file wins.
- Every future PR/change must include a short note stating which sections of this file were used or updated.
