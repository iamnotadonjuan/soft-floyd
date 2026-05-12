# Soft Floyd - Codex Instructions

This repository builds "Soft Floyd", a local personal AI cycling coach for a Garmin Edge 1050 rider. It ingests Garmin rides, classifies them as `road`, `mtb`, `indoor`, or `other`, computes HR-based training metrics, and later exposes coaching through a local conversational web UI.

Read `PLAN.md` before substantial implementation. It is the source of truth for phased scope and acceptance criteria. `CLAUDE.md` is the compact project brief and should stay consistent with this file.

## Current State

- Phase 1 is implemented and marked complete in `PLAN.md` as of 2026-05-11.
- The current codebase contains the Python ingest pipeline, SQLite/Alembic schema, Garmin auth, FIT parser, metrics, bike classifier, poller, backfill, offline FIT ingest command, and tests.
- Phase 2 work is the next planned product phase: RAG, embeddings, coach agent, cost logging, and minimal FastAPI endpoints.
- Phase 3 work must wait until the Phase 2 API exists.

## Working Rules

- Follow the phases in `PLAN.md`. Preserve the completed Phase 1 behavior while adding Phase 2. Do not start Phase 3 until the Phase 2 API exists.
- Keep changes scoped to the current phase and task. Avoid unrelated refactors.
- Preserve the single-user, local-only model. FastAPI must bind to `127.0.0.1`; do not add authentication or multi-tenancy unless explicitly requested.
- This is macOS-only. Use Keychain through `keyring` for secrets and `pync` for desktop notifications where the plan calls for notifications.
- No power meter is available. Never fabricate or infer watts. All coaching and metrics must use HR drift, decoupling, time in HR zones, GAP, VAM, TRIMP, wellness, and ride context.
- Phase 1 paths must make zero LLM or embedding calls. Phase 2 must use Anthropic prompt caching on every call and log token/cost data for each message. The cost cap is about $5-10/month, with a target around $0.04/ride.
- `garth` is unofficial. Keep it pinned to `>=0.5,<1.0`; on `GarthHTTPError(401)`, raise `ReauthRequired` and notify the user instead of silently retrying.
- Store FIT time-series records only when the total per-activity record payload is below 3 MB.
- Use the shared per-activity ingest pipeline in `src/coach/ingest/pipeline.py` instead of duplicating ingest logic in poller, backfill, or future embedding hooks.

## Common Commands

```bash
uv sync
uv run ruff check src/
uv run ruff format --check src/
uv run pytest
uv run alembic upgrade head
uv run coach login
uv run coach backfill --days 365
uv run coach run
uv run coach ingest-fit tests/fixtures/sample_road.fit
```

Frontend commands for Phase 3:

```bash
cd frontend && npm install
cd frontend && npm run dev
cd frontend && npm run build
```

## Stack

- Python 3.12 managed with `uv`
- SQLite at `data/trainer.db` with `sqlite-vec`
- SQLAlchemy 2.x typed `Mapped` models and Alembic migrations
- Garmin access through `garth`
- Garmin tokens encrypted with Fernet at `~/.coach/garth.json`; Fernet key stored in macOS Keychain under service `coach-soft-floyd`, account `garth-token-key`
- FIT parsing through `fitdecode`
- Scheduling through the local poller with a 10-minute interval; `apscheduler` is available per the plan
- Config through `pydantic-settings`, reading `~/.coach/config.toml` and `COACH_` environment variables
- CLI through `typer`
- JSON logging through `structlog`
- Notifications through `pync`
- Embeddings through OpenAI `text-embedding-3-small` in Phase 2
- LLM through Anthropic `claude-haiku-4-5-20251001` with prompt caching in Phase 2
- FastAPI plus `sse-starlette` for the backend in Phase 2+
- React 18 + Vite + TypeScript + Tailwind + Recharts for Phase 3

## Current Layout

```text
src/coach/
  config.py
  log.py
  cli.py
  store/
    models.py
    session.py
    migrations/
  ingest/
    garmin_client.py
    poller.py
    fit_parser.py
    pipeline.py
    backfill.py
  metrics/
    compute.py
    zones.py
  classify/
    bike_type.py
tests/
  fixtures/
data/
```

Target Phase 2/3 additions from `PLAN.md`:

```text
src/coach/
  rag/
    chunking.py
    embedder.py
    retriever.py
  agent/
    coach.py
    tools.py
    prompts/system.md
  web/
    api.py
    sse.py
    cost.py
frontend/
```

