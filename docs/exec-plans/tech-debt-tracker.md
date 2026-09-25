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
| ~~Coach agent / chat~~ — **resolved in 0007-coach-agent** | — | — |
| No LLM cost dashboard | 0007 enforces a monthly budget from `llm_usage` but only surfaces it as an error when reached | When the rider wants to see spend before hitting the cap |
| Coach history is a fixed last-12-message window | Long threads silently drop early context; no summarization | If riders keep very long threads — summarize older turns or lean on memory notes |
| Coach can't compute HR zones/TRIMP/NP | Those metrics don't exist yet; the coach only sees summary averages that passed the sensor gate | The training-metrics exec-plan — then add coach tools over them |
| Coach guardrail has no live eval suite | Unit tests fake the classifier; 0007 verified 9 live prompts by hand | Before changing the classifier prompt or model |
| ~~Settings screen for editing sensors/profile post-onboarding~~ — **resolved in 0004-rider-profile-and-connections-ui**, `apps/web/src/pages/Settings.tsx` | — | — |
| CORS origin hardcoded to `http://localhost:5173` in `apps/server/.../main.py` | Only dev origin exists today; no production static-serving story yet | When `COACH_SERVE_FRONTEND`-style production serving is added |
| ~~No activities/sync UI in `apps/web`~~ — **resolved in 0005-rider-ui-and-history** | — | — |
| Web manual Sync now control | This UI change focused on automatic sync health and browsing rides; manual sync remains available through REST, MCP, and CLI | If the rider needs to trigger sync without waiting for the background poller |
| `activities/classify.py` isn't garage-aware | A rider can own a `Bike` with `kind="gravel"`, but the FIT/summary-based activity classifier (`BikeType`) still only ever produces `road`/`mtb`/`indoor`/`other` — a gravel ride is classified as `mtb` by its heuristic, never linked back to the specific `Bike` it was ridden on | A ride-to-bike linking exec-plan; likely needs a `bike_id` FK on `Activity` and either a rider confirmation step or a stronger heuristic (sub_sport/GPX-shape) to distinguish gravel from mtb |
| No per-bike FTP | `ftp_watts`/`lthr` remain profile-level anchors even though power meters are now per-bike (exec-plan 0004) — a rider with two power-meter bikes (e.g. road + TT) has one FTP for both | Revisit once a rider actually has this setup; likely move `ftp_watts` onto `Bike` alongside its `has_power_meter` flag |
| UI language choice is browser-only | 0008 stores EN/ES in `localStorage` (`i18n/I18nProvider.tsx`) because the profile has no settings field yet | When the profile gains rider settings: persist `locale` there, and only the provider changes |
| Coach replies and server messages aren't localized | 0008 translates the web UI's own copy only. Coach replies follow whatever language the rider writes in. API error `detail`s and coach `tool_status` lines are always English | If Spanish riders need them: send the locale with coach turns, add a reply-language line to the core prompt, and localize the core error strings |
| External MCP client credentials | 0009 issues short-lived MCP grants only inside an authenticated web coach request; there is no account grant flow for Claude Desktop/Code | When a rider needs an external MCP host, design a scoped, revocable grant and client setup |
| Remote hosting and HTTPS | 0009 keeps the loopback bind and local HTTP cookie defaults | Before any remote deployment, add HTTPS, secure cookies, configurable origins and deployment review |
| Per-account LLM billing | 0009 attributes usage to accounts while retaining one global spending cap and API key | When account-specific budgets or payments are planned |
| Rich account Profile | 0009 displays Google identity, local ID and sign-out only; training details remain in Settings | When profile editing and account preferences are planned |
