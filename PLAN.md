# Soft Floyd — Personal Cycling Coach (Phased Implementation Plan)

> This document is written so another LLM-coding agent (Codex, Claude Code, Cursor) can pick up any phase and implement it without further context. Each phase is independently shippable and testable. Do not skip phases — Phase 2 depends on Phase 1's data model; Phase 3 depends on Phase 2's coach API.

---

## Context & Goal

Build "Soft Floyd," a personal AI cycling coach that connects to Garmin Connect, automatically ingests rides finished on a Garmin Edge 1050 (road / MTB / indoor), reasons about HR-based metrics (no power meter), and gives kind, encouraging, actionable feedback through a conversational web UI. Single user, runs locally on macOS, **LLM cost cap $5–10/month** for ~22 rides/month.

Three phases:
1. **Phase 1 — Ingest**: stand up the Garmin pipeline. Activity finishes on the Edge → SQLite has parsed records within ~10 min. Headless, CLI-only.
2. **Phase 2 — Coach + RAG**: layer on the AI. New activity → embedded → retrieved against history → Claude Haiku generates a Soft Floyd analysis. Still CLI/HTTP-only.
3. **Phase 3 — UI**: React + Vite frontend talking to the FastAPI backend with SSE-streamed chat.

---

## Global Decisions (apply across all phases)

| Area | Choice | Notes |
|---|---|---|
| Language / runtime | Python 3.12 | Pinned in `.python-version` |
| Package manager | `uv` | Single `pyproject.toml` + `uv.lock` |
| Storage | SQLite + `sqlite-vec` extension | One file at `data/trainer.db` |
| ORM / migrations | `sqlalchemy` 2.x + `alembic` | All schema changes via migrations |
| Config | `pydantic-settings` | Reads `~/.coach/config.toml` + env |
| CLI | `typer` | `coach login`, `coach backfill`, `coach run` |
| Logging | `structlog` JSON | One config in `coach/log.py` |
| Secret storage | macOS Keychain via `keyring` + `cryptography.fernet` | Garmin tokens encrypted at rest |
| Testing | `pytest` + `pytest-asyncio` + `respx` | Real fixtures from one anonymized FIT file |
| Linting | `ruff` (lint + format) | `ruff check` and `ruff format` in CI |
| Folder root | `/Users/juancamargo/Projects/ai/trainer/` | Currently empty |

### Project layout (created incrementally — full target)

```
trainer/
  pyproject.toml
  uv.lock
  .python-version          # "3.12"
  .gitignore               # data/, .env, __pycache__, node_modules, dist
  README.md
  alembic.ini
  src/coach/
    __init__.py
    config.py
    log.py
    cli.py
    store/
      __init__.py
      models.py
      session.py
      migrations/
    ingest/                # Phase 1
      __init__.py
      garmin_client.py
      poller.py
      fit_parser.py
      backfill.py
    metrics/               # Phase 1
      __init__.py
      compute.py
      zones.py
    classify/              # Phase 1
      __init__.py
      bike_type.py
    rag/                   # Phase 2
      __init__.py
      chunking.py
      embedder.py
      retriever.py
    agent/                 # Phase 2
      __init__.py
      coach.py
      tools.py
      prompts/
        system.md
    web/                   # Phases 2 & 3
      __init__.py
      api.py
      sse.py
      cost.py
  frontend/                # Phase 3
    package.json
    vite.config.ts
    tsconfig.json
    index.html
    src/
      main.tsx
      App.tsx
      api/client.ts
      api/sse.ts
      pages/ActivityList.tsx
      pages/ActivityDetail.tsx
      components/Chart.tsx
      components/ChatPanel.tsx
      components/LapTable.tsx
  tests/
    test_fit_parser.py
    test_metrics.py
    test_classifier.py
    test_retriever.py
    test_coach.py
    fixtures/
      sample_road.fit
      sample_mtb.fit
      sample_indoor.fit
  data/                    # gitignored
```

### Final data model (built incrementally; Phase 1 ships #1–6, Phase 2 adds #7–9)

