# Design Docs

These capture *why*, not *what* — durable beliefs and models that
constrain design decisions across features. If you're about to make a
judgment call that isn't covered here, consider whether it belongs here
once made.

- [core-beliefs.md](core-beliefs.md) — the handful of beliefs that should
  outlive any single feature.
- [mcp-first-backend.md](mcp-first-backend.md) — why the backend is
  FastMCP-first with REST as a derived surface.
- [sensor-capability-model.md](sensor-capability-model.md) — **the
  load-bearing doc.** What the coach may compute and say, gated by what
  hardware the rider actually has.
- [training-signal-model.md](training-signal-model.md) — the two metric
  families (power-based, HR-based) and the formulas within each.
- [rag-corpus-strategy.md](rag-corpus-strategy.md) — how training-book
  content will be chunked, retrieved, and cited once RAG is built.