`data/` is local runtime storage and must stay gitignored. The Garmin token file lives outside the repo at `~/.coach/garth.json`.

## Phase Expectations

### Phase 1 - Garmin Ingest Baseline

Implemented modules and behavior to preserve:

- `uv run coach --help` lists `login`, `backfill`, `run`, and `ingest-fit`.
- `uv run alembic upgrade head` creates the Phase 1 tables.
- `coach login` handles email/password/MFA and stores encrypted Garmin tokens.
- `coach backfill --days 365` is idempotent and uses the shared ingest pipeline.
- `coach run` polls Garmin every 10 minutes, backs off on errors, and requests reauth through notification on expired sessions.
- Parser tests use real FIT fixtures from `tests/fixtures/`.
- Metrics tests include hand-computed expected values.
- Classifier rules run in the exact order from `PLAN.md`.
- Phase 1 makes no LLM or embedding calls.

### Phase 2 - Coach Agent + RAG

Add embeddings, retrieval, read-only tools, the Soft Floyd system prompt, Anthropic orchestration, cost logging, and minimal FastAPI endpoints.

Acceptance highlights:

- Every backfilled activity has one `summary` embedding.
- Retrieval filters by bike type and combines similar rides, recent rides, wellness, and the current activity card.
- Prompt caching is present on every Anthropic system block.
- The coach response uses the Soft Floyd persona, references relevant past rides and wellness/load, and never mentions fabricated power data.
- Every message persists token and cost data.
- `GET /api/cost/month` reports current monthly spend.

### Phase 3 - React UI

Add the local UI, SSE chat, activity list/detail endpoints, charts, lap table, conversation history, and production static serving.

Acceptance highlights:

- `localhost:8000` shows the app when `COACH_SERVE_FRONTEND=1 uv run coach run` is used.
- Activity list filters by bike type.
- Activity detail shows HR/elevation chart, laps, metrics, analysis, and chat.
- Chat streams tokens and tool-call status.
- Monthly cost indicator updates after chat usage.

## Domain Rules

### HR Zones

Use configured LTHR from `~/.coach/config.toml`, defaulting to 165 if absent:

- Z1: below 80% LTHR
- Z2: 80-89% LTHR
- Z3: 90-94% LTHR
- Z4: 95-99% LTHR
- Z5: at least 100% LTHR

### Bike Classification Order

1. `is_indoor=True` -> `indoor`
2. `sub_sport in {"mountain", "gravel_cycling", "cyclocross"}` -> `mtb`
3. `sub_sport in {"road", "virtual_ride"}` -> `road`, except `virtual_ride` with no GPS -> `indoor`
4. If `avg_speed_kmh > 22` and `elev_gain_per_km < 15` -> `road`; otherwise `mtb`
5. Ambiguous cases -> `other`

The current parser may surface virtual FIT rides as `virtual_activity`; keep that compatible with the rule above. Do not add an LLM classifier fallback in Phase 1.

## Soft Floyd Persona

The coach is named Soft Floyd. The tone is kind, encouraging, honest, and focused on long-term progress. Celebrate small wins without being fake. Be direct about fatigue, pacing, recovery, and risk, but never harsh.

The Phase 2 system prompt belongs at `src/coach/agent/prompts/system.md` and must be sent as a cached Anthropic system block on every call.

## Testing Guidance

- Use `pytest` and `pytest-asyncio`.
- Use real FIT fixture files for parser tests.
- Use `respx` for Garmin HTTP mocking.
- Use deterministic golden/snapshot tests for activity-card chunking.
- Add focused tests for each metrics formula.
- Prefer integration tests where schema, ingestion, retrieval, or cost accounting crosses module boundaries.
- If fixture generation changes, use `uv run python tests/make_fixtures.py`.

## Implementation Notes

- Use SQLAlchemy 2.x typed `Mapped` syntax.
- Load the `sqlite-vec` extension on every SQLite connection through a SQLAlchemy connect listener.
- Keep `embedding.text` as the source of truth; vectors can be regenerated.
- Backfill should throttle Garmin requests to no more than 1 request per second.
- Polling should run every 10 minutes and back off up to 60 minutes on 429/5xx.
- Use structured JSON logs. Include activity IDs and bike types in ingestion logs.
- Keep all tools exposed to the coach read-only.
