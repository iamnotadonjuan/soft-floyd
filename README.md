# Soft Floyd — Personal AI Cycling Coach

A local AI cycling coach for Garmin Edge 1050 riders. Ingests rides automatically from Garmin Connect, classifies them (road / MTB / indoor), reasons about HR-based metrics, and coaches via a conversational web UI. No power meter — HR is the primary signal.

## Quick Start

```bash
# Install dependencies
uv sync

# First-time Garmin login (MFA-aware)
uv run coach login

# Seed 12 months of history
uv run coach backfill --days 365

# Start the background poller
uv run coach run
```

## Commands

| Command | Description |
|---|---|
| `coach login` | Authenticate with Garmin Connect (MFA-aware). Token encrypted in macOS Keychain. |
| `coach backfill --days N` | Import historical rides from Garmin Connect (idempotent). |
| `coach run` | Start the 10-min poller. New rides appear within ~15 min of syncing. |
| `coach ingest-fit <path>` | Manually ingest a local FIT file (offline fallback). |

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
    pipeline.py      # per-activity pipeline (parse → metrics → classify)
    poller.py        # APScheduler 10-min poller
    backfill.py      # batch historical import
  metrics/
    zones.py         # HR zone calculation from LTHR
    compute.py       # drift, decoupling, TRIMP, VAM, GAP
  classify/
    bike_type.py     # rule-based road/mtb/indoor classifier
tests/
  fixtures/          # sample_road.fit, sample_mtb.fit, sample_indoor.fit
  test_fit_parser.py
  test_metrics.py
  test_classifier.py
data/                # gitignored — trainer.db, fit/ files
```

## Configuration

Config lives at `~/.coach/config.toml`. All keys are optional:

```toml
lthr = 165            # Lactate threshold HR (bpm). Drives all zone calculations.
log_level = "INFO"
poll_interval_minutes = 10
```

## Constraints

- **No power meter** — watts are never fabricated. Everything is HR-based.
- **macOS only** — Keychain via `keyring`, notifications via `pync`.
- **Single user** — no auth layer. FastAPI will bind to `127.0.0.1` only (Phase 2+).
- **LLM cost cap $10/month** — prompt caching is mandatory on every Anthropic call (Phase 2+).

## Implementation Phases

- **Phase 1 ✅** — Ingest pipeline. Garmin auth, FIT parse, HR metrics, classifier, poller, backfill.
- **Phase 2** — RAG + coach agent + FastAPI endpoints. Claude Haiku with prompt caching.
- **Phase 3** — React + Vite frontend, SSE-streamed chat, production build.

See [PLAN.md](PLAN.md) for detailed acceptance criteria per phase.