1. **`activity`** — `id` (PK, Garmin activityId, INTEGER), `start_time` (DATETIME UTC), `sport` (TEXT), `sub_sport` (TEXT), `is_indoor` (BOOL), `bike_type` (TEXT, one of `road|mtb|indoor|other`), `distance_m` (REAL), `duration_s` (REAL), `elev_gain_m` (REAL), `avg_hr` (INT), `max_hr` (INT), `tss_proxy` (REAL nullable), `fit_path` (TEXT), `raw_summary_json` (JSON), `ingested_at` (DATETIME)
2. **`lap`** — `id` (PK), `activity_id` (FK), `lap_index` (INT), `distance_m`, `duration_s`, `avg_hr`, `avg_speed`, `elev_gain_m`, `gap_speed`
3. **`record`** — optional time-series; only persisted if needed for charts (see Phase 1 task 1.7). Columns: `activity_id`, `t_offset_s`, `hr`, `speed_mps`, `altitude_m`, `cadence`, `lat`, `lon`. Indexed on `(activity_id, t_offset_s)`.
4. **`metrics`** — `activity_id` (PK/FK), `decoupling_pct`, `hr_drift_pct`, `time_in_z1`, `time_in_z2`, `time_in_z3`, `time_in_z4`, `time_in_z5`, `vam_best_20min`, `gap_normalized`
5. **`wellness_daily`** — `date` (PK), `hrv_overnight`, `sleep_score`, `body_battery_low`, `body_battery_high`, `resting_hr`, `acute_load`, `chronic_load`, `acwr`
6. **`poll_cursor`** — single row: `last_seen_activity_id`, `last_poll_at`, `last_poll_status`
7. **`embedding`** — `id`, `activity_id` (FK), `chunk_type` (TEXT: `summary`|`lap`|`wellness`), `text` (TEXT), `created_at`. Vectors stored in a parallel `embedding_vec` `vec0` virtual table keyed by `id`.
8. **`conversation`** — `id`, `activity_id` (FK), `started_at`
9. **`message`** — `id`, `conversation_id` (FK), `role` (TEXT), `content_json` (JSON), `tokens_in`, `tokens_out`, `cache_read`, `cache_write`, `cost_usd`, `created_at`
10. **`garth_token`** — single encrypted blob row + refresh metadata (created in Phase 1)

---

# PHASE 1 — Garmin Ingest Pipeline

**Goal:** When you finish a ride on the Edge 1050 and it syncs to Garmin Connect, within ~10 minutes a row exists in `activity`, the FIT file is parsed into `lap` + `metrics`, wellness for the day is captured, and the activity is classified as `road | mtb | indoor`. Headless. CLI-only.

**Out of scope:** AI, embeddings, RAG, web UI.

## Phase 1 — Technologies

| Purpose | Library | Pinned version family |
|---|---|---|
| Garmin Connect client | `garth` | `>=0.5,<1.0` |
| FIT parser | `fitdecode` | `>=0.10,<1.0` |
| Scheduler | `apscheduler` | `>=3.10,<4.0` |
| Numerics | `numpy`, `pandas` | latest stable |
| Notifications (re-auth prompt) | `pync` | latest stable |
| Secrets | `keyring`, `cryptography` | latest stable |
| ORM / migrations | `sqlalchemy`, `alembic` | latest stable |
| sqlite-vec loader | `sqlite-vec` (Python wheel) | `>=0.1.0,<0.2.0` (loaded in Phase 1 so the schema can include the vec table later without re-migrating SQLite extension load order) |

## Phase 1 — Step-by-step tasks

**1.1 Repo bootstrap**
- `uv init` in `trainer/`. Add deps above. Create `.python-version`, `.gitignore`.
- Add `ruff` + `pytest` config to `pyproject.toml`.
- Create `src/coach/__init__.py`, `src/coach/config.py`, `src/coach/log.py`, `src/coach/cli.py` (typer skeleton with `login`, `backfill`, `run` no-op commands).
- Acceptance: `uv run coach --help` lists three commands.

