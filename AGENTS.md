# Soft Floyd — Agent Operating Manual

Soft Floyd is a sensor-aware AI cycling coach. It ingests rides from a
Garmin Edge device, reasons about training load using whatever sensors the
rider actually has, and coaches through both an MCP surface (Claude
Desktop/Code) and a small web UI. Single user, runs locally.

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
- **Single user, local-only.** The server binds to `127.0.0.1` by default;
  do not add multi-tenancy or a public bind without an explicit ask. See
  `docs/SECURITY.md`.
- **Garmin access is unofficial and will occasionally break.** Map
  auth/rate-limit failures to actionable errors, never silently retry
  forever. See `docs/RELIABILITY.md`.
- **LLM cost cap ~$5-10/month.** Model is pinned to OpenAI `gpt-4.1-mini`
  (chat) and `text-embedding-3-small` (embeddings) in
  `packages/core/src/soft_floyd_core/llm/client.py`. Every LLM call must
  be recorded there once the coach agent lands — don't call the OpenAI
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
- **Not yet implemented**: HR/power metrics computation (HR zones, TRIMP,
  decoupling, FTP/NP/TSS — see `docs/design-docs/training-signal-model.md`),
  generated coach agent/chat, ride-history retrieval, historical backfill,
  manual FIT upload, wellness/HRV/sleep sync. Each gets its own exec-plan
  before work starts. `docs/exec-plans/tech-debt-tracker.md` lists what
  was deliberately deferred and why.

The prior single-rider, no-power-meter implementation is preserved at git
tag `v0-legacy` (commit `570fb90`) for reference — see
`docs/exec-plans/tech-debt-tracker.md` for what's worth salvaging from it.
