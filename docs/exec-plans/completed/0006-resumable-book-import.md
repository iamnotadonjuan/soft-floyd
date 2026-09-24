# 0006 — Resumable training-book import

## Context

Three rider-supplied, selectable-text PDFs produce 2,582 passages. The
current importer pays for each embedding but saves passages only after an
entire book succeeds, so an interruption repeats work. Done means these
books are imported once, are searchable with citations, and interrupted
imports resume without duplicating completed embeddings.

## Design

Keep PDF extraction, embeddings, and retrieval in core. Add import status
to books and stable passage ordinals through Alembic. Save each passage
with its usage record. Only complete books participate in retrieval.
Existing books migrate as complete. The source PDFs stay outside the repo.

## Steps

1. Add the migration and resumable core import with CLI progress.
2. Add interruption, resume, migration, and retrieval tests; update docs.
3. Back up the local database, migrate, import the three PDFs, and verify
   counts and retrieval through MCP and REST.

## Verification

Run `make check`, the migration drift guard, and representative queries
with title and PDF page citations. Self-score against `docs/QUALITY_SCORE.md`.

## Outcome

Implemented passage checkpoints, resume validation, progress, and hiding of
incomplete books. Backed up and migrated the local SQLite database. Imported
all three books: 816 passages from *The Cyclist’s Training Bible*, 952 from
*Mastering Mountain Bike Skills*, and 814 from *Training and Racing with a
Power Meter*. The 2,582 import embedding calls cost about $0.011 according
to `llm_usage`. Representative training-context queries returned the
expected titles and PDF pages, with matching MCP and REST results.

`make check` passed: 140 tests, Ruff checks, and web typecheck. Database
integrity check passed. Quality self-score: correctness 1/1; single source
of truth 1/1; sensor honesty 1/1; tests 1/1; docs 1/1; scope 1/1;
local-only 1/1. Generated coaching remains a separate planned feature.
