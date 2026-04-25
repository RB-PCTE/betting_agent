-- Initial database schema for Personal Odds-Analysis App (v1)
-- Source of truth: PROJECT_RULES.md
-- Scope: tennis only, match winner market only, research/alert workflow, no automated bet placement.

BEGIN;

-- 8.1 events
-- Stores tennis events and scheduling/status metadata.
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    tournament_name TEXT NOT NULL,
    league_name TEXT NOT NULL,
    start_time_utc TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT events_sport_tennis_v1_chk CHECK (sport = 'tennis')
);

CREATE INDEX IF NOT EXISTS idx_events_start_time_utc ON events (start_time_utc);
CREATE INDEX IF NOT EXISTS idx_events_tournament_name ON events (tournament_name);
CREATE INDEX IF NOT EXISTS idx_events_league_name ON events (league_name);

-- 8.2 participants
-- Stores participants for each event (e.g., player_a/player_b).
CREATE TABLE IF NOT EXISTS participants (
    participant_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    participant_name TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT participants_role_chk CHECK (role IN ('player_a', 'player_b'))
);

CREATE INDEX IF NOT EXISTS idx_participants_event_id ON participants (event_id);
CREATE INDEX IF NOT EXISTS idx_participants_event_role ON participants (event_id, role);

-- 8.3 markets
-- Stores market rows for events and selected participant in that market.
CREATE TABLE IF NOT EXISTS markets (
    market_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    market_type TEXT NOT NULL,
    selection_participant_id TEXT NOT NULL REFERENCES participants(participant_id),
    market_status TEXT NOT NULL,
    is_uncertain BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT markets_market_type_match_winner_v1_chk CHECK (market_type = 'match_winner')
);

CREATE INDEX IF NOT EXISTS idx_markets_event_id ON markets (event_id);
CREATE INDEX IF NOT EXISTS idx_markets_selection_participant_id ON markets (selection_participant_id);
CREATE INDEX IF NOT EXISTS idx_markets_event_market_type ON markets (event_id, market_type);

-- 8.4 odds_snapshots
-- Timestamped odds observations by source; includes leader/follower source role and quality flags.
CREATE TABLE IF NOT EXISTS odds_snapshots (
    odds_snapshot_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    market_id TEXT NOT NULL REFERENCES markets(market_id),
    source_name TEXT NOT NULL,
    source_role TEXT NOT NULL,
    decimal_odds NUMERIC NOT NULL,
    implied_probability NUMERIC NOT NULL,
    snapshot_time_utc TIMESTAMPTZ NOT NULL,
    is_suspended BOOLEAN NOT NULL,
    is_stale BOOLEAN NOT NULL,
    is_missing BOOLEAN NOT NULL,
    is_uncertain BOOLEAN NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT odds_snapshots_source_role_chk CHECK (source_role IN ('leader', 'follower')),
    CONSTRAINT odds_snapshots_decimal_odds_chk CHECK (decimal_odds > 1),
    CONSTRAINT odds_snapshots_implied_probability_chk CHECK (implied_probability > 0 AND implied_probability < 1)
);

CREATE INDEX IF NOT EXISTS idx_odds_snapshots_event_market_time ON odds_snapshots (event_id, market_id, snapshot_time_utc);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_source_time ON odds_snapshots (source_name, snapshot_time_utc);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_source_role ON odds_snapshots (source_role);

-- 8.5 detected_signals
-- Stores stale-price/drift signals and the computed movement/edge values.
CREATE TABLE IF NOT EXISTS detected_signals (
    signal_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    market_id TEXT NOT NULL REFERENCES markets(market_id),
    selection_participant_id TEXT NOT NULL REFERENCES participants(participant_id),
    leader_source_name TEXT NOT NULL,
    follower_source_name TEXT NOT NULL,
    leader_old_odds NUMERIC NOT NULL,
    leader_new_odds NUMERIC NOT NULL,
    odds_move_percent NUMERIC NOT NULL,
    follower_odds NUMERIC NOT NULL,
    follower_edge_percent NUMERIC NOT NULL,
    leader_move_window_minutes INTEGER NOT NULL,
    minutes_to_start_at_signal INTEGER NOT NULL,
    signal_status TEXT NOT NULL,
    signal_reason TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT detected_signals_status_chk CHECK (signal_status IN ('open', 'expired', 'resolved', 'dismissed')),
    CONSTRAINT detected_signals_leader_odds_chk CHECK (leader_old_odds > 1 AND leader_new_odds > 1),
    CONSTRAINT detected_signals_follower_odds_chk CHECK (follower_odds > 1)
);

