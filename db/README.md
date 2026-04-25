# Database Schema (Step 2)

This folder contains the initial database schema for the Personal Odds-Analysis App.

## Files
- `schema.sql`: DDL for all v1 tables defined in `PROJECT_RULES.md` Section 8.

## Scope Applied
- Sport: tennis only (v1).
- Market: match winner only (v1).
- Product mode: alert/research only.
- No automated bet placement fields.

## Design Notes
- Table names and field names exactly follow `PROJECT_RULES.md` Section 8.
- IDs use text PK/FK fields as required by Section 5.
- UTC timestamp fields use `TIMESTAMPTZ` and retain the exact field names from Section 8.
- Indexes are added for expected query patterns:
  - event/market/time lookups
  - source/time lookups
  - status filtering
  - CLV and P/L review joins across event/market/selection
  - league/tournament review via `events`
- Check constraints are applied where explicit allowed values are defined in `PROJECT_RULES.md`.

## Not Included in Step 2
- Ingestion logic
- API connections
- Dashboard/UI
- Automated bet placement functionality
