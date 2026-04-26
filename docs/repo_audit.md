# Repository Audit: `RB-PCTE/betting_agent`

Date: 2026-04-26 (UTC)

## 1) What has already been built?

The repo contains a functioning **foundation** for a tennis-only odds research workflow:

- A complete v1 relational schema in `db/schema.sql` for events, markets, snapshots, signals, candidates, bets, closing lines, and results.
- A config loader (`src/config/project_config.py`) that validates required ingestion settings and enforces leader/follower source relationships.
- An ingestion domain model and JSON loader (`src/ingestion/models.py`, `src/ingestion/io.py`).
- An ingestion service (`src/ingestion/service.py`) that:
  - validates scope/rules (sport, market type, source approval, stale/suspended/missing/uncertain checks),
  - computes implied probability,
  - resolves source role,
  - generates deterministic snapshot IDs,
  - writes accepted snapshots via repository abstraction.
- A repository adapter (`src/ingestion/repository.py`) that upserts `events`, `participants`, `markets`, and inserts `odds_snapshots`.
- A Step-4 foundation detector (`src/detection/line_movement.py`) for leader-source price movement in a configurable lookback window with threshold filtering.
- Two runnable scripts:
  - `scripts/run_ingestion.py`
  - `scripts/run_line_movement_detector.py`
- A passing unit-test suite for config, ingestion, and line movement detection.

This is currently an **alert/research foundation**, not an end-to-end agent loop.

## 2) What files and folders exist?

Top-level structure currently present:

- `README.md`
- `PROJECT_RULES.md`
- `config/`
  - `project_config.json`
- `db/`
  - `README.md`
  - `schema.sql`
- `docs/`
  - `IMPLEMENTATION_PLAN.md`
- `scripts/`
  - `run_ingestion.py`
  - `run_line_movement_detector.py`
- `src/`
  - `__init__.py`
  - `config/` (`__init__.py`, `project_config.py`)
  - `ingestion/` (`__init__.py`, `io.py`, `models.py`, `repository.py`, `service.py`)
  - `detection/` (`__init__.py`, `line_movement.py`)
- `tests/`
  - `test_project_config.py`
  - `test_ingestion_service.py`
  - `test_line_movement_detector.py`
  - `fixtures/` (`project_config.valid.json`, `source_snapshots.json`)

## 3) What is the current strategy?

The defined strategy is **Tennis Early Line Drift**, constrained to:

- sport = tennis
- market = match winner
- mode = research/alerts only (no auto-bet)

Operationally, the implemented part of strategy is:

1. Ingest approved-source snapshots.
2. Resolve leader source via priority: Betfair exchange, then Pinnacle, then fallback leader.
3. Reject stale/suspended/missing/uncertain records.
4. Detect leader odds movement within a configured window.
5. Trigger movement event when movement meets threshold.

The follower-edge comparison and signal persistence stages are planned in docs/rules but not yet implemented in code.

## 4) What variables, thresholds, and rules are already defined?

Defined in `PROJECT_RULES.md` and partially implemented:

### Core thresholds/flags

- `LEADER_MOVE_THRESHOLD_PERCENT = 0.08`
- `FOLLOWER_EDGE_THRESHOLD_PERCENT = 0.08`
- `MINUTES_TO_START_BLOCK = 60`
- `ALLOW_WITHIN_60_MINUTES = false` (configurable)
- `LEADER_MOVE_WINDOW_MINUTES` (configurable integer)
- `STALE_SNAPSHOT_MAX_AGE_SECONDS` (configurable integer)

### Formula rules

- `implied_probability = 1 / decimal_odds`
- `odds_move_percent = (old_odds - new_odds) / old_odds`
- `follower_edge_percent = (follower_odds - leader_odds) / leader_odds`
- Candidate/manual CLV and manual bet P/L formulas are defined for future stages.

### Implemented rule enforcement in code

- Config validation of approved sources, fallback leader source, follower sources, stale age.
- Ingestion filtering for source approval, sport/market scope, missing/stale/suspended/uncertain/invalid odds.
- Source role assignment (`leader` vs `follower`) based on priority + follower list.
- Step-4 leader movement detection with source-priority choice and threshold check.

## 5) What database/schema work exists?

A robust initial schema exists in `db/schema.sql`:

