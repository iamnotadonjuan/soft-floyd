# Garmin Sync

Status: **implemented** (exec-plan
[0002-garmin-sync.md](../exec-plans/active/0002-garmin-sync.md)).

## Behavior

A background poller inside `apps/server` checks Garmin Connect every
`poll_interval_minutes` (default 10), downloads the original FIT for any
new cycling activity, parses it, classifies bike type, and records which
sensor streams that specific ride actually contained. The same cycle is
also callable on demand — MCP tool `sync_garmin_now`, REST
`POST /api/sync/garmin`, or CLI `soft-floyd garmin-sync` — all of which
share one lock with the background loop so they can never race.

Authentication is a one-time interactive step, separate from sync itself:
`soft-floyd garmin-login` prompts for email/password/MFA and hands off to
`python-garminconnect`'s own token cache (see below), and verifies the
token was actually written before reporting success. Sync then reuses
that cached token; `sync_garmin_now`/`GET /api/sync/garmin/status` report
`"reauth_required"` with an actionable message if it's missing or
expired — never a silent no-op. A 429 from Garmin during login puts
`garmin-login` on a local cooldown (`SOFT_FLOYD_GARMIN_LOGIN_COOLDOWN_MINUTES`,
default 30 min) so retrying by hand can't re-trigger the rate limit —
see `docs/RELIABILITY.md`.

## Source: `python-garminconnect`, used directly

Confirmed dead ends, recorded so they aren't reconsidered later:
- **Garmin's own Developer Program** — enterprise/legal-entity applicants
  only, no personal tier (confirmed against their FAQ).
- **Strava**, as an alternative source — their 2026 API agreement
  explicitly prohibits using Strava data "in connection with the
  development, training, evaluation, or operation of any AI Application."

`python-garminconnect` is unofficial (reverse-engineered) but free, full
featured, and actively maintained (0.3.15 as of this plan). It replaced
its `garth` dependency with its own `curl_cffi`-based login after Garmin's
Cloudflare TLS fingerprinting broke garth's auth flow in March 2026 —
don't reintroduce a `garth` dependency.

## Token storage

The library manages its own token cache (`garmin_tokens.json`, written
0600 in a 0700 directory, auto-refreshed) at `settings.garmin_token_dir`
(default `~/.soft-floyd/garmin/`). **Deliberately not wrapped in
Fernet/Keychain encryption**, unlike v0 — see
[docs/SECURITY.md](../SECURITY.md) for why: an encrypted wrapper would
break the library's silent token refresh (it can only re-persist a
refreshed token if it controls the file directly), forcing a full SSO
login against a Cloudflare-protected endpoint on every process restart.

## Sensor honesty (the point of this plan)

Every ingested `Activity` carries its own `has_power_data` / `has_hr_data`
/ `has_cadence_data` / `has_speed_data` / `has_gps_data`, derived from
that ride's actual parsed FIT records
(`soft_floyd_core.activities.sensors.detect_sensor_streams`) — completely
independent of what `RiderProfile` declares. A power-meter rider whose
battery died mid-ride gets `has_power_data=False` for that one ride; a
rider who has never owned a power meter but whose profile still (wrongly)
says otherwise gets the same honest answer. See
[../design-docs/sensor-capability-model.md](../design-docs/sensor-capability-model.md)
rule 1, and `tests/test_ingest_pipeline.py`'s rule-1 regression test.

`activities/service.py`'s `available_metrics_for_activity` intersects the
rider's general capability-tier allowlist with what this specific ride's
streams support — the allowlist an agent should actually use when
discussing one ride, narrower than the profile-level
`get_available_metrics`.

## Modules

- `packages/core/src/soft_floyd_core/garmin/` — `errors.py` (exception
  taxonomy), `client.py` (`GarminClient`, wraps `garminconnect.Garmin`),
  `sync.py` (`run_sync_cycle`, `SyncRunner`).
- `packages/core/src/soft_floyd_core/activities/` — `fit_parser.py`
  (ported from v0, `power_w`/cadence added), `classify.py` (ported
  verbatim except a rule-1 key fix — see below), `sensors.py`
  (sensor-presence detection), `pipeline.py` (`ingest_activity`),
  `service.py` (read queries + `available_metrics_for_activity`).
- `tests/fixtures/*.fit` — regenerated (not the original v0 bytes): v0's
  generator had `altitude`/`speed` FIT field numbers swapped and never
  wrote `power`/`cadence` at all. `sample_road.fit` now carries a full
  sensor set (power, cadence, HR, GPS); `sample_mtb.fit` and
  `sample_indoor.fit` deliberately have no power/cadence, matching a
  no-power-meter rider.

## What changed from v0, deliberately

- **Classifier rule 1 fixed**: v0 read `activity_summary["is_indoor"]`,
  but real Garmin summaries use `"isIndoor"` — that key never matched, so
  the summary-side indoor check was dead code (classification depended
  entirely on the FIT-side flag). Fixed to read the correct key.
- **Sync state, not just a cursor**: `GarminSyncState` (replacing v0's
  `PollCursor`) tracks `last_status`/`last_error`/`consecutive_errors`, so
  `GET /api/sync/garmin/status` can distinguish "Garmin is down" from
  "the rider has no rides" (`docs/RELIABILITY.md`'s rule). v0's cursor was
  nulled on every transient error, destroying "last seen" state; this
  version only advances it on success.
- **Reauth doesn't stop the poller.** v0's mid-loop `ReauthRequired`
  handling just kept backing off forever. This version re-checks at a
  fixed ≥15-minute interval (notifying once on transition into the
  state, not every cycle) so a fresh `garmin-login` is picked up without
  a server restart — while still never counting toward the error-backoff
  used for real API errors.
- **Blocking I/O moved off the event loop.** `garminconnect` and
  `fitdecode` are both synchronous; v0 ran them directly inside its async
  poller, blocking `/mcp` and `/api` for the whole cycle. `run_sync_cycle`
  is now a plain sync function called via `anyio.to_thread.run_sync`.
- **First sync is bounded**, not a silent mini-backfill: an empty cursor
  ingests only the single most recent activity. Historical backfill is
  out of scope for this plan (see tech-debt-tracker.md).
- Metrics (HR zones, TRIMP, decoupling, FTP/NP/TSS), wellness/HRV/sleep
  sync, and manual FIT upload are all out of scope here — see
  `docs/design-docs/training-signal-model.md` for the next exec-plan.

## Acceptance

- A ride finished on the Edge appears via `list_activities` /
  `GET /api/activities` within one poll interval of showing up in Garmin
  Connect, with correct bike-type classification and accurate
  per-activity sensor flags.
- Garmin auth failures produce `"reauth_required"` with an actionable
  message on every surface (MCP, REST, CLI) — never a silent no-op, never
  an infinite tight retry loop.
- `tests/test_ingest_pipeline.py` proves per-activity sensor data is
  independent of the rider's declared profile sensors.
