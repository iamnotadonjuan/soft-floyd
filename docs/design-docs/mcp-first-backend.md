# Why FastMCP-First

## The decision

The backend's capabilities are defined once, as MCP tools
(`apps/server/src/soft_floyd_server/mcp_server.py`), and the REST API
(`http_api.py`) is a second, thin adapter over the same
`packages/core` functions — not the other way around.

## Why

- The rider (or any agent working on their behalf) should be able to ask
  Claude Desktop or Claude Code "what's my FTP and what can you tell from
  my last ride" without a bespoke chat UI existing yet. MCP tools make
  the coach's capabilities available to any MCP-speaking agent host
  immediately.
- Designing the tool surface first forces a clean, capability-oriented
  API (`get_rider_profile`, `set_rider_profile`, `get_available_metrics`,
  `list_activities`) rather than a REST API shaped by whatever the
  current UI screen happens to need. REST then inherits that clarity.
- It keeps `packages/core` honest as the only place with logic — an MCP
  tool that's just `return profile_service.get_profile(session)` cannot
  hide a rule the REST route doesn't also get.

## Mechanics

FastMCP's `http_app()` returns an ASGI app; mounting it inside FastAPI
requires passing its `.lifespan` to the FastAPI constructor or the MCP
session manager never initializes (this is documented in FastMCP's own
FastAPI integration guide, https://gofastmcp.com/integrations/fastapi,
and confirmed against the FastMCP 2.3.1+ API). See
`apps/server/src/soft_floyd_server/main.py` for the exact composition,
and `ARCHITECTURE.md` for the full request-path diagram.

## What this doesn't mean

REST is not an afterthought or a lesser citizen — the web UI is the
primary way *this* rider will use the app day to day. "MCP-first" means
the capability boundary is designed through the MCP lens first; both
surfaces are equally real and must stay behaviorally identical, which is
why `tests/test_mcp_tools.py` asserts MCP and REST agree on the same
underlying state.
