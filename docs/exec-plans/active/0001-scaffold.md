# 0001 — Harness-Engineering Monorepo Scaffold

## Context

v0 (git tag `v0-legacy`, commit `570fb90`) was a complete but organically
grown implementation: Garmin ingest, FIT parsing, HR metrics, RAG, coach
agent, FastAPI + React UI — hardcoded to one rider with no power meter.
This plan restarts the repo as a harness-engineering monorepo: docs as
the primary artifact, code following from exec-plans, and a FastMCP-first
backend so the coach's capabilities are usable from any MCP host, not
just the bundled web UI.

It also generalizes the single hardcoded assumption in v0 — no power
meter — into a proper sensor capability model: the rider declares what
hardware they have, and the coach only reasons with signals it can
measure.

## Design

See `ARCHITECTURE.md` for the shape (`apps/server`, `apps/web`,
`packages/core`) and `docs/design-docs/sensor-capability-model.md` for
the tiering rule. Both adapters (`mcp_server.py`, `http_api.py`) call the
same `soft_floyd_core.profile.service` functions — no logic duplicated.

## Steps

1. Tag `v0-legacy` at `570fb90`, push to origin. *(done)*
2. Write the docs harness: `AGENTS.md`, `ARCHITECTURE.md`, `README.md`,
   and the full `docs/` tree (design-docs, product-specs, exec-plans,
   references, top-level guides).
3. Stand up the uv workspace: `packages/core` (config, db, models,
   profile service with capability tiering, LLM client stub) and
   `apps/server` (FastMCP tools, FastAPI routes, ASGI composition, CLI).
4. Stand up `apps/web`: Vite + React + TS + Tailwind, four-step
   onboarding (volume → goal → sensors → anchors), dashboard placeholder.
5. Dev ergonomics: `Makefile`, `.gitignore`, smoke tests covering the
   capability-tier matrix and MCP/REST agreement.

## Verification

```bash
make setup && make check                 # workspace resolves, lints, tests pass
uv run soft-floyd serve &                # server boots
curl -s localhost:8000/api/health
curl -s -X PUT localhost:8000/api/profile -d '{"has_power_meter": false, ...}'
curl -s localhost:8000/api/profile        # capability_tier == "hr"
curl -s -X PUT localhost:8000/api/profile -d '{"has_power_meter": true, "ftp_watts": 240}'
curl -s localhost:8000/api/profile        # capability_tier == "power"
```

MCP surface: an MCP client calling `get_rider_profile` against
`http://127.0.0.1:8000/mcp` must return the same `capability_tier` as the
REST call above (`tests/test_mcp_tools.py` automates this).

Web: `pnpm dev` → complete onboarding → unchecking power meter hides the
FTP question; profile persists across reload; capability summary shown
after submit matches the sensors selected.

## Status

Implemented. See `docs/exec-plans/tech-debt-tracker.md` for what was
deliberately left out (Garmin sync, metrics, RAG, coach agent, Alembic).
