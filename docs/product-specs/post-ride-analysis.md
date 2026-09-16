# Post-Ride Analysis

Status: **not implemented.** Depends on
[garmin-sync.md](garmin-sync.md) and
[../design-docs/training-signal-model.md](../design-docs/training-signal-model.md).
Write an exec-plan before starting.

## Intended behavior

Shortly after a ride syncs, the coach (Soft Floyd persona — see
`docs/design-docs/core-beliefs.md` belief 6) produces a short analysis:
what the ride was, how it compares to recent history, and one or two
concrete observations tied to the rider's stated goal.

## Hard constraint

The analysis must be generated strictly from `available_metrics` for that
activity's **actual recorded sensor streams** — not the rider's declared
profile tier. See
[../design-docs/sensor-capability-model.md](../design-docs/sensor-capability-model.md)
rule 1: a power-meter rider whose battery died mid-ride gets HR-tier
analysis for that one ride, and the analysis should say so plainly (e.g.
"no power data on this one, so I'm reading it through HR drift").

## Building blocks to reuse from v0 (git tag `v0-legacy`)

- `src/coach/rag/chunking.py` — `build_activity_card()`, a deterministic
  ~300-token text summary of a ride, used as retrieval/prompt input.
  Worth reusing as the pattern for activity cards, extended to include
  which sensor streams were present.
- `src/coach/rag/retriever.py` — pre-filter + vector search over similar
  past rides.
- `src/coach/agent/coach.py`, `tools.py`, `prompts/system.md` — the
  streaming tool-use loop and persona prompt. The persona content is
  reusable near-verbatim; the tool list must be re-scoped to the
  MCP-first tools in `apps/server/src/soft_floyd_server/mcp_server.py`
  and gated by `get_available_metrics`.
- `src/coach/web/cost.py` — token/cost accounting, superseded by
  `packages/core/src/soft_floyd_core/llm/client.py`'s `Usage` dataclass
  in this repo, but the per-message persistence pattern is worth
  reviewing.

## Acceptance (draft — refine in the exec-plan)

- Every generated analysis references only metrics present in
  `available_metrics` for that specific activity.
- The response never states a numeric power value unless that activity's
  FIT data included power.
- Token/cost is recorded for every generation, visible via a cost
  endpoint/tool consistent with the ~$5-10/month cap in `AGENTS.md`.