CREATE INDEX IF NOT EXISTS idx_detected_signals_event_market ON detected_signals (event_id, market_id);
CREATE INDEX IF NOT EXISTS idx_detected_signals_detected_at ON detected_signals (detected_at);
CREATE INDEX IF NOT EXISTS idx_detected_signals_status ON detected_signals (signal_status);
CREATE INDEX IF NOT EXISTS idx_detected_signals_edge ON detected_signals (follower_edge_percent DESC);

-- 8.6 bet_candidates
-- Stores shortlisted/ignored/expired candidates produced from detected signals.
CREATE TABLE IF NOT EXISTS bet_candidates (
    candidate_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES detected_signals(signal_id),
    event_id TEXT NOT NULL REFERENCES events(event_id),
    market_id TEXT NOT NULL REFERENCES markets(market_id),
    selection_participant_id TEXT NOT NULL REFERENCES participants(participant_id),
    recommended_source_name TEXT NOT NULL,
    candidate_odds NUMERIC NOT NULL,
    candidate_implied_probability NUMERIC NOT NULL,
    candidate_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT bet_candidates_status_chk CHECK (candidate_status IN ('shortlisted', 'ignored', 'bet_logged', 'expired')),
    CONSTRAINT bet_candidates_candidate_odds_chk CHECK (candidate_odds > 1),
    CONSTRAINT bet_candidates_candidate_implied_probability_chk CHECK (candidate_implied_probability > 0 AND candidate_implied_probability < 1)
);

CREATE INDEX IF NOT EXISTS idx_bet_candidates_signal_id ON bet_candidates (signal_id);
CREATE INDEX IF NOT EXISTS idx_bet_candidates_status ON bet_candidates (candidate_status);
CREATE INDEX IF NOT EXISTS idx_bet_candidates_event_market ON bet_candidates (event_id, market_id);

-- 8.7 manual_bets
-- Stores manually placed bets only (human reviewed), optionally linked to a candidate.
CREATE TABLE IF NOT EXISTS manual_bets (
    manual_bet_id TEXT PRIMARY KEY,
    candidate_id TEXT REFERENCES bet_candidates(candidate_id),
    event_id TEXT NOT NULL REFERENCES events(event_id),
    market_id TEXT NOT NULL REFERENCES markets(market_id),
    selection_participant_id TEXT NOT NULL REFERENCES participants(participant_id),
    bookmaker_source_name TEXT NOT NULL,
    placed_odds NUMERIC NOT NULL,
    stake_amount NUMERIC NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL,
    notes TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT manual_bets_placed_odds_chk CHECK (placed_odds > 1),
    CONSTRAINT manual_bets_stake_amount_chk CHECK (stake_amount > 0)
);

CREATE INDEX IF NOT EXISTS idx_manual_bets_candidate_id ON manual_bets (candidate_id);
CREATE INDEX IF NOT EXISTS idx_manual_bets_placed_at ON manual_bets (placed_at);
CREATE INDEX IF NOT EXISTS idx_manual_bets_event_market ON manual_bets (event_id, market_id);

-- 8.8 closing_lines
-- Stores closing odds observations for CLV comparisons.
CREATE TABLE IF NOT EXISTS closing_lines (
    closing_line_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    market_id TEXT NOT NULL REFERENCES markets(market_id),
    selection_participant_id TEXT NOT NULL REFERENCES participants(participant_id),
    source_name TEXT NOT NULL,
    closing_odds NUMERIC NOT NULL,
    closing_time_utc TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT closing_lines_closing_odds_chk CHECK (closing_odds > 1)
);

CREATE INDEX IF NOT EXISTS idx_closing_lines_event_market_selection ON closing_lines (event_id, market_id, selection_participant_id);
CREATE INDEX IF NOT EXISTS idx_closing_lines_source_name ON closing_lines (source_name);

-- 8.9 results
-- Stores result outcomes used for settlement and P/L review.
CREATE TABLE IF NOT EXISTS results (
    result_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    market_id TEXT NOT NULL REFERENCES markets(market_id),
    selection_participant_id TEXT NOT NULL REFERENCES participants(participant_id),
    outcome TEXT NOT NULL,
    settled_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT results_outcome_chk CHECK (outcome IN ('win', 'loss', 'void', 'pending'))
);

CREATE INDEX IF NOT EXISTS idx_results_event_market_selection ON results (event_id, market_id, selection_participant_id);
CREATE INDEX IF NOT EXISTS idx_results_outcome ON results (outcome);
CREATE INDEX IF NOT EXISTS idx_results_settled_at ON results (settled_at);

COMMIT;