**1.2 SQLite + Alembic setup**
- Create `src/coach/store/session.py` (engine factory; loads `sqlite-vec` extension on every connection via `sqlalchemy` event listener `connect`).
- Create `src/coach/store/models.py` with tables #1, #2, #4, #5, #6, #10 from the data model. Use `sqlalchemy` 2.x typed `Mapped` syntax.
- `alembic init src/coach/store/migrations`. Generate first migration; apply.
- Acceptance: `alembic upgrade head` creates `data/trainer.db`; `sqlite3 data/trainer.db ".tables"` lists expected tables.

**1.3 Garmin client wrapper (`ingest/garmin_client.py`)**
- Class `GarminClient` wrapping `garth.Client`.
- `login(email, password, mfa_callback)` — performs login, calls `client.dumps()`, encrypts via Fernet (key stored in macOS Keychain under service `coach-soft-floyd`, account `garth-token-key`, autocreated on first login), writes to `~/.coach/garth.json`.
- `load_from_disk()` — decrypts and resumes session. On `GarthHTTPError(401)`, raise `ReauthRequired`.
- `list_activities(start_dt, limit)` — returns list of summary dicts (id, start_time, sport, sub_sport, isIndoor, distance, duration, elevation_gain, avg_hr, max_hr, raw json).
- `download_fit(activity_id, dest_path)` — saves the original FIT to `data/fit/{activity_id}.fit`.
- `get_wellness(date)` — returns HRV, sleep, body battery, RHR for a date.
- Acceptance: `uv run coach login` walks through email/password/MFA prompt, persists token, second run reuses token without prompt.

**1.4 FIT parser (`ingest/fit_parser.py`)**
- Function `parse_fit(path) -> ParsedFit` returning a dataclass with `session` (overall summary), `laps` (list), `records` (list, optional store).
- Use `fitdecode.FitReader`. Skip developer fields we don't need; preserve raw FIT file path.
- Acceptance: parsing each fixture in `tests/fixtures/*.fit` returns expected lap counts (golden test).

**1.5 Metrics computation (`metrics/compute.py`, `metrics/zones.py`)**
- `zones.py`: HR zone boundaries derived from configured LTHR (in `~/.coach/config.toml`; default 165). 5 zones (Z1 <80% LTHR, Z2 80–89%, Z3 90–94%, Z4 95–99%, Z5 ≥100%).
- `compute.py`: `compute_metrics(parsed_fit)` returning dict matching the `metrics` table:
  - `time_in_zN` from records
  - `hr_drift_pct` = (avg HR second half − avg HR first half) / avg HR first half × 100
  - `decoupling_pct` = ratio of (HR/speed) first half vs second half, × 100
  - `gap_normalized` = grade-adjusted average speed (use simple Strava-like formula)
  - `vam_best_20min` = best 20-min vertical ascent rate
  - `tss_proxy` = TRIMP ((duration_min × HR_ratio × 0.64 × e^(1.92 × HR_ratio)))
- Acceptance: unit tests on each metric vs hand-computed values for the sample road FIT.

**1.6 Bike-type classifier (`classify/bike_type.py`)**
- `classify(activity_summary, parsed_fit) -> Literal["road","mtb","indoor","other"]`
- Rules in this exact order:
  1. `is_indoor=True` → `indoor`
  2. `sub_sport in {"mountain","gravel_cycling","cyclocross"}` → `mtb`
  3. `sub_sport in {"road","virtual_ride"}` → `road` (downgrade `virtual_ride` to `indoor` if no GPS records)
  4. Heuristic: `avg_speed_kmh > 22` AND `elev_gain_per_km < 15` → `road`, else `mtb`
- LLM fallback explicitly NOT in Phase 1. Default ambiguous → `other`.
- Acceptance: golden tests on three fixtures classify correctly.

**1.7 Poller (`ingest/poller.py`)**
- `APScheduler` `AsyncIOScheduler` with `IntervalTrigger(minutes=10)`.
- Job: fetch activities since `poll_cursor.last_seen_activity_id`. For each new one:
  1. `INSERT OR IGNORE` into `activity` (initially with raw summary)
  2. Download FIT
  3. Parse FIT → upsert `lap`, optional `record` (store records only if total < 3MB to keep DB small)
  4. Compute metrics → upsert `metrics`
  5. Pull wellness for `start_time::date` → upsert `wellness_daily`
  6. Classify bike type → update `activity.bike_type`
  7. Emit log line `activity_ingested activity_id=… bike_type=…`
