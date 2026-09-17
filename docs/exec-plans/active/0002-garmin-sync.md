# 0002 — Garmin Activity Sync

## Context

The scaffold (0001) shipped a rider profile with sensor capability
tiering, but `list_activities`/`GET /api/activities` were permanent
stubs returning `[]`. This plan wires up real Garmin data.

**Why this shape** — researched and decided at the start of this plan:
- Garmin's own Developer Program is enterprise/legal-entity-only, no
  personal tier. Not usable.
- Strava's 2026 API agreement prohibits using their data "in connection
  with the development, training, evaluation, or operation of any AI
  Application." Not usable as an alternative source — don't reach for it
  later either.
- **Decision: `python-garminconnect` directly** (unofficial,
  reverse-engineered, free, actively maintained — 0.3.15 at plan time).
  Not intervals.icu, not an abstract multi-source port.
- `garth` (v0's auth dependency) was deprecated 2026-03-27 after Garmin's
  Cloudflare TLS fingerprinting broke its auth flow.
  `python-garminconnect` decoupled from it, moving to its own
  `curl_cffi`-based login with a built-in token cache. v0's Fernet+Keychain
  wrapper around a garth token dump does not port — see
  `docs/SECURITY.md` for why we deliberately don't re-wrap the new
  library's token cache either.
- **Scope: automatic sync only.** No manual `ingest-fit <path>` CLI, no
  historical backfill, no wellness/HRV sync. Background poller + a manual
  "sync now" (MCP/REST/CLI), using a one-time interactive
  `soft-floyd garmin-login`.
- **Metrics computation (HR zones, TRIMP, decoupling, FTP/NP/TSS) is out
  of scope** — that's `docs/design-docs/training-signal-model.md`'s
  concern, a future exec-plan. This plan's job: get real ride data in,
  correctly classified, with accurate per-ride sensor-presence flags.

"Done" means: a ride that finishes on the Edge and syncs to Garmin
Connect appears in `list_activities`/`GET /api/activities` within one
poll interval, with the correct `bike_type` and honest per-activity
sensor flags; a Garmin auth failure surfaces as an actionable message and
a queryable status, never a silent retry loop.

## What v0 got right vs. what was fixed, not carried forward

Verified by reading `v0-legacy` directly. Salvaged the shape, fixed:

- **Cursor nulled on every error** (v0) → fixed: `GarminSyncState.last_seen_activity_id`
  only advances on success, never reset on a transient failure.
- **Mid-loop `ReauthRequired` backed off forever** (v0) → fixed: the
  poller re-checks at a fixed ≥15-minute interval instead, notifying once
  on transition into the state (not every cycle), and doesn't count
  toward the error-backoff used for real API errors.
- **Classifier rule 1 was dead code** (v0 read `summary["is_indoor"]`,
  real Garmin summaries use `"isIndoor"`) → fixed to read the correct
  key.
- **`RecordData` had no `power` field**, and the fixture generator had
  `altitude`/`speed` FIT field numbers swapped (verified against
  `fitdecode`'s own profile data) → fixed the generator, added
  `power_w`/cadence throughout the parser and schema.
- **Synchronous Garmin/FIT calls ran directly inside the async poller**,
  blocking `/mcp` and `/api` for the whole cycle → fixed: `run_sync_cycle`
  is a plain sync function called via `anyio.to_thread.run_sync`.
- **First sync silently mini-backfilled** (empty cursor → up to
  `page_size` activities ingested) → fixed: bounded to the single most
  recent activity (`FIRST_RUN_INGEST_LIMIT`); historical backfill is
  explicitly out of scope (tech-debt-tracker.md).

## Design

### Package layout

```
packages/core/src/soft_floyd_core/
  garmin/            the source adapter — everything that knows Garmin exists
    errors.py        GarminApiError + ReauthRequired/GarminRateLimited/GarminNotFound
    client.py        GarminClient (wraps garminconnect.Garmin)
    sync.py          run_sync_cycle() + SyncRunner (lock, thread, backoff loop)
  activities/        the domain — knows nothing about Garmin
    fit_parser.py    parse_fit() -> ParsedFit (ported from v0, + power/cadence)
    classify.py      classify() -> BikeType (ported from v0, rule-1 key fixed)
    sensors.py       detect_sensor_streams() — the rule-1 enforcement point
    pipeline.py      ingest_activity() (ported from v0, metrics/wellness/embed removed)
    service.py       read queries + Pydantic Out models + available_metrics_for_activity
```

The dependency direction is `garmin -> activities`, never the reverse:
`activities/pipeline.py` depends on a `FitSource` `Protocol`
(`download_fit(activity_id, dest_path) -> Path`), which `GarminClient`
satisfies structurally. Every pipeline/classifier/parser/sensor test runs
against a five-line fake with no `garminconnect` import anywhere near it.

### Token storage

`python-garminconnect`'s own token cache, pointed at
`settings.garmin_token_dir` (default `~/.soft-floyd/garmin/`) — not
wrapped in Fernet/Keychain encryption. See `docs/SECURITY.md` for the
reasoning (an encrypted wrapper breaks the library's silent refresh).

### Blocking I/O

`garminconnect` and `fitdecode` are synchronous. `run_sync_cycle` is a
plain function; `SyncRunner` (the only async code in `garmin/sync.py`)
calls it via `anyio.to_thread.run_sync`, keeping the server responsive
during a sync.

### Sensor honesty

`activities/sensors.py`'s `detect_sensor_streams` takes a `ParsedFit` and
returns booleans for power/hr/cadence/speed/gps. Presence rule: at least
one record with a value that is both non-`None` and greater than zero
(GPS: lat and lon both present) — an all-zero channel (an unpaired sensor
slot some head units write) doesn't count as present. The module never
imports `RiderProfile`/`profile`/`Settings` (enforced by an AST-based
static-scan test, not just a docstring). `Activity.fit_status`
distinguishes `pending`/`ok`/`download_failed`/`parse_failed`/`missing` —
the `has_*_data` flags are only meaningful when it's `"ok"`.

`activities/service.py`'s `available_metrics_for_activity` intersects the
rider's profile-level allowlist with what this specific ride's streams
actually support (`_STREAM_BY_METRIC`), so the per-ride view is never
wider than what was actually recorded — see
`tests/test_ingest_pipeline.py`'s rule-1 regression test.

### Schema (Alembic, introduced here)

Alembic replaces `Base.metadata.create_all()`
(`packages/core/src/soft_floyd_core/db.py`'s `run_migrations`, called
from `make_engine`) — batch mode (`render_as_batch=True`) since SQLite
can't `ALTER`. `run_migrations` handles three cases: a fresh file
(`upgrade head`), an existing pre-Alembic DB recognizable by having
`rider_profile` but no `alembic_version` (create the newer tables once,
then `stamp head`), and an already-stamped DB (`upgrade head`, a no-op if
current). One baseline migration covers everything (`RiderProfile` plus
the new tables), since nothing had ever been deployed under Alembic
before this.

New tables: `Activity` (Garmin activityId as PK; sport/sub_sport/bike_type;
distance/duration/elevation; avg/max HR; avg/max power; avg cadence; the
five `has_*_data` flags; `fit_status`; `fit_path`; `record_count`;
`records_stored`; `raw_summary_json`), `Lap`, `Record` (per-sample time
series, size-gated at ~3MB estimated like v0, now including `power_w`),
`GarminSyncState` (single row: `last_seen_activity_id`, `last_sync_at`,
`last_status`, `last_error`, `consecutive_errors` — durable sync health,
not just a cursor, so `GET /api/sync/garmin/status` can distinguish
"Garmin is down" from "no rides yet").

### Config

New `Settings` fields: `garmin_email`, `garmin_token_dir`, `fit_dir`,
`garmin_poll_enabled`, `poll_interval_minutes`, `poll_max_backoff_minutes`,
`garmin_page_size`. No `garmin_password` field — prompted once by the CLI,
never persisted.

### Adapters

- `runtime.py`: `get_sync_runner()` — an `lru_cache`d `SyncRunner`
  singleton, mirroring `get_session_factory()`.
- `lifespan.py` (new): `poller_lifespan` starts/stops the background
  poller task.
- `main.py`: the app's first non-MCP startup/shutdown hook — merged with
  FastMCP's own lifespan via `combine_lifespans` (verified against the
  installed `fastmcp==4.0.4`; see `docs/references/fastmcp-notes.md`).
- `mcp_server.py` / `http_api.py`: `list_activities`/`get_activity` now
  query real data; new `sync_garmin_now`/`POST /api/sync/garmin` (manual
  trigger) and `get_garmin_sync_status`/`GET /api/sync/garmin/status`.
  Every handler is a `session_scope` + one `activities_service`/`garmin.sync`
  call — no logic duplicated between the two surfaces (tested by
  `tests/test_mcp_tools.py`'s cross-surface agreement tests).
- `cli.py`: `garmin-login` (interactive email/password/MFA,
  hidden-input password, never persisted), `garmin-logout`, `garmin-sync`
  (one-shot cycle without starting the server).

### Testing strategy

`python-garminconnect` transports over `curl_cffi`, not `httpx` — `respx`
would not intercept anything. Every Garmin-touching test mocks at the
`garminconnect.Garmin` **object** boundary instead, via a `client_factory`
constructor parameter on `GarminClient`. An autouse fixture
(`tests/conftest.py`) additionally patches `garminconnect.Garmin.__init__`
itself (not the name imported into `client.py` — a default-argument value
is bound once at function-definition time, so patching only the
module-level alias would silently miss it) to raise if a test ever
constructs a real client without an explicit fake.

New test files: `test_garmin_errors.py`, `test_garmin_client.py`,
`test_fit_parser.py`, `test_bike_type.py`, `test_sensor_streams.py`,
`test_ingest_pipeline.py`, `test_sync_cycle.py`, `test_activities_api.py`,
`test_lifespan.py`, `test_migrations.py`; extended `test_mcp_tools.py`.
82 tests total pass with no network access.

## Verification

```bash
uv sync && make check                 # 82 tests pass, no network access
uv run soft-floyd serve &
curl -s localhost:8000/api/health
curl -s localhost:8000/api/activities                 # []
curl -s localhost:8000/api/sync/garmin/status         # authenticated:false, last_status:"never"
curl -s -X POST localhost:8000/api/sync/garmin        # 200, status:"reauth_required"
```

Confirmed live: server boots, background poller runs one cycle at
startup and correctly records `reauth_required` (no token yet) without
looping tightly; SIGTERM shuts down cleanly with no dangling-task
warning. MCP surface confirmed via `fastmcp.Client` in-process tests
(`test_mcp_tools.py`) rather than the external inspector CLI this time,
since the cross-surface agreement tests already exercise real HTTP-free
round-trips against both adapters.

**Live check against a real Garmin account requires the rider's own
credentials** — not something an implementing agent can supply:

```bash
uv run soft-floyd garmin-login
uv run soft-floyd garmin-sync
curl -s localhost:8000/api/activities | jq '.[0] | {id, bike_type, sensors_present, fit_status}'
```

## Bug caught and fixed during verification

`notify.py`'s AppleScript notification used Python's `repr()` (single-quoted)
for the message string, but AppleScript string literals are double-quoted
— every real notification failed with a silent `osascript` syntax error
in the logs. Caught by actually running the server and reading its
output, not just by unit tests (which mocked past `notify()` entirely).
Fixed with a proper double-quote escaper.

## Status

Implemented. See `docs/exec-plans/tech-debt-tracker.md` for what remains
deliberately out of scope (backfill, manual FIT upload, wellness sync,
metrics computation, web UI for activities).
