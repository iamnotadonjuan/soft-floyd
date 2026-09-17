# FastMCP — Mounting into FastAPI

Verified 2026-09-15 against https://gofastmcp.com/integrations/fastapi,
re-verified 2026-09-16 against the installed `fastmcp==4.0.4` source for
`combine_lifespans` (exec-plan 0002 needed a second lifespan — the
background Garmin poller — for the first time).

## The pattern used in this repo (apps/server/src/soft_floyd_server/main.py)

```python
from fastmcp.utilities.lifespan import combine_lifespans

mcp_app = mcp.http_app(path="/")
app = FastAPI(
    title="Soft Floyd",
    lifespan=combine_lifespans(poller_lifespan, mcp_app.lifespan),
)
app.include_router(other_router, prefix="/api")
app.mount("/mcp", mcp_app)
```

## Key facts

- `mcp.http_app(path=...)` returns a standalone ASGI application serving
  the MCP transport (streamable-http by default; `sse` and `http` are
  also selectable via `transport=`).
- **`mcp_app.lifespan` must run for every process, one way or another.**
  Without it, the MCP session manager is never started and requests to
  the mounted path hang.
- **`combine_lifespans`** (`fastmcp.utilities.lifespan`, a `utilities`
  module, not a top-level export — re-check this path if fastmcp is
  upgraded) merges any number of lifespans:
  ```python
  def combine_lifespans(
      *lifespans: Callable[[AppT], AbstractAsyncContextManager[Mapping[str, Any] | None]],
  ) -> Callable[[AppT], AbstractAsyncContextManager[dict[str, Any]]]:
  ```
  Enters them in argument order, exits LIFO, merges any yielded mappings
  (a plain FastAPI-style lifespan yielding `None` is fine in any
  position — only non-`None` results get merged). Confirmed via
  `tests/test_lifespan.py`, including a hang guard that actually POSTs an
  MCP `initialize` request through `TestClient` and asserts it doesn't
  404/500 — the failure mode if this wiring regresses is a silent hang,
  not an exception, so that test exists specifically to catch it.
- Feature available since FastMCP 2.3.1+.
- In-process testing: `fastmcp.Client(mcp_server_instance)` talks to the
  server via an in-memory transport, no HTTP server needed — used in
  `tests/test_mcp_tools.py`. A tool's structured result comes back as
  `result.data`, but note: for a return type of `list[SomeModel]` or a
  plain `@dataclass`, FastMCP reconstructs each item as a **dynamically
  generated dataclass** (`Root`), not the original class — it has no
  `.model_dump()`. Use `pydantic.TypeAdapter(type(item)).dump_python(item,
  mode="json")` to compare it against a REST response's `.json()` (see
  `tests/test_mcp_tools.py`'s `_as_json` helper). A tool returning a
  single Pydantic model directly still works fine with plain attribute
  access (`result.data.some_field`).

## Gotchas hit while building the scaffold

- `@mcp.tool` (bare decorator, no parens) is the documented shorthand;
  `@mcp.tool()` also works. This repo uses the bare form.
- A tool parameter typed as a Pydantic model (e.g. `ProfileIn`) is
  accepted directly — FastMCP builds the tool's input schema from the
  model's fields.
