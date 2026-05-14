# Soft Floyd — Personal AI Cycling Coach

A local AI cycling coach for Garmin Edge 1050 riders. Ingests rides automatically from Garmin Connect, classifies them (road / MTB / indoor), reasons about HR-based metrics, and coaches via a conversational web UI. No power meter — HR is the primary signal.

## Quick Start

```bash
# Install dependencies
uv sync

# First-time Garmin login (MFA-aware)
uv run coach login

# Seed 12 months of history and embed all activities
uv run coach backfill --days 365

# Start the poller + HTTP server (127.0.0.1:8000)
uv run coach run
```

## Phase 2 Setup

Add your API keys to `~/.coach/config.toml`:

```toml
openai_api_key = "sk-..."       # for embeddings (text-embedding-3-small)
anthropic_api_key = "sk-ant-..." # for Soft Floyd coach (Haiku 4.5)
```

Or set `COACH_OPENAI_API_KEY` and `COACH_ANTHROPIC_API_KEY` environment variables.

## Commands

| Command | Description |
|---|---|
| `coach login` | Authenticate with Garmin Connect (MFA-aware). Token encrypted in macOS Keychain. |
| `coach backfill --days N` | Import historical rides from Garmin Connect (idempotent). |
| `coach run` | Start the 10-min poller + FastAPI server at `127.0.0.1:8000`. |
| `coach ingest-fit <path>` | Manually ingest a local FIT file (offline fallback). |

## HTTP API (Phase 2)

All endpoints are local-only (`127.0.0.1:8000`):

| Endpoint | Description |
|---|---|
| `POST /api/activities/{id}/analysis` | Generate Soft Floyd's initial analysis |
| `GET /api/activities/{id}/analysis` | Retrieve latest stored analysis |
| `POST /api/activities/{id}/chat` | Send a follow-up question `{"message": "..."}` |
| `GET /api/cost/month` | Current month's LLM spend |

## Development

```bash
# Install deps
uv sync

# Lint and format
uv run ruff check src/
uv run ruff format --check src/

# Tests
uv run pytest

# Recreate test FIT fixtures (only needed after changing make_fixtures.py)
uv run python tests/make_fixtures.py

# Apply DB migrations
uv run alembic upgrade head
```

## Project Structure

```
src/coach/
  config.py          # pydantic-settings; reads ~/.coach/config.toml
  cli.py             # typer entrypoint
  log.py             # structlog JSON to stdout
  store/
    models.py        # SQLAlchemy 2.x typed models
    session.py       # engine factory + sqlite-vec loader
    migrations/      # Alembic migration scripts
  ingest/
    garmin_client.py # garth client + Fernet token encryption
    fit_parser.py    # fitdecode-based FIT parser
    pipeline.py      # per-activity pipeline (parse → metrics → classify → embed)
    poller.py        # APScheduler 10-min poller + coach auto-trigger
    backfill.py      # batch historical import
  metrics/
    zones.py         # HR zone calculation from LTHR
    compute.py       # drift, decoupling, TRIMP, VAM, GAP
  classify/
    bike_type.py     # rule-based road/mtb/indoor classifier
  rag/
    chunking.py      # build_activity_card() — deterministic ~300-token text cards
    embedder.py      # OpenAI text-embedding-3-small; stores in embedding + embedding_vec
    retriever.py     # pre-filter + vec search → RetrievalContext
  agent/
    tools.py         # 5 read-only Anthropic tool schemas + executor
    coach.py         # CoachSession: streaming + tool-use loop
    prompts/
      system.md      # Soft Floyd persona (~2000 tokens, prompt-cached)
  web/
    api.py           # FastAPI app: analysis, chat, cost endpoints
    cost.py          # Haiku 4.5 token accounting + monthly_total()
tests/
  fixtures/          # sample_road.fit, sample_mtb.fit, sample_indoor.fit
  test_fit_parser.py
  test_metrics.py
  test_classifier.py
  test_retriever.py  # chunking + card determinism tests
  test_coach.py      # tools, cost calculation tests
data/                # gitignored — trainer.db, fit/ files
```

## Configuration

Config lives at `~/.coach/config.toml`. All keys are optional:

```toml
lthr = 165                  # Lactate threshold HR (bpm). Drives all zone calculations.
log_level = "INFO"
poll_interval_minutes = 10
openai_api_key = "sk-..."         # Phase 2: for embeddings
anthropic_api_key = "sk-ant-..."  # Phase 2: for Soft Floyd coach
```

## Constraints

- **No power meter** — watts are never fabricated. Everything is HR-based.
- **macOS only** — Keychain via `keyring`, notifications via `pync`.
- **Single user** — no auth layer. FastAPI binds to `127.0.0.1` only.
- **LLM cost cap $10/month** — prompt caching on every Anthropic call. Target ~$0.04/ride.

## Frontend Development (Phase 3)

```bash
cd frontend
pnpm install
pnpm dev        # dev server at localhost:5173 (proxies /api → :8000)
pnpm build      # outputs frontend/dist/
```

To serve the production build via FastAPI:

```bash
COACH_SERVE_FRONTEND=1 uv run coach run
# → full app at http://localhost:8000
```

## Implementation Phases

- **Phase 1 ✅** — Ingest pipeline. Garmin auth, FIT parse, HR metrics, classifier, poller, backfill.
- **Phase 2 ✅** — RAG + coach agent + FastAPI endpoints. Claude Haiku 4.5 with prompt caching.
- **Phase 3 ✅** — React + Vite frontend, SSE-streamed chat, production build served by FastAPI.

See [PLAN.md](PLAN.md) for detailed acceptance criteria per phase.
