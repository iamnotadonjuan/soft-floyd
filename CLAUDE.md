# Soft Floyd — Cycling Coach

Personal AI cycling coach for a Garmin Edge 1050 rider. Ingests rides automatically from Garmin Connect, classifies them (road / MTB / indoor), and coaches via a conversational web UI using HR-based metrics. No power meter — HR is the primary signal.

See `PLAN.md` for the full phased implementation plan.

## Common commands

```bash
# Setup
uv sync

# Run all checks
uv run ruff check src/ && uv run ruff format --check src/
uv run pytest

# CLI
uv run coach login          # first-run Garmin auth (MFA-aware)
uv run coach backfill --days 365   # seed 12 months of history
uv run coach run            # start poller + FastAPI server

# Frontend (Phase 3)
cd frontend && npm install && npm run dev   # dev server at :5173
cd frontend && npm run build               # outputs frontend/dist/
```

## Project structure

```
src/coach/
  config.py          # pydantic-settings; reads ~/.coach/config.toml
  cli.py             # typer entrypoint
  store/             # SQLAlchemy models + Alembic migrations
  ingest/            # garth client, APScheduler poller, FIT parser, backfill
  metrics/           # HR zones, compute (drift, decoupling, GAP, VAM, TRIMP)
  classify/          # rule-based bike-type classifier
  rag/               # chunking, OpenAI embedder, sqlite-vec retriever
  agent/             # CoachSession + Anthropic tool loop + prompts/system.md
  web/               # FastAPI app, SSE streaming, cost meter
frontend/            # React 18 + Vite + TypeScript (Phase 3)
data/                # gitignored — trainer.db, *.fit files, garth tokens
tests/
  fixtures/          # sample_road.fit, sample_mtb.fit, sample_indoor.fit
```

## Stack

| Area | Choice |
|---|---|
| Language / pkg mgr | Python 3.12, `uv` |
| Database | SQLite + `sqlite-vec` extension (`data/trainer.db`) |
| ORM / migrations | SQLAlchemy 2.x (typed `Mapped` syntax) + Alembic |
| Garmin access | `garth` (unofficial); tokens Fernet-encrypted in `~/.coach/garth.json`, key in macOS Keychain |
| FIT parsing | `fitdecode` (better Edge 1050 dev-field support than `fitparse`) |
| Scheduler | `apscheduler` `AsyncIOScheduler`, 10-min interval |
| Embeddings | OpenAI `text-embedding-3-small` (1536-dim) |
| LLM | `claude-haiku-4-5-20251001` via Anthropic SDK with prompt caching |
| Web backend | FastAPI + `sse-starlette` for streaming chat |
| Frontend | React 18 + Vite + TypeScript + Tailwind + Recharts |
| Config | `pydantic-settings`, reads `~/.coach/config.toml` + env vars |
| CLI | `typer` |
| Logging | `structlog` JSON to stdout |

## Key constraints

- **No power meter**: never fabricate watts. Coach reasons exclusively in HR drift %, decoupling %, time-in-zone, GAP, VAM, TRIMP. If an analysis mentions watts, it's a bug.
- **Single user**: no auth layer, no multi-tenancy. Bind FastAPI to `127.0.0.1` only.
- **macOS only**: Keychain access via `keyring`, desktop notifications via `pync`.
- **LLM cost cap $10/month**: ~22 rides/month. Prompt caching is mandatory on every Anthropic call. Target ~$0.04/ride. Log every API call to the `message` table with token counts and cost.
- **`garth` is unofficial**: pin the version (`>=0.5,<1.0`). On `GarthHTTPError(401)` raise `ReauthRequired` and notify the user — never silently retry.
- **Storage budget**: store FIT time-series (`record` table) only when total size < 3 MB per activity to keep the DB small.

## Soft Floyd persona

The coach is named "Soft Floyd." Tone: kind, encouraging, focuses on long-term progress, celebrates small wins, honest but never harsh. The system prompt lives at `src/coach/agent/prompts/system.md` and is sent as a cached block on every Anthropic call.

## Data model highlights

- `activity` — one row per Garmin activity; `bike_type` ∈ `{road, mtb, indoor, other}`
- `metrics` — derived HR stats per activity (decoupling, drift, time-in-zone, VAM, GAP)
- `wellness_daily` — HRV, sleep, Body Battery, RHR, ACWR from Garmin Connect
- `embedding` + `embedding_vec` (vec0 virtual table) — activity cards for RAG
- `conversation` / `message` — chat history with token + cost accounting
- `poll_cursor` — last seen activity ID for the poller

## Bike-type classification rules (in order)

1. `is_indoor=True` → `indoor`
2. `sub_sport ∈ {mountain, gravel_cycling, cyclocross}` → `mtb`
3. `sub_sport ∈ {road, virtual_ride}` → `road` (virtual_ride with no GPS → `indoor`)
4. Heuristic: avg speed > 22 km/h AND elev_gain/km < 15 m → `road`, else `mtb`
5. Ambiguous → `other` (no LLM fallback in Phase 1)

## Phasing

- **Phase 1** — Ingest pipeline only. Garth + FIT parse + metrics + classifier + poller + backfill. No AI, zero LLM cost.
- **Phase 2** — RAG + coach agent + minimal FastAPI endpoints. Claude Haiku with prompt caching.
- **Phase 3** — React + Vite frontend, SSE-streamed chat, production build served by FastAPI.

Each phase has its own acceptance criteria in `PLAN.md`. Do not start Phase 2 until all Phase 1 acceptance criteria pass.

## Testing conventions

- Use `pytest` + `pytest-asyncio`. Real FIT fixture files in `tests/fixtures/` — no mocking the parser.
- Mock `garth` HTTP calls with `respx`.
- Golden / snapshot tests for `build_activity_card()` output (chunking must be deterministic).
- Every metrics function has at least one test with a hand-computed expected value.
