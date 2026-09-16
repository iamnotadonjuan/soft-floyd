# RAG Corpus Strategy

Not yet implemented — recorded ahead of time so the eventual exec-plan
has a starting design. Out of scope for the scaffold.

## Goal

Feed the coach agent real training literature (road and MTB) so its
advice is grounded in established training science, not just this
rider's own ride history. v0 already had a working RAG pipeline over ride
history (`src/coach/rag/`, preserved at git tag `v0-legacy`) — this
extends the same mechanism to a second corpus: books, not rides.

## Design sketch

- **Two retrieval corpora, not one.** Ride-history retrieval (similar
  past rides, recent trend) stays separate from book retrieval (training
  principles). The coach's context assembly combines both, but they're
  chunked and embedded independently since their update cadence and
  chunking strategy differ (rides arrive continuously; books are static
  once ingested).
- **Chunking** — semantic sections (a book's own chapter/heading
  structure) rather than fixed-token windows where the source has
  structure to exploit; fall back to ~300-token windows with overlap
  otherwise. Store the section title/citation alongside the chunk so the
  coach can cite "per [Book], on threshold training..." rather than
  presenting borrowed advice as its own.
- **Embeddings** — reuse the pinned model,
  `packages/core/src/soft_floyd_core/llm/client.py`'s
  `text-embedding-3-small`, for both corpora so a single vector search
  path (`sqlite-vec`, as in v0) serves both.
- **Retrieval filtering** — filter book chunks by the rider's
  `primary_discipline` (road vs. mtb) and, where a chunk is
  power/HR-specific, by the rider's current `capability_tier` — don't
  retrieve a section about reading a power curve for a rider with no
  power meter. This is the same sensor-honesty rule as
  [sensor-capability-model.md](sensor-capability-model.md), applied to
  retrieved content, not just computed metrics.
- **Cost** — embedding a handful of books is a one-time cost; keep it
  logged through the same `Usage`/`cost_usd` accounting as chat, so it's
  visible against the ~$5-10/month cap even though it's not per-ride.

## Open questions for the eventual exec-plan

- Which books, and do we have the right to store/embed their full text
  locally? (Personal use, not redistributed — but confirm before
  ingesting anything not owned outright.)
- Chunk size/overlap tuning once real source material is in hand.
