# Soft Floyd — Agent Operating Manual

Soft Floyd is a sensor-aware AI cycling coach. It ingests rides from a
Garmin Edge device, reasons about training load using whatever sensors the
rider actually has, and coaches through an authenticated MCP surface and
a small web UI. Multiple account-owned riders, runs locally.

This file is the entrypoint for any agent (human or AI) working in this
repo. Read it before writing code.

## Before you implement anything

1. Read the relevant docs first:
   - `docs/design-docs/` for *why* — the beliefs and models that constrain
     design decisions. Start with `core-beliefs.md` and, for anything
     touching metrics or coaching output, `sensor-capability-model.md`.
   - `docs/product-specs/` for *what* — the user-facing behavior a feature
     must satisfy.
   - `ARCHITECTURE.md` for *where* — which package/app a change belongs in.
2. Write an exec-plan in `docs/exec-plans/active/` before substantial
   implementation (see `docs/PLANS.md` for the format). Small fixes and
   pure refactors don't need one; new features and schema changes do.
3. When you finish a phase of an exec-plan, move it to
   `docs/exec-plans/completed/` and update `docs/exec-plans/tech-debt-tracker.md`
   with anything you deliberately deferred.

## Non-negotiable rules

- **Never fabricate a sensor signal.** If the rider has no power meter, do
  not estimate watts and present it as power. See
  `docs/design-docs/sensor-capability-model.md` — every metric is gated by
  hardware, and per-activity analysis must check the actual FIT stream,
  not just the profile's declared sensors.
- **All domain logic lives in `packages/core`.** `apps/server`'s
  `mcp_server.py` (MCP tools) and `http_api.py` (REST routes) are both
  thin adapters that call the same `soft_floyd_core` functions. If you
  find yourself writing a rule inside either adapter, move it into core
  and call it from both. This is what keeps the MCP and REST surfaces
  from drifting apart.
- **Account isolation, local-only.** Every rider-data operation must run
  under the authenticated account; books are the shared corpus. The server
  binds to `127.0.0.1` by default. See `docs/SECURITY.md`.
- **Garmin access is unofficial and will occasionally break.** Map
  auth/rate-limit failures to actionable errors, never silently retry
  forever. See `docs/RELIABILITY.md`.
- **LLM cost cap ~$5-10/month.** Model is pinned to OpenAI `gpt-4.1-mini`
  (chat) and `text-embedding-3-small` (embeddings) in
  `packages/core/src/soft_floyd_core/llm/client.py`. Every paid call's
  `Usage` must be persisted with `llm/usage.py::record_usage` — the coach
  refuses new turns once month-to-date spend reaches
  `SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD` (default 10). Don't call the OpenAI
  SDK directly from elsewhere.
- **Alembic is the only way schema changes.** `packages/core/src/soft_floyd_core/db.py`'s
  `run_migrations` handles it (`uv run alembic revision --autogenerate`,
  then read the generated file before trusting it). Never add
  `Base.metadata.create_all()` back for a new table.
- Self-score a change against `docs/QUALITY_SCORE.md` before calling it done.

## Common commands

```bash
make setup          # uv sync + pnpm install
make dev-server      # uv run soft-floyd serve --reload
make dev-web         # cd apps/web && pnpm dev
make check           # lint + test, both stacks
make docs-schema     # regenerate docs/generated/db-schema.md
```

## Current state

- **0018-first-open-tour** (built; signed-in visual review pending): a six-step spotlight walkthrough starts
  after new-rider setup and can be replayed from Help. The Overview checklist
  remains available. See `docs/product-specs/help-and-first-use.md`.
- **0017-aws-deployment** (built; not yet deployed, so the plan is still in
  `docs/exec-plans/active/`): `infra/` Pulumi program (S3 + CloudFront UI,
  one t4g.nano EC2 backend, SSM secrets, nightly S3 backups), a `Dockerfile`,
  and an origin-verify guard. See `infra/README.md`.

- **0016-suggested-training** (done; signed-in visual review pending):
  Training accepts optional outdoor area, terrain and starting altitude,
  and offers an evidence-led suggestion from recent verified rides, load
  and imported books. Suggestions can be saved workouts or unsaved rest
  advice with an easy-ride alternative. REST and MCP share core logic.
  See `docs/product-specs/suggested-training.md`.
- **0015-help-and-first-use** (done; signed-in visual review pending): a
  dismissible guide after onboarding, a Help/FAQ page, and tappable
  explanations in Settings and training load. English and Spanish UI copy;
  browser-local, account-keyed dismissal. See
  `docs/product-specs/help-and-first-use.md`.
- **0014-signed-in-ui-redesign** (done; live-account review pending): a
  premium cycling editorial theme, shared desktop/mobile navigation, a
  connect-first empty dashboard, and refreshed signed-in screens. Login
  and backend behavior are unchanged. See `docs/FRONTEND.md`.

