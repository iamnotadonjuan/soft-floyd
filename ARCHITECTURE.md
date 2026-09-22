# Architecture

## Shape

One Python backend process, one small web frontend, one shared domain
package. Not microservices — a monorepo where the seams are drawn by
responsibility, not by deployment unit.

```
apps/
  server/   FastMCP tools + FastAPI routes, composed into one ASGI app.
            No domain logic — every handler is a call into packages/core.
  web/      Vite + React + TypeScript + Tailwind. Talks to apps/server
            over REST (and, once the coach agent exists, SSE) at /api.
packages/
  core/     All domain logic: config, DB models, the rider profile service
            (including the sensor capability model), the LLM client. The
            only package with rules in it.
```

## Why FastMCP-first

The coach's capabilities are defined as MCP tools first (`apps/server/src/soft_floyd_server/mcp_server.py`),
so the same rider profile, sensor-aware metrics, and (later) ride analysis
are usable directly from Claude Desktop or Claude Code, not only from the
bundled web UI. The web UI is a REST client of the same backend — it does
not get a privileged code path. See `docs/design-docs/mcp-first-backend.md`.

## Request paths

**MCP** (agent host, e.g. Claude Desktop):
```
Claude Desktop --MCP/streamable-http--> /mcp --> mcp_server.py tool --> packages/core --> SQLite
```

**Web UI:**
```
apps/web (fetch) --REST--> /api --> http_api.py route --> packages/core --> SQLite
```

Both adapters are mounted in the same ASGI app (`apps/server/src/soft_floyd_server/main.py`):

```python
mcp_app = mcp.http_app(path="/")
app = FastAPI(
    title="Soft Floyd",
    lifespan=combine_lifespans(poller_lifespan, mcp_app.lifespan),
)
app.include_router(http_router, prefix="/api")
app.mount("/mcp", mcp_app)
```

`mcp_app.lifespan` running is not optional — without it the MCP session
manager never initializes and `/mcp` requests hang silently. Since
exec-plan 0002 added a second startup/shutdown hook (the background
Garmin poller in `lifespan.py`), the two are merged with FastMCP's own
`combine_lifespans` helper rather than passing `mcp_app.lifespan` alone —
see `docs/references/fastmcp-notes.md` for the verified signature and
`tests/test_lifespan.py` for the hang-guard test.

## The load-bearing constraint

**`packages/core` is the only place a domain rule may be written.**
`mcp_server.py` and `http_api.py` are both thin adapters: each handler is a
type conversion plus a call into a `soft_floyd_core` function. Concretely,
adding a capability means writing one function in
`packages/core/src/soft_floyd_core/` and calling it from both a
`@mcp.tool` and an `@router.get/put`. If a rule is duplicated — or worse,
only implemented on one surface — that's a bug, not a style preference:
`tests/test_mcp_tools.py::test_mcp_and_rest_agree_on_capability_tier`
exists specifically to catch that class of drift.

## Data

SQLite at `data/soft-floyd.db` (gitignored), one engine per process,
created via `soft_floyd_core.db.make_engine`. Schema is managed by
Alembic (`packages/core/src/soft_floyd_core/migrations/`) — introduced in
exec-plan 0002, per `AGENTS.md`'s rule that the first schema change after
the scaffold must not be another ad hoc `create_all()`. Tables today:
`rider_profile`, `activity`, `lap`, `record`, `garmin_sync_state`,
`book`, `book_passage`, and `llm_usage`
(`packages/core/src/soft_floyd_core/models.py`; generated reference at
`docs/generated/db-schema.md`).

## What's deliberately not built yet

HR/power metrics computation (HR zones, TRIMP, decoupling, FTP/NP/TSS),
Generated coaching, ride-history retrieval, and a cost dashboard are
out of scope so far. Training-book retrieval is implemented in exec-plan
0005. Garmin ingest/auth and FIT parsing/classification are implemented
in exec-plan 0002 (`docs/product-specs/garmin-sync.md`). Each remaining item is a future
exec-plan under `docs/exec-plans/active/`. The prior v0 implementation of
most of these (HR-only, single hardcoded rider) is preserved at git tag
`v0-legacy` for reference and partial salvage.