- On `ReauthRequired`: send macOS notification via `pync` ("Soft Floyd needs Garmin re-auth"), do NOT silently retry.
- Backoff: exponential up to 60 min on 429/5xx.
- Acceptance: `uv run coach run` started in foreground; after a short test ride, an `activity` row appears within 15 minutes with all derived columns populated.

**1.8 Backfill command (`ingest/backfill.py`)**
- `coach backfill --days 365` — paginates `list_activities` 20-at-a-time backwards, throttled to ≤1 req/sec. Reuses the same per-activity pipeline as the poller.
- Idempotent: re-running skips already-ingested IDs.
- Acceptance: after running, `SELECT COUNT(*) FROM activity` matches your Garmin Connect ride count for the period (±2 for in-flight syncs).

## Phase 1 — Acceptance criteria (must all pass before Phase 2)

> **Phase 1 COMPLETE** — implemented 2026-05-11.

- [x] `uv run coach login` completes MFA flow and persists encrypted token.
- [x] `uv run coach backfill --days 365` ingests last 12 months of rides into all Phase 1 tables.
- [x] `uv run coach run` polls every 10 min; a brand new test ride lands in SQLite within 15 min, fully classified.
- [x] `pytest` passes with at least: parser fixtures, metric correctness, classifier rules. (41 tests passing)
- [x] No LLM calls and no embedding calls have been made (zero AI cost in Phase 1).

---

# PHASE 2 — Coach Agent + RAG

**Goal:** When Phase 1's pipeline ingests a new activity, automatically embed it, retrieve relevant history, and generate a Soft Floyd analysis via Claude Haiku 4.5 with prompt caching. Expose two HTTP endpoints (`GET activity analysis`, `POST activity chat`) so Phase 3 has something to talk to. Still no UI.

**Depends on:** Phase 1 (uses `activity`, `lap`, `metrics`, `wellness_daily`).

## Phase 2 — Technologies

| Purpose | Library | Notes |
|---|---|---|
| LLM | `anthropic` SDK | Model: `claude-haiku-4-5-20251001`. Use `cache_control: {"type": "ephemeral"}` on system block. Stream with `client.messages.stream()`. |
| Embeddings | `openai` SDK | Model: `text-embedding-3-small`, 1536-dim |
| Vector store | `sqlite-vec` (already loaded in Phase 1) | Add `embedding_vec` `vec0` virtual table |
| Web framework | `fastapi`, `uvicorn` | Local-only bind `127.0.0.1` |
| Streaming | `sse-starlette` | For chat endpoint |
| Pricing logic | hand-rolled in `coach/web/cost.py` | Reads token counts from Anthropic response |

## Phase 2 — Step-by-step tasks

**2.1 Schema migration**
- Add tables #7 `embedding` (regular table) and #7b `embedding_vec` (vec0 virtual, dim=1536, keyed on `id`), #8 `conversation`, #9 `message`. Alembic migration.
- Acceptance: migration applies cleanly on top of Phase 1 DB.

**2.2 Activity-card chunking (`rag/chunking.py`)**
- Function `build_activity_card(activity, laps, metrics, wellness_for_date) -> str` returning a deterministic ~300-token text block:
```
2026-04-15 | road | 62.3 km / 2h08 / 845 m gain
HR avg/max: 142/178 — Z1 8% Z2 51% Z3 28% Z4 12% Z5 1%
Decoupling 3.2% (good aerobic stability). HR drift 1.8%.
Top climb: VAM 870 m/h over 18 min on "Cerro X".
Wellness that morning: HRV 54 (baseline 52), sleep 7h45 (score 82), Body Battery 42→89.
Narrative: steady Z2 endurance with a sustained Z3/4 effort on the main climb.
```
- Function `build_wellness_chunk(date_range)` — weekly summary of HRV trend, sleep, ACWR.
- Acceptance: snapshot tests on a fixed activity produce stable output.

