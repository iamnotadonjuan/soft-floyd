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
app = FastAPI(title="Soft Floyd", lifespan=mcp_app.lifespan)  # lifespan is required
app.include_router(http_router, prefix="/api")
app.mount("/mcp", mcp_app)
```

The `lifespan=mcp_app.lifespan` wiring is not optional — without it the
MCP session manager never initializes and `/mcp` requests hang silently.

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
created via `soft_floyd_core.db.make_engine`. Schema is currently
`Base.metadata.create_all()` — no migrations yet; see
`docs/exec-plans/tech-debt-tracker.md`. The only table today is
`rider_profile` (`packages/core/src/soft_floyd_core/models.py`).

## What's deliberately not built yet

Garmin ingest/auth, FIT parsing, HR/power metrics computation, RAG over
training books, the coach agent/chat, and a cost dashboard are all out of
scope for the scaffold. Each is a future exec-plan under
`docs/exec-plans/active/`. The prior implementation of most of these
(HR-only) is preserved at git tag `v0-legacy` for reference and partial
salvage.
