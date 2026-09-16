# Tech Debt Tracker

One line per deliberately deferred item: what, why, and when to revisit.

| Item | Why deferred | Revisit when |
|---|---|---|
| No Alembic — schema created via `Base.metadata.create_all()` | Scaffold has one table with no migration history to manage yet | The first change to `RiderProfile` or new table after this commit |
| v0 (git tag `v0-legacy`) domain modules not carried forward: `src/coach/ingest/fit_parser.py`, `src/coach/metrics/compute.py`, `src/coach/metrics/zones.py`, `src/coach/classify/bike_type.py`, `tests/fixtures/*.fit` | User chose clean-slate scaffold over immediate salvage; the logic is correct and tested but the module layout changed | `docs/product-specs/garmin-sync.md` and the metrics module in `docs/design-docs/training-signal-model.md` — pull from the tag rather than re-deriving |
| Garmin OAuth/token storage not rebuilt | Out of scope for scaffold | Same exec-plan as garmin-sync.md |
| RAG / book corpus not implemented | Out of scope for scaffold; needs source material decided first | See open questions in `docs/design-docs/rag-corpus-strategy.md` |
| Coach agent / chat / cost dashboard not implemented | Depends on Garmin sync + training signal model existing first | After both land |
| Settings screen for editing sensors/profile post-onboarding | `PUT /api/profile` already supports partial updates; only the UI is missing | Whenever a rider needs to change hardware outside first run |
| CORS origin hardcoded to `http://localhost:5173` in `apps/server/.../main.py` | Only dev origin exists today; no production static-serving story yet | When `COACH_SERVE_FRONTEND`-style production serving is added |
