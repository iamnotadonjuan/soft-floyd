# RAG Corpus Strategy

Book ingestion and retrieval are implemented in exec-plan 0005. Ride-history
retrieval and generated coaching are future work.

## Goal

Give the coach cited training literature alongside verified ride facts, so
later advice can refer to sources without inventing sensor measurements.

## Current design

- **Two sources.** The latest ride is read directly from SQLite with
  per-activity sensor gating. Book passages are retrieved semantically.
  Similar past rides and trend retrieval remain a later feature.
- **Chunking.** Selectable PDF text is split within page boundaries into
  220-word windows with 40-word overlap. Book title, author, and PDF page
  number accompany every result.
- **Embeddings.** Reuse the pinned `text-embedding-3-small` model. Store
  float32 vectors as SQLite BLOBs and calculate exact cosine similarity in
  Python for this small, static corpus. The PDF source is not committed.
- **Retrieval safety.** Passages are cited source material, not claims about
  a ride. The ride context checks actual FIT streams. Sensor-topic passage
  filtering belongs in the generated coaching phase, before an agent can
  turn power-only guidance into unsupported advice for an HR-only rider.
- **Cost.** Record each book and query embedding call in `llm_usage` using
  `LLMClient`'s pinned pricing.
- **Interrupted imports.** Save each embedded passage with its usage record.
  Resume by source-file hash and passage order; only complete books can be
  retrieved. Existing imported books remain complete after migration.

## Remaining decisions for generated coaching

- The rider selected *The Cyclist's Training Bible*, *Mastering Mountain Bike
  Skills*, and *Training and Racing with a Power Meter*. Their local PDFs
  contain selectable text; embeddings require an OpenAI API key.
- Whether real books need chapter-aware chunking or OCR.
