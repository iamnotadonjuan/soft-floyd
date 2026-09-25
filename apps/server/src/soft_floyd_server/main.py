"""ASGI app composition: FastMCP mounted inside FastAPI.

The lifespan wiring is load-bearing — without passing mcp_app.lifespan to
FastAPI, the MCP session manager never initializes and every /mcp request
hangs. See docs/references/fastmcp-notes.md and
https://gofastmcp.com/integrations/fastapi.

Since exec-plan 0002, this app also needs its own startup/shutdown hook
(the background Garmin poller in lifespan.py), so the two lifespans are
merged with FastMCP's own `combine_lifespans` helper (verified against
the installed fastmcp==4.0.4) rather than passing mcp_app.lifespan alone.

Since exec-plan 0009, `stateless_http=True` is load-bearing for account
isolation: the SDK's stateful mode binds a session to `scope["user"]`
(mcp/server/streamable_http_manager.py), which our AccountAuthMiddleware
never sets — it puts the account on `scope["state"]` instead. Without
this, a request carrying another account's still-open `mcp-session-id`
header would run its tool calls under whichever account opened that
session, not the caller's own token. Stateless mode re-authenticates and
re-scopes every request instead of reusing a session's context, and
CoachMCPBridge already opens a fresh client per call, so nothing is lost.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.utilities.lifespan import combine_lifespans

from soft_floyd_server.auth_api import router as auth_router
from soft_floyd_server.auth_middleware import AccountAuthMiddleware
from soft_floyd_server.http_api import router as http_router
from soft_floyd_server.lifespan import poller_lifespan
from soft_floyd_server.mcp_server import mcp

mcp_app = mcp.http_app(path="/", stateless_http=True)

app = FastAPI(title="Soft Floyd", lifespan=combine_lifespans(poller_lifespan, mcp_app.lifespan))

# Local-only, single-user. The web UI's Vite dev server (localhost:5173)
# is the only cross-origin caller; production build is same-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccountAuthMiddleware)

app.include_router(auth_router, prefix="/api")
app.include_router(http_router, prefix="/api")
app.mount("/mcp", mcp_app)