**2.3 Embedder (`rag/embedder.py`)**
- `embed_activity(activity_id)` — builds card, calls `client.embeddings.create(model="text-embedding-3-small", input=text)`, inserts into `embedding` and `embedding_vec`.
- `embed_weekly_wellness(week_start)` — same flow with chunk_type=`wellness`.
- Idempotent: re-embedding upserts.
- Acceptance: after first call for a known activity, `SELECT COUNT(*) FROM embedding WHERE activity_id=?` returns 1.

**2.4 Retriever (`rag/retriever.py`)**
- `retrieve_for_activity(activity_id) -> RetrievalContext`:
  1. Pre-filter SQL: same `bike_type`, last 90 days **plus** all-time top-5 by similar `duration_s` bucket (±20%)
  2. Cosine top-8 from `embedding_vec` (`MATCH` query) over the pre-filtered set
  3. Always include: last 7 days `wellness_daily`, last 3 activities chronologically, current activity card
- Returns a structured object with: `current_card`, `similar_cards: list[str]`, `recent_cards: list[str]`, `wellness_summary: str`
- Acceptance: integration test on the seeded backfill DB returns 8–11 chunks with expected bike type filter.

**2.5 Wire ingest → embed**
- After Phase 1's per-activity pipeline succeeds, dispatch `embed_activity(activity_id)` (in-process, sync — embedding is sub-second). Add to `ingest/poller.py` and `ingest/backfill.py`.
- Acceptance: post-backfill, every activity has exactly one `summary`-type embedding row.

**2.6 Coach prompt (`agent/prompts/system.md`)**
- ~2000-token Markdown file containing:
  - **Persona**: "You are Soft Floyd. Kind, encouraging cycling coach. Celebrates small wins. Honest but never harsh. Focuses on long-term progress over single-ride judgements."
  - **Methodology**: HR-zone definitions, no-power-meter rules ("never fabricate watts; reason in HR drift, decoupling, GAP, VAM, time-in-zone"), bike-type-specific framing (road = aerobic efficiency / climbing economy / pacing; mtb = HR variability handling / technical recovery; indoor = Z2 base or structured intervals).
  - **Output format**: `## TL;DR` (1–2 sentences) → `## What went well` (1–3 bullets) → `## What to watch` (1–2 bullets) → `## Next session suggestion` (1 paragraph).
  - **Tool usage rules**: when to call each tool, when not to.

**2.7 Tool layer (`agent/tools.py`)**
- All tools are read-only Python functions exposed via Anthropic tool-use schema:
  - `fetch_ride_detail(activity_id: int)` → full lap+metric breakdown
  - `compare_to_ride(activity_id_a: int, activity_id_b: int)` → metric diff
  - `get_recent_load(days: int = 28)` → ACWR + per-day TRIMP
  - `get_wellness_window(days: int = 14)` → HRV, sleep, RHR series
  - `find_similar_routes(activity_id: int)` → activities with overlapping geo bounding box
- Each function returns JSON-serializable dict.
- Acceptance: unit tests verify each tool against the seeded backfill DB.

**2.8 Coach orchestration (`agent/coach.py`)**
- `class CoachSession`:
  - `__init__(activity_id)`: loads RetrievalContext, builds messages.
  - `initial_analysis() -> AsyncIterator[str]`: calls Anthropic with:
    - `system`: list with one block `{"type":"text","text": <system.md contents>, "cache_control":{"type":"ephemeral"}}`
    - `messages`: one user message containing the structured ride summary + retrieved context (uncached)
    - `tools`: schemas from `tools.py`
    - `tool_choice`: `{"type":"auto"}`
    - Stream content; on `tool_use` block, execute tool synchronously, append `tool_result`, continue loop. Cap at 5 tool calls.
  - `chat(user_message) -> AsyncIterator[str]`: loads conversation history, re-sends cached system block, appends prior turns + new user message. Same streaming + tool loop.
- Persist every turn to `message` with full token + cache + cost accounting via `web/cost.py`.
- Acceptance: against a real ride, `initial_analysis()` returns a Soft-Floyd-formatted string in <10s with at least one cache_read on the second call within 5 min.

**2.9 Cost meter (`web/cost.py`)**
- Constants: Haiku 4.5 input $1/MTok, output $5/MTok, cache write 1.25× input, cache read 0.10× input.
- `record_usage(usage_dict) -> Decimal`: writes to `message` row.
- `monthly_total() -> dict`: aggregates by current calendar month.
- Acceptance: after one chat, `SELECT SUM(cost_usd) FROM message` returns a non-zero Decimal matching hand calc.

