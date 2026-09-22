# Tech Debt Tracker

One line per deliberately deferred item: what, why, and when to revisit.

| Item | Why deferred | Revisit when |
|---|---|---|
| ~~No Alembic~~ — **resolved in 0002-garmin-sync**, `packages/core/src/soft_floyd_core/migrations/` | — | — |
| ~~Garmin OAuth/token storage not rebuilt~~ — **resolved in 0002-garmin-sync**, `soft_floyd_core.garmin.client.GarminClient` | — | — |
| v0 (git tag `v0-legacy`) metrics module not carried forward: `src/coach/metrics/compute.py`, `src/coach/metrics/zones.py` | The HR-based formulas (zones, drift, decoupling, TRIMP, GAP, VAM) are correct and tested but need adapting to the new `Record`/`Activity` schema | `docs/design-docs/training-signal-model.md` — pull from the tag rather than re-deriving |
| Historical backfill not implemented | Out of scope for 0002 — first sync ingests only the single most recent activity (`FIRST_RUN_INGEST_LIMIT`), older rides are never picked up automatically | A dedicated backfill exec-plan, reusing v0's `src/coach/ingest/backfill.py`'s paginated/throttled shape |
| Manual FIT upload (`ingest-fit <path>`) not implemented | Deliberately dropped from 0002's scope (automatic sync only) | If/when an offline-import need shows up; v0's `ingest_single_fit` is a reference, though it duplicated the pipeline rather than reusing it — fix that if reviving it |
| Wellness/HRV/sleep sync not implemented | Out of scope for 0002 (ride sync only) | A daily-readiness exec-plan; v0's `GarminClient.get_wellness` is a reference |
| `Record` time-series has no downsampling | Rides over the ~3MB estimated size (`_RECORD_SIZE_LIMIT_BYTES`) store zero raw records — `record_count`/sensor flags still work, but no per-second chart data survives for those rides | If/when a lap/chart UI needs long-ride data; decimate instead of dropping entirely |
| `available_metrics_for_activity`'s stream mapping is coarse | `_STREAM_BY_METRIC` maps `gap`/`vam` to the GPS stream and `decoupling` to HR only, though both really need two streams (HR+pace, HR+power) | The training-metrics exec-plan, once real formulas are implemented and can define their own precise sensor requirements |
| Non-cycling activity types are invisible | `GarminClient.list_recent_activities` hardcodes `activitytype="cycling"` (matches v0 and this app's scope) | If Soft Floyd ever coaches other sports |
| ~~RAG / book corpus not implemented~~ — **resolved in 0005-tiny-book-rag** | — | — |
| Book retrieval has no OCR, chapter-aware chunking, or sensor-topic tags | No real book files were supplied for tuning; this phase only exposes cited passages | Review once books are imported and before generated coaching uses passages |
| Coach agent / chat / cost dashboard not implemented | Depends on Garmin sync (done) + training signal model existing first | After the metrics exec-plan lands |
| Settings screen for editing sensors/profile post-onboarding | `PUT /api/profile` already supports partial updates; only the UI is missing | Whenever a rider needs to change hardware outside first run |
| CORS origin hardcoded to `http://localhost:5173` in `apps/server/.../main.py` | Only dev origin exists today; no production static-serving story yet | When `COACH_SERVE_FRONTEND`-style production serving is added |
| No activities/sync UI in `apps/web` | Scaffold's `Dashboard.tsx` still shows the "no rides synced yet" empty state even once rides exist | A dashboard/activity-list exec-plan for the web UI |
