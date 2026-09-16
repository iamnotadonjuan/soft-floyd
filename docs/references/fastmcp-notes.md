# FastMCP — Mounting into FastAPI

Verified 2026-09-15 against https://gofastmcp.com/integrations/fastapi.

## The pattern used in this repo

```python
mcp_app = mcp.http_app(path="/")  # ASGI app from the FastMCP server
app = FastAPI(title="...", lifespan=mcp_app.lifespan)  # REQUIRED
app.include_router(other_router, prefix="/api")
app.mount("/mcp", mcp_app)
```

## Key facts

- `mcp.http_app(path=...)` returns a standalone ASGI application serving
  the MCP transport (streamable-http by default; `sse` and `http` are
  also selectable via `transport=`).
- **Passing `mcp_app.lifespan` to `FastAPI(lifespan=...)` is mandatory.**
  Without it, the MCP session manager is never started and requests to
  the mounted path hang. If you need to combine it with your own
  lifespan, FastMCP exposes a `combine_lifespans` helper — not needed in
  this repo since `apps/server` has no other startup/shutdown hooks yet.
- Feature available since FastMCP 2.3.1+.
- In-process testing: `fastmcp.Client(mcp_server_instance)` talks to the
  server via an in-memory transport, no HTTP server needed — used in
  `tests/test_mcp_tools.py`.

## Gotchas hit while building the scaffold

- `@mcp.tool` (bare decorator, no parens) is the documented shorthand;
  `@mcp.tool()` also works. This repo uses the bare form.
- A tool parameter typed as a Pydantic model (e.g. `ProfileIn`) is
  accepted directly — FastMCP builds the tool's input schema from the
  model's fields.
