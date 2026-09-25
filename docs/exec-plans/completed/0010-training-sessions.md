# 0010 — Training sessions: "what should I ride tomorrow?"

## Context

The coach only gives advice in chat today — nothing recommends a specific
session, and nothing produces a workout a rider can load onto a device.
This adds an optional Training section: the rider says which device(s)
they train with (Garmin Edge, Wahoo, Zwift, other), what they have in
mind for their next ride (day, minutes available, indoor/outdoor,
discipline — road/MTB/gravel — and a free-text idea like "hill repeats at
Patios, Bogotá"), and gets back one structured workout that blends what
they asked for with what their recent training load and goal suggest.
The workout can be pushed straight to Garmin Connect (syncs to the Edge
or a paired smart trainer) or downloaded as a file for Wahoo, Zwift and
other head units.

Done means: a rider can open Training, answer the short flow, get a
sensor-honest workout with a plain-language rationale, and either send it
to Garmin or download it. The same capability is reachable over REST,
MCP, and a coach tool.

## Design

See `docs/product-specs/training-sessions.md` for the user-facing
behavior, `docs/design-docs/sensor-capability-model.md` for the rule this
must not violate (never fabricate a sensor signal — no invented watts or
HR zones), and `docs/product-specs/coach-chat.md` for the agent
conventions (tools, budget, memory) this reuses.

**Core** (`packages/core/src/soft_floyd_core/training/`):

- `schemas.py` — `SessionRequest` (planned_date, available_minutes,
  setting: indoor/outdoor, discipline: road/mtb/gravel, bike_id,
  route_idea, feel) and `Workout` (name, steps, est_minutes). A step has a
  kind (warmup/interval/recovery/cooldown/repeat), an end condition
  (time/distance/lap_button — `lap_button` covers "until the top of the
  climb"), and a target (power_pct_ftp/hr_zone/cadence_range/rpe).
- `intent.py` — deterministic (no LLM): combines
  `activities.service.get_training_summary`, recent rides
  (`activities.service.list_activities`), and the profile (weekly
  targets, `available_days`, `focus_areas`, `target_event_date`, `feel`)
  into a `SessionIntent` — an emphasis (recovery/endurance/tempo/
  threshold/vo2/climbing) plus the plain reasons behind it.
- `sanitize.py` — enforces the sensor rule: no power target without a
  power meter on the chosen bike *and* `ftp_watts` set; no HR-zone target
  without `has_hr_monitor` *and* `lthr`/`max_hr`; no cadence target
  without a cadence sensor (falls back to an RPE cue); duration clamped
  to `available_minutes`.
- `generator.py` — builds the LLM context (profile, `SessionIntent`, the
  rider's own words, 2-3 book passages via
  `rag.service.get_training_context`), calls a new
  `LLMClient.chat_structured` (a parameterized generalization of
  `chat_json`, which becomes a thin `max_completion_tokens=50` wrapper
  around it), runs `ensure_within_budget`/`record_usage` exactly like the
  coach, then `sanitize.py` before persisting.
- `export.py` — pure, unit-tested functions: `to_garmin_payload` (built
  with `garminconnect.workout`'s typed builders —
  `CyclingWorkout`/`create_interval_step`/`create_repeat_group`, extended
  with `targetValueOne`/`targetValueTwo` watt/bpm ranges since the
  library ships no percent-of-FTP helper), `to_fit_workout` (the
  `fit-tool` package, which writes real FIT `workout`/`workout_step`
  messages — confirmed via its own `write_workout_example.py`), and
  `to_zwo`/`to_erg` (offered only when the workout carries power
  targets, since ERG-style files cannot be built honestly without them).
- `service.py` — CRUD plus `export_session` and `send_to_garmin`, which
  extends `garmin.client.GarminClient` with `upload_and_schedule_workout`
  and reuses the account's single `SyncRunner` (its lock + worker thread)
  the same way `sync_once()`/`login()` already do, so a workout push can
  never race a sync cycle.

**Data**: new `TrainingSession` table (account-owned, added to
`account_scope.OWNED_MODELS`) and `RiderProfile.workout_devices` (JSON
list). Migration down-revision `6767c65736c0`.

**Adapters** (thin, per `AGENTS.md`'s core/adapter rule):
REST `POST/GET /api/training/sessions`, `GET/PATCH/DELETE
/api/training/sessions/{id}`, `GET .../export`, `POST .../garmin`; MCP
`plan_training_session`/`list_training_sessions`/`get_training_session`/
`send_training_session_to_garmin`; a coach tool
`plan_training_session`/`list_training_sessions` in `coach/tools.py` so
"what should I ride tomorrow?" in chat produces the same persisted
session.

**Web**: a new `"training"` view, `pages/Training.tsx` (a short flow:
devices once, then when/how-long, where + discipline, route idea + feel),
`components/training/WorkoutCard.tsx` (steps, rationale, Send to
Garmin/Download/Regenerate/Mark done), a Dashboard entry point, and a
device field in Settings. New i18n keys under `training` in both `en.ts`
and `es.ts`.

## Steps

1. Docs (this plan + product spec), `docs/product-specs/index.md`,
   `AGENTS.md` current state.
2. Migration + `OWNED_MODELS`; `make docs-schema`.
3. `training/schemas.py`, `intent.py`, `sanitize.py` + unit tests.
4. `llm/client.py::chat_structured`; `training/generator.py` + tests with
   a fake LLM.
5. `training/export.py` (Garmin payload, FIT, ZWO, ERG) + golden tests;
   add `garminconnect[workout]` extra (already usable — pydantic is
   already a transitive dep) and `fit-tool` to `packages/core/pyproject.toml`.
6. `GarminClient.upload_and_schedule_workout`, `SyncRunner.send_workout`,
   `training/service.py::send_to_garmin`, tested with the fake
   `client_factory`.
7. REST, MCP, coach-tool adapters + adapter tests.
8. Web: types/client, `Training.tsx`, `WorkoutCard.tsx`, Dashboard entry,
   Settings device field, i18n.
9. `make check`; move this plan to `completed/`; tech-debt tracker entry
   for anything deferred; self-score against `docs/QUALITY_SCORE.md`.

## Verification

- `make check` (lint + tests, both stacks), including: a no-power-meter
  rider never gets watts or a ZWO/ERG export; an HR-only rider gets
  HR-zone targets; an outdoor climbing request yields `lap_button` steps;
  a round-trip `to_fit_workout` → `fitdecode` reads back the same steps.
- Manual: `make dev-server` + `make dev-web` → Dashboard → Plan a
  session → Garmin, tomorrow, 90 min, outdoor, road, "hill repeats at
  Patios", tired → expect an eased rationale. Send to Garmin and confirm
  the workout lands on tomorrow's date in Garmin Connect and syncs to the
  Edge. Download the .fit and open it with `fitdecode`; download the
  .zwo (power rider only) and import into Zwift/SYSTM. Switch to Spanish
  and confirm every string translates.
- MCP: `plan_training_session` with the same inputs as the REST call
  should return an equivalent session.
- `SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD=0` should 402 with a clear message.

## Result

- Built `packages/core/src/soft_floyd_core/training/`: `schemas.py`
  (request/intent/workout, plus the LLM's abstract "draft" shapes),
  `intent.py` (deterministic emphasis + reasons), `sanitize.py` (the one
  place a numeric target is allowed to exist — resolves %FTP/HR-zone/
  cadence-rpm against the rider's actual sensors/anchors, drops to a
  plain-language cue otherwise, and clamps duration to the ask),
  `generator.py` (prompt + `LLMClient.chat_structured` call, budget
  checked first), `export.py` (Garmin JSON via `garminconnect.workout`,
  a real FIT workout via `fit-tool` with correct
  `REPEAT_UNTIL_STEPS_CMPLT` repeat semantics, `.zwo`/`.erg`), and
  `service.py` (CRUD, regenerate, export gating, Garmin push).
- Added `llm/schema.py::to_strict_schema` — a general pydantic-model ->
  OpenAI-strict-JSON-Schema converter (nullable-not-omitted fields,
  `additionalProperties: false` throughout `$defs`) — and
  `LLMClient.chat_structured`, with `chat_json` now a thin 50-token
  wrapper over it.
- `TrainingSession` table + `RiderProfile.workout_devices`, migration
  `487fbddd43bf` (verified against the drift-guard test and a scratch-DB
  autogenerate round trip). `GarminClient.upload_and_schedule_workout`
  and `SyncRunner.send_workout` reuse the account's existing lock/thread
  pattern.
- REST (`/api/training/sessions*`), MCP (`plan_training_session`,
  `list_training_sessions`, `get_training_session`,
  `send_training_session_to_garmin`), and a coach tool
  (`plan_training_session`, `list_training_sessions`) all call the same
  `training/service.py` — verified equivalent with a cross-surface test
  in `tests/test_mcp_tools.py`.
- Web: `pages/Training.tsx` (devices step once, then a plan form, result
  card, upcoming/past lists), `components/training/WorkoutCard.tsx`,
  a Dashboard "Plan a session" button plus an upcoming-session card, and
  a Settings devices section. Full `en`/`es` coverage.
- `make check` passes: 200 backend tests (25 in `test_training.py`, 3 in
  `test_training_api.py`, plus new coach/MCP coverage), ruff lint +
  format, and the web `tsc` typecheck; `pnpm run build` also succeeds.
  Fixed an incidental break this migration caused in
  `book_copy.py` (its account-era check was hardcoded to the
  pre-existing head revision) by resolving the head dynamically instead.
- **Not verified live** (no Garmin test account or OpenAI spend in this
  session): an actual push to Garmin Connect and a real
  `chat_structured` call against OpenAI's API. The FIT output was
  validated with `fit_tool.validation.validate_fit_file` and a decode
  round-trip; the Garmin JSON payload's shape follows the reverse-engineered
  structure `garminconnect.workout`'s own builders use, extended with
  `targetValueOne`/`targetValueTwo` for custom ranges. Do the manual
  verification steps above before treating either as field-tested.

## Quality self-score

1. Correctness: automated verification (tests, schema/FIT validators,
   drift guard) all pass; the two live-network paths above are unverified
   pending real credentials.
2. Single source of truth: yes — REST/MCP/coach tool are thin adapters
   over one `training/service.py`, cross-surface-tested.
3. Sensor honesty: yes — `sanitize.py` is the only place a target is
   created, gated on the same sensor/anchor rules as the rest of the app;
   unsupported targets become an RPE cue, never a fabricated number.
4. Tests: yes — unit tests for sanitize/intent/export, generator/service
   tests with a fake LLM, REST/MCP/coach adapter tests, a cross-surface
   agreement test.
5. Docs kept honest: yes — `docs/product-specs/training-sessions.md`,
   `docs/product-specs/index.md`, this exec-plan, `AGENTS.md`, and
   `docs/generated/db-schema.md` are updated; a new tech-debt row covers
   what's deferred.
6. Scope discipline: mostly — added `RiderProfile.workout_devices`/
   `TrainingSession.sources` (a `sources` column beyond the original
   plan's field list) to support device selection and book citations
   properly rather than skipping them; both were implied by the plan's
   Design section, not scope creep beyond it.
7. Local-only, account-safe: yes — `TrainingSession` is in
   `account_scope.OWNED_MODELS`; the Garmin push reuses the existing
   per-account `SyncRunner`.
