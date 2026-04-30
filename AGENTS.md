# Soft Floyd - Codex Instructions

This repository builds "Soft Floyd", a personal AI cycling coach for a Garmin Edge 1050 rider. The product ingests Garmin rides, classifies them as road / MTB / indoor / other, computes HR-based training metrics, and later exposes coaching through a local conversational web UI.

Read `PLAN.md` before implementing substantial work. It is the source of truth for the phased implementation plan and acceptance criteria. `CLAUDE.md` contains a compact project brief with the same constraints.

## Working Rules

- Follow the phases in `PLAN.md`. Do not start Phase 2 work until all Phase 1 acceptance criteria pass. Do not start Phase 3 work until the Phase 2 API exists.
- Keep changes scoped to the current phase and task. Avoid unrelated refactors.
- Preserve the single-user, local-only model. FastAPI must bind to `127.0.0.1`; do not add authentication or multi-tenancy unless explicitly requested.
- This is macOS-only. Use Keychain through `keyring` for secrets and `pync` for desktop notifications where the plan calls for notifications.
- No power meter is available. Never fabricate or infer watts. All coaching and metrics must use HR drift, decoupling, time in HR zones, GAP, VAM, TRIMP, wellness, and ride context.
- LLM cost is tightly capped. Phase 1 must make zero LLM or embedding calls. Phase 2 must use prompt caching on every Anthropic call and log token/cost data for each message.
- `garth` is unofficial. Pin it to `>=0.5,<1.0`; on `GarthHTTPError(401)`, raise `ReauthRequired` and notify the user instead of silently retrying.
- Store FIT time-series records only when the total per-activity record payload is below the storage budget described in `PLAN.md`.

## Common Commands

```bash
uv sync
uv run ruff check src/
uv run ruff format --check src/
uv run pytest
uv run coach login
uv run coach backfill --days 365
uv run coach run
```

Frontend commands for Phase 3:

```bash
cd frontend && npm install
cd frontend && npm run dev
cd frontend && npm run build
```

## Target Stack

- Python 3.12 managed with `uv`
- SQLite at `data/trainer.db` with `sqlite-vec`
- SQLAlchemy 2.x typed `Mapped` models and Alembic migrations
- Garmin access through `garth`
- FIT parsing through `fitdecode`
- Scheduling through APScheduler `AsyncIOScheduler`
- Config through `pydantic-settings`, reading `~/.coach/config.toml` and environment variables
- CLI through `typer`
- JSON logging through `structlog`
- Embeddings through OpenAI `text-embedding-3-small` in Phase 2
- LLM through Anthropic `claude-haiku-4-5-20251001` with prompt caching in Phase 2
- FastAPI plus `sse-starlette` for the backend
- React 18 + Vite + TypeScript + Tailwind + Recharts for Phase 3

## Target Layout

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
    backfill.py
  metrics/
    compute.py
    zones.py
  classify/
    bike_type.py
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
tests/
  fixtures/
data/
```

`data/` is local runtime storage and should be gitignored.

## Phase Expectations

### Phase 1 - Garmin Ingest

Implement repo bootstrap, SQLite/Alembic, Garmin login/token persistence, FIT parsing, HR metrics, bike classification, polling, and backfill.

Acceptance highlights:

- `uv run coach --help` lists `login`, `backfill`, and `run`.
- `alembic upgrade head` creates the Phase 1 tables.
- `coach login` handles email/password/MFA and reuses encrypted tokens on the next run.
- Parser tests use real FIT fixtures from `tests/fixtures/`.
- Metrics tests include hand-computed expected values.
- Classifier rules run in the exact order from `PLAN.md`.
- `coach backfill --days 365` is idempotent.
- Phase 1 makes no LLM or embedding calls.

### Phase 2 - Coach Agent + RAG

Add embeddings, retrieval, read-only tools, the Soft Floyd system prompt, Anthropic orchestration, cost logging, and minimal FastAPI endpoints.

Acceptance highlights:

- Every backfilled activity has one `summary` embedding.
- Retrieval filters by bike type and combines similar rides, recent rides, wellness, and the current activity card.
- Prompt caching is present on every Anthropic system block.
- The coach response uses the Soft Floyd persona, references relevant past rides and wellness/load, and never mentions fabricated power data.
- Every message persists token and cost data.

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

Do not add an LLM classifier fallback in Phase 1.

## Soft Floyd Persona

The coach is named Soft Floyd. The tone is kind, encouraging, honest, and focused on long-term progress. Celebrate small wins without being fake. Be direct about fatigue, pacing, recovery, and risk, but never harsh.

The Phase 2 system prompt belongs at `src/coach/agent/prompts/system.md` and should be sent as a cached Anthropic system block on every call.

## Testing Guidance

- Use `pytest` and `pytest-asyncio`.
- Use real FIT fixture files for parser tests.
- Use `respx` for Garmin HTTP mocking.
- Use deterministic golden/snapshot tests for activity-card chunking.
- Add focused tests for each metrics formula.
- Prefer integration tests where schema, ingestion, retrieval, or cost accounting crosses module boundaries.

## Implementation Notes

- Use SQLAlchemy 2.x typed `Mapped` syntax.
- Load the `sqlite-vec` extension on every SQLite connection through a SQLAlchemy connect listener.
- Keep `embedding.text` as the source of truth; vectors can be regenerated.
- Backfill should throttle Garmin requests to no more than 1 request per second.
- Polling should run every 10 minutes and back off up to 60 minutes on 429/5xx.
- Use structured JSON logs. Include activity IDs and bike types in ingestion logs.
- Keep all tools exposed to the coach read-only.
