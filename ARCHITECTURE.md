# Architecture

## Shape

One local Python process combines FastAPI REST routes and a FastMCP server.
The Vite/React/TypeScript web app calls `/api`; the web coach also calls
`/mcp` for rider context and data tools. All domain rules remain in
`packages/core`; adapters convert transport inputs and outputs only.

```
Browser --cookie JWT--> /api --verified account--> core --> SQLite
Web coach --short-lived Bearer JWT--> /mcp --> core --> SQLite
Garmin poller (one runner per account) --> core --> SQLite + per-account files
```

## Authentication and account ownership

`auth_api.py` handles Google's authorization-code redirect and callback.
`core.auth.service` verifies identity and issues revocable, audience-specific
app JWTs. `auth_middleware.py` verifies each private REST or MCP request and
places the account in request context. `core.account_scope` applies ownership
filters and write checks to all rider-owned ORM tables. Account and auth
session tables are global; books and passages are the shared training corpus.
LLM usage records attribute calls to an account, while budget enforcement
sums spend globally.

A Garmin `activityId` is unique only with its account. `Activity.id` is the
local surrogate key used by ride detail and child rows; `(account_id,
garmin_id)` prevents duplicate imports. Garmin token caches, FIT files, sync
state, login coordination and pollers are separate per account. CLI Garmin
commands require an account ID.

## Coach and MCP

The REST coach route owns conversation streaming and OpenAI calls through
`core.llm.client`. For its starting rider context and each model-requested
data tool, it uses `mcp_bridge.py` to call the protected FastMCP endpoint.
The MCP tool calls the same core functions as other adapters. The browser
session cookie is never sent to MCP; the server mints a short-lived Bearer
JWT with the MCP audience. External MCP client issuance is deferred.

FastMCP's lifespan is combined with the Garmin poller supervisor lifespan
in `main.py`; omitting it causes MCP requests to hang. The poller supervisor
starts one runner per registered account and detects newly registered
accounts. The server remains bound to `127.0.0.1` by default.

## Database lifecycle

Alembic owns schema changes. `data/soft-floyd-accounts.db` is the new
account-era default. `soft-floyd prepare-account-db` can copy complete books
and passages from the old `data/soft-floyd.db` into a fresh account-era DB,
leaving the source untouched. Populated single-rider databases cannot be
upgraded in place because there is no reliable Google account owner for
those rows.
