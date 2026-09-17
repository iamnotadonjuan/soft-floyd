"""ASGI app composition: FastMCP mounted inside FastAPI.

The lifespan wiring is load-bearing — without passing mcp_app.lifespan to
FastAPI, the MCP session manager never initializes and every /mcp request
hangs. See docs/references/fastmcp-notes.md and
https://gofastmcp.com/integrations/fastapi.

Since exec-plan 0002, this app also needs its own startup/shutdown hook
(the background Garmin poller in lifespan.py), so the two lifespans are
merged with FastMCP's own `combine_lifespans` helper (verified against
the installed fastmcp==4.0.4) rather than passing mcp_app.lifespan alone.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.utilities.lifespan import combine_lifespans

from soft_floyd_server.http_api import router as http_router
from soft_floyd_server.lifespan import poller_lifespan
from soft_floyd_server.mcp_server import mcp

mcp_app = mcp.http_app(path="/")

app = FastAPI(title="Soft Floyd", lifespan=combine_lifespans(poller_lifespan, mcp_app.lifespan))

# Local-only, single-user. The web UI's Vite dev server (localhost:5173)
# is the only cross-origin caller; production build is same-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(http_router, prefix="/api")
app.mount("/mcp", mcp_app)