- All v1 tables from rules are created (`events`, `participants`, `markets`, `odds_snapshots`, `detected_signals`, `bet_candidates`, `manual_bets`, `closing_lines`, `results`).
- Naming conventions align with the rules (`snake_case`, text IDs, UTC timestamps).
- Domain constraints/checks exist for sport, market type, enum-like status/outcome fields, and odds/probability value bounds.
- Indexes exist for common query paths (event/market/time, statuses, joins for review/reporting).

Current write-path coverage in code reaches only:

- `events`
- `participants`
- `markets`
- `odds_snapshots`

No repository/service code currently writes `detected_signals`, `bet_candidates`, `manual_bets`, `closing_lines`, or `results`.

## 6) What tests exist?

The test suite currently includes:

- `tests/test_project_config.py`
  - config loading and leader priority construction.
- `tests/test_ingestion_service.py`
  - accepts valid snapshot,
  - rejects stale snapshot,
  - dry-run behavior skips DB writes.
- `tests/test_line_movement_detector.py`
  - movement detection at threshold,
  - exclusion of uncertain/suspended/stale/missing,
  - source-priority behavior,
  - DB read path (`fetch_snapshots_from_db`) with in-memory SQLite.

All current tests pass (`8/8`).

## 7) What loop, if any, already exists?

There is **no continuous loop/orchestrator** implemented.

What exists:

- one-shot script for ingestion (`run_ingestion.py`)
- one-shot script for line movement detection (`run_line_movement_detector.py`)

Missing:

- periodic scheduler/daemon,
- stateful orchestration across pipeline stages,
- durable signal/candidate lifecycle transitions,
- idempotent loop checkpoints/recovery.

## 8) What is missing before this becomes a usable loop-driven agent?

High-impact missing pieces:

1. **Follower-vs-leader edge computation** and rule gating (`FOLLOWER_EDGE_THRESHOLD_PERCENT`).
2. **Signal persistence layer** into `detected_signals` with status/reason semantics.
3. **Loop orchestrator** that runs ingestion + detection on schedule and writes outputs.
4. **Minutes-to-start gating** (`MINUTES_TO_START_BLOCK`, `ALLOW_WITHIN_60_MINUTES`) in executable pipeline logic.
5. **Source availability/leader-resolution resilience** across real feeds and partial outages.
6. **Configuration completion**: default `config/project_config.json` is placeholder/empty values right now.
7. **Operational hardening**: logging structure, retries, idempotency keys, metrics, and run health checks.
8. **Manual-review UX/reporting surface** (even CLI/CSV minimum) for shortlist consumption.

## 9) What should be kept?

Keep and build on:

- `PROJECT_RULES.md` governance model (clear source-of-truth and change control).
- `db/schema.sql` breadth and constraints foundation.
- `src/ingestion/service.py` validation/normalization pattern.
- `src/detection/line_movement.py` isolated, testable detection structure.
- existing tests as a quality baseline.
- script entry points as practical operator interfaces during early iterations.

## 10) What should be discarded or treated as scratch?

Treat as scratch/temporary:

- `config/project_config.json` current values (`[]`, empty strings, zero stale age) — these are placeholders, not usable runtime config.
- Any assumption that `README.md` “to be added later” structure notes reflect current state (repo has already progressed beyond that text).
- The current detection output mode (JSON print only) as final behavior; it is a temporary dry-run style surface.

Do **not** discard:

- schema,
- ingestion service,
- movement detection module,
- tests.

---

## Recommended next single build step

**Implement Phase 5 foundation: follower-vs-leader comparison and `detected_signals` persistence (dry-run + write mode).**

Why this single step next:

- It converts current movement-only detection into actionable, rules-aligned signals.
- It is the minimum bridge between existing ingestion+movement components and a usable shortlist pipeline.
- It exercises already-defined schema (`detected_signals`) without requiring full dashboard/manual-bet/result workflows yet.

Suggested acceptance criteria for that step:

1. For each leader movement event, evaluate follower stale-price edge using `follower_edge_percent` formula.
2. Enforce both thresholds (`LEADER_MOVE_THRESHOLD_PERCENT` and `FOLLOWER_EDGE_THRESHOLD_PERCENT`) plus data quality checks.
3. Enforce match-start gating from project rules.
4. Insert eligible signals into `detected_signals` with `signal_status='open'` and explicit `signal_reason`.
5. Add unit tests for pass/fail edge cases and source-priority interactions.
