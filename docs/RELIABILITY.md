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
  (`soft_floyd_core.garmin.sync.backoff_seconds`). A server-supplied
  `Retry-After` can only *lengthen* the delay, never shorten an
  already-earned backoff (`rate_limited_delay_seconds`).
- A 429 during `soft-floyd garmin-login` itself (each login runs
  `garminconnect`'s full 5-strategy SSO chain against
  Cloudflare-protected endpoints, which is easy to exhaust by retrying
  interactively) sets a local cooldown
  (`GarminSyncState.login_blocked_until`,
  `SOFT_FLOYD_GARMIN_LOGIN_COOLDOWN_MINUTES`, default 30). A repeated
  `garmin-login` while the cooldown is active is refused locally with no
  network call — see `soft_floyd_core.garmin.login.perform_login`.
- Never treat "Garmin is down" as "the rider has no data" — distinguish
  a sync failure from an empty result. `GarminSyncState`
  (`last_status`/`last_error`/`consecutive_errors`) is the durable answer;
  `GET /api/sync/garmin/status` / MCP `get_garmin_sync_status` expose it.
- Riders never see raw Garmin errors. `GarminApiError.user_message` is the
  plain-language text the web app shows (REST `detail`, the connection
  card's `last_error`); `str(exc)` keeps the technical text (HTTP status,
  upstream message) for the CLI and MCP, and `map_garmin_exception` logs it
  as a `garmin_request_failed` warning with the action, status and error.
  A `5xx` from `connectapi.garmin.com` is `GarminUnavailable`. Cloudflare
  `521`-`523` (its edge couldn't reach Garmin's servers, so the request never
  arrived) is retried once for workout uploads; nothing else is retried. This
  happened for real on 2026-09-28: `connectapi.garmin.com` answered `521`
  from Cloudflare even with no credentials while `connect.garmin.com` was
  fine, so both workout upload and ride sync failed until Garmin recovered.
- Sending a workout is two calls (create or update, then schedule). If the
  second fails, `WorkoutNotScheduled` carries the workout id and
  `training.service.send_to_garmin` keeps it, so a retry updates that
  workout instead of uploading a duplicate.
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