**2.10 Minimal HTTP surface (`web/api.py`, `web/sse.py`)**
- `POST /api/activities/{id}/analysis` — triggers (or re-runs) `initial_analysis`, persists conversation, returns final assistant text. (Synchronous JSON for now; SSE in Phase 3.)
- `GET /api/activities/{id}/analysis` — returns latest conversation's first assistant message.
- `POST /api/activities/{id}/chat` — body `{message: str}`; returns assistant reply (synchronous JSON, full message). Streaming added in Phase 3.
- `GET /api/cost/month` — returns current month's spend.
- Bind `127.0.0.1:8000`. CORS not needed yet.
- Acceptance: `curl -X POST localhost:8000/api/activities/{id}/analysis` returns Soft Floyd's analysis as plain JSON within 15s.

**2.11 Auto-trigger on new activity**
- In poller's per-activity pipeline, after embedding, call `CoachSession(activity_id).initial_analysis()` and persist. (Send macOS notification "Soft Floyd has thoughts on your ride" via `pync`.)
- Acceptance: a brand new ride results in a populated `message` row within 20 min of finishing.

## Phase 2 — Acceptance criteria

- [ ] All 12 months of backfilled activities have `embedding` rows.
- [ ] Triggering analysis on any past ride returns a Soft Floyd response that:
  - includes the right bike-type framing
  - references at least one specific past ride from RAG
  - references current wellness/load
  - never fabricates power numbers
- [ ] Multi-turn chat on the same activity within 5 min shows `cache_read > 0` in the `message` row.
- [ ] `GET /api/cost/month` after a week of rides projects to **< $5/month** at 5 rides/week.

---

# PHASE 3 — React UI

**Goal:** A local web app you open in the browser to see your activities, view a ride's HR/elevation chart and laps, read Soft Floyd's analysis, and chat with him. Chat streams via SSE.

**Depends on:** Phase 2 (consumes `/api/*` endpoints, upgrades chat to SSE).

## Phase 3 — Technologies

| Purpose | Library | Notes |
|---|---|---|
| Frontend framework | React 18 + Vite | TypeScript |
| Routing | `react-router-dom` v6 | |
| HTTP client | `fetch` + a tiny `api/client.ts` wrapper | No axios |
| SSE | native `EventSource` (or `@microsoft/fetch-event-source` for POST + SSE) | needed because chat is `POST` with a body |
| Charts | `recharts` | Easier React API than Chart.js; renders SVG |
| Styling | Tailwind CSS | Fast for a single-user app, no design system needed |
| Date formatting | `date-fns` | |

## Phase 3 — Step-by-step tasks

**3.1 Backend: enable CORS + SSE chat**
- In `web/api.py`: add `CORSMiddleware` allowing `http://localhost:5173` (Vite dev server).
- Replace `POST /api/activities/{id}/chat` with an SSE-streaming endpoint using `sse-starlette.EventSourceResponse`. Each token chunk → `event: token`, on tool call → `event: tool` (for UX feedback "checking your last 4 weeks…"), on complete → `event: done`.
- Add `GET /api/activities` (paginated, query params `?bike_type=&page=&page_size=`).
- Add `GET /api/activities/{id}` — returns full detail: header summary, laps, computed metrics, downsampled time-series for charts (decimate `record` rows to ≤1000 points).
- Add `GET /api/activities/{id}/messages` — full conversation history.
- Acceptance: `curl -N -X POST localhost:8000/api/activities/{id}/chat -d '{"message":"how was my pacing?"}' -H "Content-Type: application/json"` streams SSE events.

**3.2 Frontend bootstrap**
- `cd trainer && npm create vite@latest frontend -- --template react-ts`
- Install: `react-router-dom recharts date-fns @microsoft/fetch-event-source` and Tailwind (`tailwindcss postcss autoprefixer`, init).
- Vite config: proxy `/api` → `http://localhost:8000`.
- Acceptance: `npm run dev` serves an empty Vite app at `localhost:5173`; `/api/cost/month` is reachable through the proxy.

