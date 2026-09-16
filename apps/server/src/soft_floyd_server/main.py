"""ASGI app composition: FastMCP mounted inside FastAPI.

The lifespan wiring is load-bearing — without passing mcp_app.lifespan to
FastAPI, the MCP session manager never initializes and every /mcp request
hangs. See https://gofastmcp.com/integrations/fastapi.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from soft_floyd_server.http_api import router as http_router
from soft_floyd_server.mcp_server import mcp

mcp_app = mcp.http_app(path="/")

app = FastAPI(title="Soft Floyd", lifespan=mcp_app.lifespan)

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
