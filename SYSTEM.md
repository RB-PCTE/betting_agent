# SYSTEM.md

## Purpose
This document describes the current architecture and data flow of the repository.

`PROJECT_RULES.md` remains the single source of truth for:
- strategy definitions
- thresholds
- formulas
- eligibility constraints
- schema naming and field contracts

This file intentionally does not redefine those rules.

## Current System Scope (Implemented)
- Sport: tennis only.
- Market: match winner only.
- Strategy slice implemented: early leader line movement detection foundation.
- Product mode: research/alert only.
- Automation boundary: no automatic betting; human action is external/manual.

## High-Level Architecture
The system is organized into loop-ready stages:

1. **Configuration loading**
   - Reads project-level source controls (approved sources, fallback leader, follower list, stale-age limit).
2. **Ingestion stage (implemented)**
   - Loads normalized source snapshots.
   - Validates scope and quality constraints.
   - Assigns source role (leader/follower).
   - Computes implied probability.
   - Persists normalized records to core tables.
3. **Leader movement detection stage (implemented foundation)**
   - Reads leader snapshots from persisted data.
   - Filters to usable snapshots in a configurable window.
   - Detects movement events using source-priority resolution.
   - Emits dry-run movement events.
4. **Follower-vs-leader edge stage (next)**
   - Compare follower prices against detected/selected leader prices.
   - Compute follower edge and apply threshold constraints from `PROJECT_RULES.md`.
5. **Signal persistence stage (next)**
   - Persist eligible signals to `detected_signals`.
6. **Candidate/review/reporting stages (future)**
   - Produce shortlist outputs, CLV review, and performance reporting.

## Data Domains and Modules

### Configuration
- `src/config/project_config.py`
  - Defines `ProjectConfig`.
  - Loads and validates project configuration JSON.
  - Resolves leader source priority from static order + configured fallback.

### Ingestion
- `src/ingestion/io.py`
  - Reads normalized source snapshots.
- `src/ingestion/models.py`
  - Defines typed records for event/market/participant/odds snapshot payloads.
- `src/ingestion/service.py`
  - Core validation and normalization logic.
  - Applies scope and quality rejections.
  - Computes implied probability and snapshot identity.
- `src/ingestion/repository.py`
  - Upserts event/participant/market entities.
  - Inserts normalized `odds_snapshots` rows.

### Detection
- `src/detection/line_movement.py`
  - Fetches leader snapshots.
  - Applies usability filters and source-priority selection.
  - Calculates leader movement events in the configured window.
  - Returns dry-run event payloads (no signal-table write yet).

### Operational scripts
- `scripts/run_ingestion.py`
  - CLI entry point for ingestion dry-run or DB write path.
- `scripts/run_line_movement_detector.py`
  - CLI entry point for leader movement detection run.

## Canonical Data Flow

1. **Inputs**
   - Config JSON (`config/project_config.json`).
   - Snapshot feed JSON (via ingestion script input).

2. **Normalize + validate snapshots**
   - Reject non-approved sources and out-of-scope records.
   - Reject missing/stale/suspended/uncertain records.
   - Accept valid records and enrich with derived fields.

3. **Persist normalized state**
   - Upsert identity tables (`events`, `participants`, `markets`).
   - Insert `odds_snapshots` history.

4. **Run leader movement detector**
   - Query persisted leader snapshots.
   - Restrict to time window and usable quality state.
   - Select active leader source by configured priority.
   - Emit movement events for downstream edge comparison/persistence.

5. **(Planned) edge + signal persistence**
   - Compare follower snapshots vs. selected leader state.
   - Persist only eligible opportunities to `detected_signals`.

## Loop-Driven Readiness
The repository already has the two required loop anchors:
- **Ingestion loop anchor**: repeatable snapshot normalization and storage.
- **Detection loop anchor**: repeatable leader movement scan over persisted snapshots.

To complete the standard loop-driven architecture, the next increments are:
1. follower-vs-leader edge computation stage
2. `detected_signals` persistence with status lifecycle fields
3. loop-level reporting outputs for operator review

## Data Quality and Trust Boundaries
- Only approved sources are processed.
- Leader role is deterministic from priority resolution.
- Odds are decimal-only and validated before acceptance.
- Snapshot recency is bounded by configurable stale thresholds.
- Suspended/missing/uncertain rows are excluded from actionable flow.

## Non-Goals in Current Implementation
- No automatic wagering or order placement.
- No schema mutation at runtime.
- No autonomous bankroll or stake engine.
- No production alert transport guarantees yet (CLI-focused foundations).
