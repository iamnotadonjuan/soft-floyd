# Garmin Sync

Status: **not implemented.** Next planned feature after the scaffold —
write an exec-plan in `docs/exec-plans/active/` before starting.

## Intended behavior

After a ride finishes on the rider's Garmin Edge device and syncs to
Garmin Connect (automatically, over the Edge's own connectivity), Soft
Floyd picks it up within roughly the poll interval (v0 used 10 minutes)
without the rider doing anything manual, and it's available via
`list_activities` (MCP) / `GET /api/activities` (REST) shortly after.

## Building blocks to reuse from v0 (git tag `v0-legacy`)

- `src/coach/ingest/garmin_client.py` — `python-garminconnect`-based
  adapter with Fernet-encrypted token storage. Auth/rate-limit failures
  map to actionable errors (`ReauthRequired`, `GarminRateLimited`) rather
  than silent retry — see `docs/RELIABILITY.md`.
- `src/coach/ingest/fit_parser.py` — `fitdecode`-based FIT file parsing.
- `src/coach/ingest/pipeline.py` — the shared per-activity ingest
  pipeline (parse → classify → store); poller and backfill both call it
  rather than duplicating ingest logic. Preserve that shape.
- `src/coach/ingest/poller.py`, `backfill.py` — scheduled polling and
  historical batch import.
- `src/coach/classify/bike_type.py` — the rule-based road/mtb/indoor
  classifier (order matters; see the rules preserved in
  `docs/design-docs/core-beliefs.md`'s sibling docs and v0's `AGENTS.md`
  at the tag).
- `tests/fixtures/*.fit` — real anonymized FIT fixtures, worth carrying
  forward as-is rather than regenerating.

## What changes from v0

- Ingested activities must record **which sensors were actually present
  in that FIT file's data streams** (power, HR, cadence, speed) — not
  just assume the profile's declared hardware. This is what
  [sensor-capability-model.md](../design-docs/sensor-capability-model.md)
  rule 1 requires: per-activity analysis checks the stream, not the
  profile.
- Ingestion is exposed as an MCP tool (`sync_now` or similar) in addition
  to the background poller, so a rider using Claude Desktop can trigger a
  manual sync — matching the "manual Garmin sync" goal from the original
  ask.

## Acceptance (draft — refine in the exec-plan)

- A ride finished on the Edge appears via `list_activities` within one
  poll interval of showing up in Garmin Connect, with correct bike-type
  classification and a record of which sensor streams were present.
- Garmin auth failures produce a clear, actionable message, never a
  silent no-op.