- **0013-edit-planned-sessions** (built; manual checks pending, so the plan
  is still in `docs/exec-plans/active/`): a planned session can be edited
  from its card (Training page and coach chat) or by asking the coach —
  date, minutes, setting, discipline, bike, idea, feel. A date-only edit
  just moves it; anything else rebuilds the workout with one LLM call. REST
  `PATCH /api/training/sessions/{id}`, MCP `update_training_session`. See
  `docs/product-specs/training-sessions.md`.
- **0012-training-load-model** (done; live checks still pending, see the
  tech-debt tracker): fitness/fatigue/form (CTL/ATL/TSB)
  from the rider's own rides, each scored from the best stream that ride
  verified (NP power, average power, HR zones, average HR, else a labelled
  duration estimate). Over REST (`/api/training/load`), MCP, a coach tool
  and a Dashboard card; once there are about 6 weeks of history it also
  steers session emphasis in `training/intent.py`. See
  `docs/product-specs/training-load.md`.
- **0011-coach-plans-sessions** (done): the coach asks for what the Plan a
  session form would (inferring what it can from the rider's words), plans
  the session, and the chat shows it as a workout card with downloads and
  Send to Garmin; the card survives a reload. See
  `docs/product-specs/coach-chat.md`.
- **0010-training-sessions** (done): an optional Training section — the
  rider says their device(s), and what they have in mind for their next
  ride (day, minutes, indoor/outdoor, discipline, a free-text idea, how
  they feel); the coach blends that with a deterministic read on their
  recent load/goal into one sensor-honest structured workout, over REST,
  MCP, and a coach tool. Push to Garmin Connect (scheduled, synced to the
  Edge/trainer) or download `.fit`/`.zwo`/`.erg`. See
  `docs/product-specs/training-sessions.md`.
- **0009-google-accounts** (done): Google registration/sign-in, revocable
  JWT sessions, account-owned rider data, protected MCP tools for the web
  coach, a shared book corpus, and simple Profile. See
  `docs/product-specs/google-accounts.md`.

- **0001-scaffold** (done): rider profile with sensor capability tiering,
  end-to-end across MCP, REST, and the web onboarding flow.
- **0002-garmin-sync** (done): automatic Garmin activity sync — background
  poller + manual sync (MCP/REST/CLI), FIT parsing, bike classification,
  per-activity sensor-presence detection. See
  `docs/product-specs/garmin-sync.md`. Auth is `soft-floyd garmin-login`
  (one-time, interactive).
- **0005-tiny-book-rag** (done): local PDF book import, SQLite-backed
  semantic passage retrieval, and verified latest-ride context through
  MCP and REST. See `docs/product-specs/training-book-retrieval.md`.
  Book imports checkpoint passages so interrupted imports can resume;
  incomplete books are hidden from retrieval.
- **0004-rider-profile-and-connections-ui** (done): coach-shaped
  onboarding (habits, goals, a per-bike garage, about-you, anchors,
  connected apps), a post-onboarding Settings screen, and a
  provider-generic Connected Apps panel with Garmin browser login. See
  `docs/product-specs/new-user-onboarding.md` and
  `docs/product-specs/connected-apps.md`. Bike-mounted sensors
  (power/cadence/speed) now live on a `Bike` per rider garage row rather
  than flat on `RiderProfile` — see
  `docs/design-docs/sensor-capability-model.md`.
- **0005-rider-ui-and-history** (done): responsive onboarding, Settings,
  and dashboard UI; latest ride plus cursor-paginated history and recorded
  ride detail. See `docs/product-specs/ride-journal.md`.
- **0007-coach-agent** (done): cycling-only coach chat in the web UI
  (unlocked once Garmin is connected) — scope guardrail, OpenAI
  tool-calling over sensor-gated ride data, weekly training summary,
  cited book passages, rider memory notes, persisted conversations
  streamed over SSE, and a monthly LLM budget. See
  `docs/product-specs/coach-chat.md`.
- **Not yet implemented**: HR drift, decoupling, GAP, VAM, the power curve
  and FTP auto-detection (NP/TSS, HR zones and training load are built — see
  `docs/design-docs/training-signal-model.md`), multi-week plans, matching
  planned sessions to recorded rides, proactive coach check-ins,
  historical backfill,
  manual FIT upload, wellness/HRV/sleep sync. Each gets its own exec-plan
  before work starts. `docs/exec-plans/tech-debt-tracker.md` lists what
  was deliberately deferred and why.

The prior single-rider, no-power-meter implementation is preserved at git
tag `v0-legacy` (commit `570fb90`) for reference — see
`docs/exec-plans/tech-debt-tracker.md` for what's worth salvaging from it.
