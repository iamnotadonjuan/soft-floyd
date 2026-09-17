# Soft Floyd

A sensor-aware AI cycling coach. It learns what training volume and goals
you have, what hardware you actually ride with (power meter, HR monitor,
cadence/speed sensors), and coaches you using only the signals that
hardware can produce — never a fabricated one.

Single user, runs locally. Backend exposes both an MCP surface (usable
from Claude Desktop/Code) and a small REST API for the bundled web UI.

For how the system is put together, see [ARCHITECTURE.md](ARCHITECTURE.md).
For agent/contributor working rules, see [AGENTS.md](AGENTS.md).
For the product and design reasoning, see [docs/](docs/) — start with
[docs/design-docs/index.md](docs/design-docs/index.md).

## Quick start

```bash
make setup        # uv sync + pnpm install

# terminal 1
make dev-server    # http://127.0.0.1:8000  (REST at /api, MCP at /mcp)

# terminal 2
make dev-web       # http://localhost:5173  (proxies /api, /mcp to :8000)
```

Open `http://localhost:5173` and complete onboarding: how much you ride,
what you want to improve, and what sensors you have. That last part
determines what the coach is allowed to talk about — see
[docs/design-docs/sensor-capability-model.md](docs/design-docs/sensor-capability-model.md).

## Connecting Garmin

One-time interactive login, then sync runs automatically every 10
minutes (or trigger it manually):

```bash
uv run soft-floyd garmin-login   # prompts email/password/MFA; nothing is persisted but the resulting token
uv run soft-floyd garmin-sync    # one-shot sync, without starting the server
```

See [docs/product-specs/garmin-sync.md](docs/product-specs/garmin-sync.md)
for how the free/unofficial `python-garminconnect` integration works and
why the official Garmin/Strava APIs aren't options here.

## Talking to it from Claude Desktop / Claude Code

Point an MCP client at `http://127.0.0.1:8000/mcp` (streamable-http
transport) while `make dev-server` is running. Available tools today:
`get_rider_profile`, `set_rider_profile`, `get_available_metrics`,
`list_activities`, `get_activity`, `sync_garmin_now`,
`get_garmin_sync_status`.

## Commands

```bash
make check          # lint + test, Python and web
make docs-schema     # regenerate docs/generated/db-schema.md
uv run pytest        # Python tests only
uv run ruff check .   # Python lint only
cd apps/web && pnpm run typecheck
```

## Status

Rider profile (sensor capability tiering) and Garmin activity sync
(automatic + manual, bike classification, per-ride sensor-presence
detection) both work end-to-end across MCP, REST, and the CLI. Metrics
computation (HR zones, TRIMP, FTP/NP/TSS), RAG over training books, and
the coach agent are not built yet — see `docs/exec-plans/active/` for
what's planned next and `docs/exec-plans/tech-debt-tracker.md` for what's
deferred (including: historical backfill, manual FIT upload, wellness
sync, and a web UI for the activities that now sync in the background).

The previous single-rider, HR-only implementation is preserved at git tag
`v0-legacy`.
