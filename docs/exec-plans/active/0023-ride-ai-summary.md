# 0023 — AI ride summary

## Context
Riders want an AI read of each ride: what went well, what to improve, and a few
useful metrics. Implements `docs/product-specs/post-ride-analysis.md`. Generated
**on demand** (an "Analyze this ride" button on the ride page), **persisted** per
ride, and regenerable. Done means a rider can open any ride, request an analysis,
reload and still see it, and the analysis never mentions a sensor signal the
ride's own FIT data did not contain.

## Design
- `packages/core/src/soft_floyd_core/analysis/metrics.py`: deterministic,
  sensor-gated ride metrics (NP/IF/TSS/VI, HR zones, HR drift, load + basis,
  climbing per km, lap consistency, notes). Every field is gated by
  `available_metrics_for_activity` and the ride's own `has_*_data`.
- `analysis/service.py`: one structured LLM call that writes the narrative from
  those facts only, plus a comparison against recent same-type rides. Same
  budget-check -> call -> `record_usage` shape as `training/generator.py`.
  A post-check rejects watt figures when the ride has no verified power.
- New table `ride_analysis` (Alembic), account-owned, one row per ride.
- REST `GET/POST /api/activities/{id}/analysis` and MCP tools
  `get_ride_analysis` / `analyze_ride` are thin adapters over core.
- Web: `RideAnalysisCard` on the ride detail page, EN + ES strings.
- Sensor rules: see `docs/design-docs/sensor-capability-model.md`.

## Steps
1. Model + `OWNED_MODELS` + Alembic migration; `make docs-schema`.
2. `analysis/metrics.py` + unit tests.
3. `analysis/service.py` + tests with a fake LLM.
4. REST and MCP adapters + tests.
5. Web card, client, types, i18n.
6. Docs: product spec, tech-debt tracker.

## Verification
- `make check`.
- `tests/test_ride_analysis.py`: no power fields/watts without verified power,
  usage recorded (including incomplete responses), cached row reused without an
  LLM call, regenerate calls again, 402 over budget, account isolation.
- Manual: open a ride, Analyze, reload (persists, no new `llm_usage` row),
  Regenerate, switch to ES.

## Deferred
Auto-analysis after sync; power curve and decoupling (no exec-plan yet).
