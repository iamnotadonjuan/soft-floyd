# Reliability

## Garmin Connect is unofficial

There is no supported public API for Garmin Connect (confirmed: their
Developer Program is enterprise-only); ingestion uses `python-garminconnect`,
an unofficial client library. That means:

- Garmin can change behavior or rate-limit without notice — `garth` (an
  earlier auth dependency, no longer used) broke entirely in March 2026
  when Garmin changed its TLS fingerprinting. Map `401`s to
  `ReauthRequired` and surface it (CLI message, desktop notification,
  `GET /api/sync/garmin/status`) rather than silently retrying forever.
  On reauth, the poller re-checks periodically (≥15 min) rather than
  stopping outright, so a fresh `garmin-login` is picked up without a
  restart — see `soft_floyd_core.garmin.sync.SyncRunner`.
- Map `429`/`5xx` to backoff, not immediate retry — 10-minute poll
  interval, exponential backoff capped at 60 minutes
  (`soft_floyd_core.garmin.sync.backoff_seconds`).
- Never treat "Garmin is down" as "the rider has no data" — distinguish
  a sync failure from an empty result. `GarminSyncState`
  (`last_status`/`last_error`/`consecutive_errors`) is the durable answer;
  `GET /api/sync/garmin/status` / MCP `get_garmin_sync_status` expose it.
- Garmin/FIT calls are synchronous (`garminconnect`, `fitdecode`) — never
  call them directly from an async context (event loop, app lifespan).
  `SyncRunner` runs each sync cycle via `anyio.to_thread.run_sync` so a
  slow Garmin response can't block `/mcp` or `/api`.

## LLM calls (once the coach agent exists)

- Every call goes through `packages/core/src/soft_floyd_core/llm/client.py`
  so cost accounting (`Usage.cost_usd`) is never bypassed.
- A failed LLM call should degrade to "I couldn't generate an analysis
  right now" — never to a fabricated response.

## Local server

- Single process, single SQLite file. No HA requirements — this runs on
  one machine for one rider. Restart-safe means: Alembic migrations
  (`soft_floyd_core.db.run_migrations`) run on boot and are idempotent —
  including handling a database this app previously created via the old
  `create_all()` path.
- `soft-floyd serve` binds to `127.0.0.1` — a bind failure (port in use)
  should error clearly, not silently pick another port.