**3.3 API client (`frontend/src/api/client.ts`)**
- Typed wrappers: `listActivities(filter)`, `getActivity(id)`, `getMessages(id)`, `triggerAnalysis(id)`, `streamChat(id, message, onToken, onTool, onDone)` (uses `fetchEventSource` to POST with body and consume SSE).
- Mirror backend types in `frontend/src/api/types.ts`.

**3.4 `ActivityList` page (`pages/ActivityList.tsx`)**
- Table of recent activities (date, bike-type chip, distance, duration, elevation, avg HR, "analyzed" badge).
- Filter chips at top: All / Road / MTB / Indoor.
- Pagination (20 per page).
- Row click → `/activity/:id`.
- Acceptance: open `localhost:5173`, see backfilled rides, filter chips work.

**3.5 `ActivityDetail` page (`pages/ActivityDetail.tsx`)**
- Header card: bike type, date, distance/duration/elevation, avg/max HR, time-in-zone bar.
- `<Chart>` component (`components/Chart.tsx`): dual-axis Recharts `LineChart` — HR (left axis) and elevation (right axis) over time. Brush for zoom.
- `<LapTable>` component: lap rows with HR avg, distance, duration, GAP.
- `<ChatPanel>` component (right column on desktop, below on mobile):
  - Loads existing `messages` on mount.
  - "Generate Soft Floyd's analysis" button if none yet → calls `triggerAnalysis(id)`.
  - Input box + send → `streamChat(...)` appending tokens to a growing assistant bubble.
  - Tool-call events render as faded "checking recent load…" status pills.
- Acceptance: opening a ride shows the chart, laps, and either existing analysis or the trigger button. Sending a message streams Soft Floyd's reply token-by-token.

**3.6 Layout + nav**
- Single top nav: app title "Soft Floyd", link to activity list, monthly cost indicator pulling from `/api/cost/month` (e.g., "$1.42 / $10").
- Tailwind: clean light theme, mobile-first.

**3.7 Production build + serve**
- `npm run build` outputs `frontend/dist/`.
- In `web/api.py`, mount `StaticFiles(directory="frontend/dist", html=True)` at `/` when env var `COACH_SERVE_FRONTEND=1`.
- Update `coach run` to start uvicorn alongside the poller (one process, `asyncio.gather`).
- Acceptance: `COACH_SERVE_FRONTEND=1 uv run coach run` serves the full app at `localhost:8000`.

## Phase 3 — Acceptance criteria

- [ ] Open `localhost:8000` and see all 12 months of backfilled rides in the list.
- [ ] Filter chips correctly narrow by bike type.
- [ ] Activity detail page shows HR + elevation chart, lap table, and Soft Floyd's analysis.
- [ ] Chat input streams Soft Floyd's tokens in real time and surfaces tool-call status.
- [ ] Monthly cost indicator updates after every chat.
- [ ] After a real test ride, the new activity appears in the list within 15 min and the analysis is auto-generated and visible.

---

## Cross-phase Risks

- **`garth` is unofficial** — pin the version, expect quarterly breakage, build the manual FIT-upload fallback path early in Phase 1 (one extra CLI command `coach ingest-fit <path>`).
- **MFA friction** — implement re-auth notification in Phase 1.7 on day one. Don't silently retry.
- **`sqlite-vec` is young** — pin version. Keep `embedding.text` as the source of truth; vectors can be regenerated.
- **Prompt cache TTL is 5 min** — multi-turn chat stays warm only if user replies quickly. Cost model already assumes some misses.
- **Garmin rate limits** — undocumented. 10-min poll cadence and ≤1 req/sec backfill are conservative.
- **Single-user trust model** — Garmin password lives in macOS Keychain; document recovery if Mac is wiped.

## Definition of Done (overall)

When all three phases are accepted, the user finishes a ride on the Edge 1050, walks home, opens `localhost:8000` in 15 minutes, sees the new ride at the top of the list with Soft Floyd's analysis already written, asks a follow-up like "how does this compare to last week's similar ride?", and gets a streamed answer that references the right past ride and current wellness — for under $5/month total.
