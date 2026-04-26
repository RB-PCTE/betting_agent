# OPERATING_LOOP.md

## Purpose
This document defines the runtime operating loop, trigger model, state handling, reporting responsibilities, and human approval boundaries.

`PROJECT_RULES.md` remains authoritative for formulas, thresholds, and eligibility definitions.

## Runtime Loop Overview
The standard loop is:

1. **Load configuration and run context**
2. **Ingest latest snapshots**
3. **Run leader movement detection**
4. **(Next) Compute follower-vs-leader edge**
5. **(Next) Persist eligible signals**
6. **Publish operator-facing run summary**
7. **Wait for next trigger**

Current implementation status:
- Steps 1–3 are implemented as foundations.
- Steps 4–5 are the next development targets.
- Step 6 exists at logging/CLI-output level.

## Trigger Model
Recommended trigger modes:
- **Scheduled interval trigger** (primary): run every N minutes (operator-configured).
- **Manual trigger** (secondary): ad hoc runs for testing, replays, or incident handling.

Trigger safeguards:
- Each run captures a single `as_of_utc` boundary.
- The run should process available snapshots deterministically for that boundary.
- Parallel runs should be prevented or isolated by orchestration (external runner responsibility).

## Per-Run State Contract
Each loop run should maintain a run-state envelope with:
- run identifier (external orchestration ID)
- started/ended UTC timestamps
- config reference/hash used for the run
- counts:
  - snapshots received
  - snapshots accepted
  - snapshots rejected (by reason)
  - leader movement events detected
  - (next) edge-qualified opportunities
  - (next) signals persisted
- terminal status: success / partial / failed

This repository currently exposes most of the above as CLI logs and return summaries, not yet as a dedicated run table.

## Stage-by-Stage Operating Behavior

### Stage 1: Configuration load
- Read project configuration before processing.
- Validate required keys and source constraints.
- Fail fast on invalid config.

### Stage 2: Ingestion
- Read incoming source snapshots.
- Normalize timestamps/fields.
- Enforce in-scope and quality constraints.
- On non-dry-run: persist accepted snapshots.
- Emit accepted/rejected counters and reasons.

### Stage 3: Leader movement detection
- Read leader snapshots from storage.
- Restrict to configured lookback window and usable records.
- Select leader source by priority.
- Compute movement events.
- Emit dry-run event payloads and count.

### Stage 4 (Next): Follower-vs-leader edge
- For each leader movement candidate, locate follower stale prices.
- Compute edge percent and threshold qualification.
- Produce edge-qualified records for signal eligibility checks.

### Stage 5 (Next): Signal persistence
- Apply full eligibility gates including start-time block and data quality checks.
- Persist only eligible rows to `detected_signals`.
- Initialize signal lifecycle state for downstream review workflows.

## Failure Handling and Recovery
- **Config errors**: hard fail; do not continue with defaults.
- **Input parse errors**: reject affected records, continue run if safe.
- **Database write errors**: fail run and surface error for operator retry.
- **Detection errors**: fail detection stage; keep ingestion outputs already committed.

Recovery approach:
- Re-run from the same or later trigger with corrected config/input.
- Use immutable snapshot history to recompute downstream stages.

## Reporting and Operator Outputs
Minimum per-run operator output should include:
- run boundary (`as_of_utc`)
- accepted/rejected ingestion summary
- rejection reason breakdown
- leader movement event count
- (next) edge-qualified count
- (next) signals created count
- notable warnings/errors

Current implementation provides:
- structured log lines from ingestion
- JSON event output from line movement detector CLI

## Human Approval Boundaries
Hard boundaries:
- No automatic bet placement.
- No automatic execution against bookmaker/exchange APIs.
- Any bet action occurs only after human review outside this loop.

Human decision checkpoints (target end-state):
1. Review open detected signals.
2. Decide whether to create/accept a bet candidate.
3. Place bets manually (if any) using external interfaces.
4. Log manual bet metadata for CLV/P&L follow-up.

## Idempotency and Determinism Notes
- Ingestion uses deterministic snapshot IDs derived from stable fields.
- Re-running the same snapshot set should not create duplicate event/participant/market identities.
- Detection output is deterministic for a fixed snapshot state + `as_of_utc` + config.

## Implementation Boundaries for Next Changes
When implementing loop completion:
- add follower-vs-leader edge stage without changing source-of-truth formulas
- add signal persistence without altering schema contracts
- preserve explicit dry-run path for safe validation
- keep all approval boundaries intact (manual-only wagering)
