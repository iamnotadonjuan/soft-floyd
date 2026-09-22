# 0005 — Tiny training book RAG

## Context

The coach needs cited training literature from two or three rider-supplied PDFs.
This phase provides import, semantic retrieval, and verified latest-ride context;
generated coaching remains a later feature.

## Design

Follow `docs/design-docs/rag-corpus-strategy.md`, `core-beliefs.md`, and
`sensor-capability-model.md`. Extract selectable PDF text with page numbers,
chunk it, and embed through the pinned LLM client. Store float32 embeddings in
SQLite and rank the small corpus exactly in Python. Keep ride context as a
direct database read, with per-activity sensor gating. Core owns every rule;
MCP and REST only adapt the same result.

## Steps

1. Add Alembic-managed book, passage, and LLM-usage tables and PDF dependency.
2. Implement idempotent CLI import and persistent per-call embedding usage.
3. Implement semantic passage retrieval plus ride/profile context in core.
4. Add one MCP tool and matching REST endpoint; update design/product docs.

## Verification

- Test page citations, textless PDF rejection, duplicate import, ranking, and
  usage recording with a fake embedding client.
- Test latest/missing rides and absent sensor streams; compare MCP and REST.
- Run `make check` and the migration drift test.

## Outcome

Book import, core retrieval, MCP and REST adapters, schema reference, and
tests are implemented. The isolated staged snapshot passes the full Python
suite (102 tests) and Ruff checks. The shared working checkout contains
concurrent exec-plan 0004 work, so its full check currently fails in that
work's unfinished migration and profile tests. No RAG test fails.

Quality self-score (`docs/QUALITY_SCORE.md`): correctness 1/1 in the
isolated snapshot; single source of truth 1/1;
sensor honesty 1/1; tests 1/1; docs 1/1; scope 1/1; local-only 1/1.
