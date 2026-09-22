# 0004 — Rider Profile, Garage, and Connected Apps UI

## Context

Soft Floyd's onboarding (`apps/web/src/pages/Onboarding.tsx`) asks four
questions: weekly volume, a free-text goal, four sensor checkboxes, FTP/LTHR.
That is enough to pick a `capability_tier`, but it is nowhere near what a
coach would ask a rider who "just rides" and wants to get better. It also
can't express the things this rider actually owns: a gravel bike, a second
bike without a power meter, an indoor trainer.

Three concrete gaps prompted this plan:

1. **The questions are too thin to coach from.** Nothing captures
   experience, availability, body metrics, or *what kind of better* the
   rider wants. Core belief 3 ("the rider's stated goal shapes what good
   means") is currently backed by one untyped text field.
2. **Sensors are modeled on the rider, not on the bike.** `has_power_meter`
   is a single boolean, so "power meter on the road bike, nothing on the
   MTB" is unrepresentable — and that is the normal case. Gravel isn't a
   discipline at all today (`Discipline = road | mtb`).
3. **There is no way to edit anything after first run, and no connection
   UI.** The settings screen is an open item in
   `docs/exec-plans/tech-debt-tracker.md`, which puts the repo in direct
   violation of `sensor-capability-model.md` rule 5 ("sensors are editable,
   and the tier moves immediately"). Garmin can only be connected from an
   interactive CLI.

**Done means:** a rider can complete a coach-shaped onboarding, describe a
garage of bikes with per-bike sensors, connect Garmin from the browser, and
change every one of those answers later from a settings screen — with
`capability_tier` moving the moment they do.

Out of scope: the dashboard / ride list (its own plan, per the tracker),
sign-in (no auth today — `docs/SECURITY.md`; Google sign-in is a possible
future, not now), metrics computation.

## Design

### One source of truth for sensors: the garage

New `bike` table. **Bike-mounted** sensors move onto it; **body-worn** HR
stays on `RiderProfile` (a strap is not a bike accessory). A smart trainer
is just a bike with `kind="indoor"` and `has_power_meter=True` — no
separate trainer concept.

```
bike
  id            int PK autoincrement
  nickname      str                      "Tarmac", "the gravel bike"
  kind          road | gravel | mtb | tt | indoor
  is_primary    bool                     exactly one True, enforced in service
  has_power_meter, has_cadence_sensor, has_speed_sensor   bool
  created_at, updated_at
```

`RiderProfile` **loses** `has_power_meter` / `has_cadence_sensor` /
`has_speed_sensor` / `primary_discipline` as stored columns and **keeps**
`has_hr_monitor`, `ftp_watts`, `lthr`.

Critically, `ProfileOut` keeps all four `has_*` fields and
`primary_discipline` as **derived, read-only** values — the union of the
garage's sensors, and the primary bike's kind. This keeps the blast radius
small: `available_metrics_for_activity()`, the MCP tools,
`CapabilitySummary`, and the coach's future prompt all keep reading the
same field names. Only `ProfileIn` changes: those fields become
non-writable, and writes go through the bikes endpoints instead.

`capability_tier()` in
`packages/core/src/soft_floyd_core/profile/service.py` gains a `bikes`
argument and unions over them. Add a sibling
`capability_tier_for_bike(bike, profile)` — the onboarding summary should
be able to say *"power on the road bike, heart rate only on the MTB"*,
which is core belief 4 (downgrade visibly) applied to hardware.

### New profile fields

All optional, all skippable in the UI, all rendered into the coach's
context later.

| Block | Fields |
|---|---|
| Focus | `focus_areas` (JSON list: `endurance`, `climbing`, `flat_speed`, `sprint`, `technical_skill`, `weight`, `first_event`, `consistency`, `enjoy`), `goal_text` (kept), `target_event_name`, `target_event_date` (kept) |
| Experience | `years_riding`, `longest_recent_ride_km`, `followed_plan_before`, `self_rated_level` (`beginner`/`recreational`/`enthusiast`/`competitive`) |
| Availability | `available_days` (JSON list of `mon`…`sun`), `weekday_max_minutes`, `weekend_max_minutes` |
| Body & health | `birth_year` (not age — doesn't go stale), `weight_kg`, `max_hr`, `health_notes` |

`hasCompletedOnboarding()` stays gated on `goal_text`, so the existing gate
in `App.tsx` is unchanged.

### Connected apps: an abstraction, backed by what exists

**No new table.** Garmin's state already lives in `GarminSyncState`. Add
`packages/core/src/soft_floyd_core/connections/service.py` exposing a
provider-shaped read model assembled from `GarminSyncState` +
`GarminClient.has_token()`:

```python
class ConnectionOut(BaseModel):
    provider: str  # "garmin"
    display_name: str  # "Garmin Connect"
    status: str  # connected | disconnected | reauth_required
    # | rate_limited | error
    last_sync_at: datetime | None
    last_error: str | None  # human-readable only — never a token
    supports_login_in_app: bool
    detail: str | None  # e.g. "polls every 10 min"
```

Adding Strava/Wahoo later means adding a provider module and a row to the
list — the UI renders the list generically and never mentions Garmin by
name except in the login form component.

### Garmin login in the browser

`GarminClient.login()` takes a **blocking** `mfa_callback`, and
`garmin.login.perform_login()` owns the 30-minute 429 cooldown
(exec-plan 0003). Rather than rewrite either, run the login on a worker
thread and have the MFA callback block on a `threading.Event`:

1. `POST /api/connections/garmin/login {email, password}` → starts the
   login on a worker thread via `SyncRunner` (so it takes the same
   `asyncio.Lock` and can never race a poll cycle), and registers an
   in-process `PendingLogin`.
2. If Garmin asks for MFA, `mfa_callback` blocks on the event (bounded,
   ~120 s) and the route returns `{state: "mfa_required"}`.
3. `POST /api/connections/garmin/mfa {code}` sets the code, releases the
   event, waits for the thread → `{state: "connected"}` or
   `{state: "failed", message}`.
4. No MFA needed → step 1 returns `{state: "connected"}` directly.
5. `DELETE /api/connections/garmin` → `GarminClient.logout()`.

Because login goes through `SyncRunner`'s own `GarminClient`, the
background poller resumes on the next tick with no server restart.

`PendingLogin` lives in process memory only, holds a deadline, and is
discarded on completion/timeout. The password exists only in the request
body and the worker thread's frame; it is never written to the DB,
config, or a log line.

**A note on the tradeoff, since it moves a line `docs/SECURITY.md`
currently draws:** today the Garmin password is typed into a TTY and
never leaves the process. After this it crosses a loopback HTTP boundary
in a POST body. On a 127.0.0.1-bound, single-user, no-auth app the
practical exposure is small (no TLS to strip, CORS still pinned to the
Vite dev origin, nothing persisted), but it is a real change and
`docs/SECURITY.md` must be rewritten **in this change**, not after it.
The CLI `garmin-login` stays as the fallback path.

### MCP surface

Bikes get full MCP parity (`list_bikes`, `add_bike`, `update_bike`,
`delete_bike`) — they're domain state the coach should be able to read.
Connections get **read-only** parity (`get_connections`). There is
deliberately no MCP login tool: routing a Garmin password through an
LLM's tool-call is not worth the convenience. The AGENTS.md rule is that
domain logic lives in `packages/core` — not that every REST route needs
an MCP twin — so the cross-surface agreement test asserts agreement on
reads only, with a comment saying why.

### Web structure

No router dependency. `App.tsx` keeps its profile gate and adds a
`useState<"dashboard" | "settings">` — two destinations don't justify
react-router yet (`docs/FRONTEND.md`: reach for a library when the
scaffold visibly strains). Note it as the upgrade point when a third
route lands.

The field components are written once and mounted twice — onboarding
walks them as steps, settings stacks them as sections. That is what makes
rule 5 cheap to honor.

Onboarding order follows `docs/DESIGN.md` (volume and goals before
sensors; never ask for a number the rider can't produce):

| # | Step | Skippable |
|---|---|---|
| 1 | **Habits** — rides/week, hours/week, available days, weekday vs weekend max | no |
| 2 | **Goals** — focus chips + free text + optional target event & date | no (`goal_text` gates completion) |
| 3 | **Garage** — add bikes; kind, nickname, per-bike sensors; "I ride indoors" adds an indoor bike | no (≥1 bike) |
| 4 | **About you** — birth year, weight, years riding, self-rated level, followed a plan before, health notes | every field |
| 5 | **Anchors** — FTP only if some bike has power; LTHR/max HR only if `has_hr_monitor` | yes |
| 6 | **Connect** — the Garmin connection card | yes |
| 7 | **Summary** — overall tier + per-bike tier lines | — |

## Steps

1. **Docs.** This file, plus `docs/product-specs/new-user-onboarding.md`
   rewritten for the 7-step flow, a new
   `docs/product-specs/connected-apps.md`, and
   `docs/design-docs/sensor-capability-model.md` updated (tier unions the
   garage; per-bike tier; rule 3 restated against `bike.has_power_meter`).
2. **Model + migration.** Add `Bike` to
   `packages/core/src/soft_floyd_core/models.py` with a `BikeKind`
   literal — leave the existing `BikeType` (the FIT-derived activity
   classification in `activities/classify.py`) alone; they are different
   axes and must not be merged. One Alembic revision that: creates
   `bike`, adds the new profile columns, **seeds one bike** from the
   existing profile row (kind from the old `primary_discipline`, sensors
   from the old three booleans, `is_primary=True`), then drops the four
   superseded columns. Use `batch_alter_table` — SQLite has no `DROP
   COLUMN` in older paths. Read the autogenerated file before trusting
   it; the seed step is hand-written.
3. **Core: bikes service.** New
   `packages/core/src/soft_floyd_core/bikes/service.py` —
   `BikeIn`/`BikeOut`, list/create/update/delete, and the invariant that
   exactly one bike is primary (promote another on delete; refuse
   deleting the last bike). `BikeOut` carries its own `capability_tier`.
4. **Core: profile service.** Extend `ProfileIn`/`ProfileOut` with the
   new fields; make the four `has_*` + `primary_discipline` derived on
   `ProfileOut` and remove the three bike-sensor fields from `ProfileIn`.
   Change `capability_tier(profile, bikes)` and add
   `capability_tier_for_bike`. This file stays the single implementation
   both adapters call.
5. **Core: connections service.** New
   `packages/core/src/soft_floyd_core/connections/service.py` with
   `ConnectionOut` and `list_connections(session, settings, client)`,
   mapping `GarminSyncState.last_status` + token presence onto `status`.
   Reuse `activities/service.py`'s `get_sync_status` rather than
   re-querying.
6. **Core: browser login.** Add `PendingLogin` + `start_login` /
   `submit_mfa` to `soft_floyd_core/garmin/login.py`, wrapping the
   existing `perform_login` so the 429 cooldown and `GarminRateLimited`
   mapping are inherited, not reimplemented. Add `SyncRunner.login()` /
   `.submit_mfa()` in `garmin/sync.py` so the login shares the existing
   lock and client instance.
7. **Adapters.** `apps/server/.../http_api.py`: `GET/POST/PATCH/DELETE
   /api/bikes`, `GET /api/connections`, `POST /api/connections/garmin/login`,
   `POST /api/connections/garmin/mfa`, `DELETE /api/connections/garmin`.
   `mcp_server.py`: the four bike tools + `get_connections`. Both stay
   thin.
8. **Web: API layer.** `apps/web/src/api/types.ts` (mirror the new
   `ProfileOut`, add `BikeOut`/`BikeIn`/`ConnectionOut` — field names
   identical to the API) and `api/client.ts` (one function per new
   endpoint).
9. **Web: shared field components.** `components/BikeEditor.tsx`,
   `components/FocusPicker.tsx`, `components/AvailabilityPicker.tsx`,
   `components/connections/ConnectionCard.tsx`,
   `components/connections/GarminLoginForm.tsx` (email/password → MFA →
   connected, surfacing the cooldown message verbatim on a 429).
10. **Web: onboarding.** Rewrite `pages/Onboarding.tsx` as the 7 steps
    above with a progress indicator; new `HabitsStep`, `GoalsStep`,
    `GarageStep`, `AboutYouStep`, `ConnectStep`; update `AnchorsStep`'s
    condition to "any bike has power". Extend `CapabilitySummary.tsx`
    with per-bike lines.
11. **Web: settings.** New `pages/Settings.tsx` — the same components as
    stacked sections, each saving independently. Add the
    dashboard↔settings toggle in `App.tsx`.
12. **Docs + debt.** Rewrite `docs/SECURITY.md`'s Garmin section for the
    browser login. Update `docs/FRONTEND.md`'s component map. Run
    `make docs-schema`. In `docs/exec-plans/tech-debt-tracker.md`: remove
    the "Settings screen" row, and add the deferrals —
    `classify.py` still maps gravel rides to `mtb` (the activity
    classifier isn't garage-aware yet); rides aren't linked to a specific
    `bike` row; no per-bike FTP.

## Verification

```bash
make check                               # lint + tests, both stacks
uv run alembic upgrade head              # against a pre-0004 DB with a seeded
                                         # profile → exactly one bike, flags carried
make docs-schema && git diff --stat docs/generated/db-schema.md
```

Tests to write:

- `tests/test_capability_tier.py` — rewrite the matrix over a garage. Keep
  rule 3: a stale `ftp_watts` with no power-meter bike must **not** grant
  `power`. Keep `test_power_tier_still_includes_hr_metrics`.
- `tests/test_bikes_api.py` — CRUD; exactly-one-primary invariant;
  promotion on delete; refusing to delete the last bike; adding a
  power-meter bike flips `GET /api/profile`'s `capability_tier` to
  `power` on the very next read (rule 5).
- `tests/test_connections.py` — `list_connections` status mapping for
  each `GarminSyncState.last_status`; the login state machine against the
  existing fake client seam (`client_factory`) covering no-MFA, MFA,
  wrong code, MFA timeout, and a 429 surfacing the cooldown message.
- `tests/test_migrations.py` — extend with the seed assertion from above.
- `tests/test_mcp_tools.py` — bike tools agree with REST; `get_connections`
  agrees with `GET /api/connections`; assert no MCP login tool exists.

Manual end-to-end (`make dev-server` + `make dev-web`):

1. Delete `data/soft-floyd.db` → onboarding runs. Walk all 7 steps,
   adding a road bike with a power meter and an MTB without → summary
   shows `power` overall and `hr` for the MTB specifically.
2. On step 6, connect Garmin with a real account → MFA prompt appears in
   the browser, code accepted, card shows "Connected". "Sync now"
   returns rides. Confirm the background poller picks up on the next
   tick with no restart.
3. Open Settings → remove the power meter from the road bike → reload →
   `capability_tier` is `hr` and the FTP field is gone (rule 5, and
   `PRODUCT_SENSE.md`'s "no power UI for a rider without a power meter").
4. `grep -ri "password" data/ ~/.soft-floyd/` and the server log output →
   nothing.

## Status

Implemented. All steps landed: `Bike` model + migration (with the
data-seeding step, verified against a scratch DB both manually and in
`tests/test_migrations.py`), `bikes`/`connections` core services,
`SyncRunner.login`/`submit_mfa`'s browser MFA handshake, the REST/MCP
adapters, and the full 7-step onboarding + `Settings.tsx` + Connected
Apps UI. `make check` (136 backend tests + web typecheck/build) is
green; a live server smoke test confirmed the bike-add → tier-flip →
delete-refusal → `ProfileIn` extra-field-rejection chain over real HTTP.

One planned deliverable was deliberately dropped rather than shipped
half-built: manual end-to-end verification against a **real** Garmin
account (item 2 in Verification above) wasn't run — this session had no
live Garmin credentials available. The login handshake is covered
end-to-end against a fake client
(`tests/test_connections.py`), but a real Garmin SSO chain (including
its actual MFA prompt shape) has not been exercised through the new
browser path. Revisit before relying on it for a real account, or ask
the rider to confirm it works while `soft-floyd garmin-login` (the CLI
path, unchanged and still fully functional) remains the fallback.
