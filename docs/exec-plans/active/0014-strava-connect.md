# 0014 — Strava Connect

## Context

Garmin is the only activity source today. Riders who record on other
devices, or who already sync everything to Strava, can't use Soft Floyd.
This plan adds Strava (via [`stravalib`](https://github.com/stravalib/stravalib))
as a second provider next to Garmin.

**Risk acceptance (decided 2026-09-28).** Exec-plan 0002 and
`docs/product-specs/garmin-sync.md` record Strava as a "confirmed dead
end", because Strava's 2026 API agreement prohibits using their data "in
connection with the development, training, evaluation, or operation of
any AI Application." Soft Floyd is an AI coach, so this is a real
conflict. The decision here is to proceed for **personal / self-hosted
use only** and accept that risk. Constraints that follow from it:
- Strava data is never used to train or fine-tune any model.
- This is not a hosted, multi-tenant offering of Strava-derived data.
- The two "dead end" notes are amended to point at this plan (step 9)
  rather than left contradicting it.

**Scope.** Streams → `Lap`/`Record` rows, so training load, zones and
sensor flags work the same as for Garmin rides. Summary-only import is
not the goal.

"Done" means: connecting Strava from Settings (OAuth) leads to a ride
appearing in `list_activities`/`GET /api/activities` within one poll
interval, with honest per-activity sensor flags, and no ride is counted
twice when Garmin is also connected.

Out of scope: webhooks, historical backfill, pushing workouts to Strava,
wellness data.

## Design

**Library.** `stravalib`, added to `packages/core/pyproject.toml`.

**Auth (OAuth2, unlike Garmin's password login).**
- `strava_client_id` / `strava_client_secret` in `core/config.py`
  (`SOFT_FLOYD_STRAVA_*`).
- `GET /api/connections/strava/authorize` redirects to Strava, scope
  `activity:read_all`, with a signed `state` carrying the account id.
- `GET /api/connections/strava/callback` exchanges the code and saves
  tokens. It must be allowlisted in `server/auth_middleware.py`. Copy the
  Google OAuth pattern in `server/auth_api.py`.
- Tokens (access, refresh, expires_at) live in
  `~/.soft-floyd/strava/<account_id>/strava_tokens.json`, mode 0600 —
  the same token-dir approach as Garmin, keeping secrets out of the DB.
  Record this in `docs/SECURITY.md` (Strava is the first provider with an
  app-level client secret).
- The client refreshes the access token before calls when it is close to
  expiring.

**Client.** `core/strava/client.py`: `StravaClient`, modeled on
`core/garmin/client.py`, with a `client_factory` seam for tests. Methods:
`list_recent_activities(after)`, `get_activity(id)`, `get_streams(id)`
(time, heartrate, watts, cadence, velocity_smooth, altitude, latlng,
distance), `logout` (deauthorize + delete the token file).

**Errors.** `core/strava/errors.py`: 401 → reauth, 429 → rate-limited
(100 req/15 min, 1000/day; honor the rate-limit headers), 404 →
not-found, with rider-facing `USER_*` messages like
`core/garmin/errors.py`. Introduce a shared `ProviderApiError` base so
`pipeline.py` (`GarminApiError` catch, ~line 123) and
`training/service.py:20` stop depending on Garmin-specific types.

**Schema (Alembic).**
- `Activity.source` String(16), default `"garmin"`, backfilled.
- `Activity.external_id` String, taking over the role of `garmin_id`.
  Decide during implementation whether to keep `garmin_id` nullable or
  rename it; check the `account_scope.py` autofill (`garmin_id = id`)
  first.
- Unique constraint becomes `(account_id, source, external_id)`.
- New table `strava_sync_state`, shaped like `GarminSyncState`. The
  cursor is `last_activity_start_at` (timestamp, used with `after=`),
  not an activity id.
- `make docs-schema` afterwards.

**Ingest.** `ingest_strava_activity(session, settings, source, summary)`
in `core/activities/pipeline.py`.
- `core/strava/streams.py` converts streams into the existing
  `ParsedFit` (`SessionSummary`, `LapData`, `RecordData`), so
  `_apply_sensor_data`, Lap/Record persistence, the 3 MB gate and
  `classify` are reused unchanged.
- Summary mapping: `start_date`, `sport_type`/`type`, `trainer` →
  `is_indoor`, `distance`, `moving_time` (always moving time; document
  it), `total_elevation_gain`, `average_heartrate`, `max_heartrate`.
- `device_watts=False` means estimated power: **do not** set
  `has_power_data` (sensor-capability-model: never fabricate a signal).
- `classify.py:34` reads the Garmin key `isIndoor`; pass a normalized
  summary or teach it `trainer`.
- `fit_status="ok"` means streams were stored. Renaming it (e.g.
  `data_status`) is deferred to the tech-debt tracker.
- Cycling sport types only, like Garmin.

**Cross-provider dedup.** Before inserting, skip a ride if another
source already has an activity for the same account starting within
±2 min with duration within 5%. Garmin wins (real FIT data).

**Sync runner.** `core/strava/sync.py` `run_sync_cycle` never raises;
mirrors the Garmin cycle's first-run limit and backoff. Generalize
`server/runtime.py` and `server/lifespan.py` to one runner per connected
provider per account.

**Connections.** `_strava_connection()` in `core/connections/service.py`;
add `login_kind: "password" | "oauth"` to `ConnectionOut`.

**Adapters (thin, per AGENTS.md).**
- REST: `POST /api/sync/strava`, `GET /api/sync/strava/status`,
  `DELETE /api/connections/strava`, plus authorize/callback.
- MCP: `sync_strava_now`, `get_strava_sync_status`. No MCP login.
- "Send workout to device" stays Garmin-only.

**Web.** `ConnectionCard.tsx` renders a "Connect with Strava" button when
`login_kind === "oauth"`; disconnect becomes provider-aware
(`api.disconnect(provider)`, today it always calls `garminDisconnect`).
Update `api/client.ts`, `api/types.ts`, and `i18n/en.ts`/`es.ts`. The
callback redirects to `/settings?connected=strava`.

## Steps

1. Add the dependency and settings; update the SECURITY.md token note.
2. Migration: `source`/`external_id`/constraint + `strava_sync_state`;
   `make docs-schema`.
3. Shared provider error base, then `strava/errors.py`.
4. `strava/client.py` with token refresh.
5. `strava/streams.py`, `ingest_strava_activity`, dedup.
6. `strava/sync.py`; generalize runners and lifespan.
7. Connections service, REST/MCP adapters, OAuth routes.
8. Web card, API client, i18n.
9. Docs: update `connected-apps.md`, add `product-specs/strava-sync.md`,
   amend the "dead end" notes in 0002 and `garmin-sync.md` to point here,
   and log deferred items in `tech-debt-tracker.md` (webhooks, backfill,
   `fit_status` rename).

## Verification

Tests follow the repo style: hand-written fakes, no mock library, temp
SQLite via `make_engine`.
- `tests/test_strava_client.py`: `FakeStravaLib` factory; token refresh
  and error mapping.
- `tests/test_strava_streams.py`: sensor flags for HR+power, HR only, and
  estimated power (`device_watts=False` → `has_power_data=False`).
- `tests/test_strava_sync.py`: cursor, first-run limit, cross-provider
  dedup against an existing Garmin row.
- Extend `test_connections.py`, `test_mcp_tools.py` (MCP/REST parity) and
  `test_migrations.py`.
- Add an autouse `_no_real_strava` guard in `tests/conftest.py`.

`make check` passes. Manual:
1. Create a Strava API app with callback
   `http://localhost:<port>/api/connections/strava/callback`.
2. `make dev-server` and `make dev-web`; Settings → Connect with Strava.
3. `POST /api/sync/strava` returns the latest ride; `GET /api/activities`
   shows `source="strava"`.
4. Training load updates, and a Garmin duplicate does not appear.
