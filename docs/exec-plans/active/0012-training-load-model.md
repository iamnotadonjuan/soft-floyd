# 0012 — Training-load model: fitness, fatigue and form

## Context

The coach and the session planner both lean on the LLM's judgment about
how hard the rider has been training. `training/intent.py` reads only
ride dates, durations and weekly aggregates, and the coach can only quote
`get_training_summary` (ride counts, hours, average HR/power). Nothing
computes how *loaded* the rider is, so "am I fresh enough for intervals
tomorrow?" gets a plausible-sounding answer rather than a number the
rider can check.

This plan adds a deterministic training-load model — chronic load
(fitness), acute load (fatigue) and their difference (form), the
standard CTL/ATL/TSB trio — computed from the rider's own synced rides
and honest about how each ride's load was measured. It is the foundation
for the rest of the "real training agent" work (see *What follows*):
multi-week plans, the plan-vs-actual loop and proactive check-ins all
need one trustworthy load number to reason about.

Done means:

- `get_training_load` returns CTL, ATL, TSB, a 7-day ramp rate and a
  daily series, plus how much of that history is sensor-verified versus
  estimated, through core, REST, MCP and a coach tool.
- `training/intent.py` uses form and ramp rate to pick the session
  emphasis when there is enough history, and says why in `reasons`.
- The Dashboard shows a small fitness / fatigue / form card.
- Nothing is invented: a ride with no verified power or HR is scored from
  duration and labelled as an estimate, never as measured load.

## Design

See `docs/design-docs/training-signal-model.md` for the formulas this
implements (NP, IF, TSS, HR zones, TRIMP) and
`docs/design-docs/sensor-capability-model.md` for the rule it must not
break: only compute the family that *this ride's own recorded streams*
support. `Activity.has_power_data` / `has_hr_data` (with
`fit_status == "ok"`) decide the basis per ride, never the profile or
bike flags. Reuse whichever helper `get_training_summary` and
`rag.service.ride_context` already use for that per-ride gate rather than
re-deriving it.

**Per-ride load** (`packages/core/src/soft_floyd_core/metrics/load.py`).
One number per ride on a TSS-like scale (an hour at threshold ≈ 100),
tagged with the basis it came from, best first:

| basis | needs | how |
|---|---|---|
| `power_np` | verified power, `ftp_watts`, stored records | NP from the 30 s rolling mean, IF = NP/FTP, TSS = duration·NP·IF / (FTP·3600) · 100 |
| `power_avg` | verified power, `ftp_watts`, no stored records | same formula with average power standing in for NP (understates variable rides) |
| `hr_zones` | verified HR, `lthr` (else derived from `max_hr`), stored records | time in each HR zone (zones from LTHR, per the signal doc) × a per-hour stress weight |
| `hr_avg` | verified HR, `lthr`/`max_hr`, no stored records | hours · (avg_hr / LTHR)² · 100 |
| `duration` | nothing verified | hours × a flat endurance-pace weight, flagged as an estimate |

Every load carries its `basis`, so the series can say how much of the
rider's history is measured (`power_*`, `hr_*`) versus estimated
(`duration`). Rides with `fit_status` other than `ok` fall to
`duration`, and are never read as "no HR/power on this ride".

**Daily series and CTL/ATL/TSB** (`metrics/service.py`).
Sum ride loads per calendar day (rest days are zero), then two
exponentially-weighted averages: CTL with a 42-day time constant and ATL
with a 7-day one, TSB = CTL − ATL, ramp rate = CTL change over 7 days.
`days_of_history` and `confidence` (`low` under 21 days of data, `ok`
from 42) are returned alongside, and consumers must ignore load when it's
`low`. The series is computed on demand from the `activity` (and, for
NP/zones, `record`) tables — no schema change in this plan.

**Output** (`TrainingLoadOut`, pydantic, shared by all surfaces):
`as_of`, `ctl`, `atl`, `tsb`, `form` (plain-language label: fresh /
neutral / tired / very tired), `ramp_rate_7d`, `days_of_history`,
`confidence`, `basis_counts` (`{"power_np": 12, "hr_zones": 5, …}`),
`series` (per-day `date, load, ctl, atl, tsb`) and `notes` (e.g. "60% of
your recent load is estimated from ride duration — set your FTP/LTHR for
better numbers").

**Consumers.**

- `training/intent.py`, same deterministic style as today: after the
  existing `feel` and long-ride-yesterday rules, and only when confidence
  is `ok`, add rules for form and ramp — very tired (TSB well below zero,
  or ramp rate above a safe ceiling) → `recovery`; fresh with load
  trending down → `threshold`/`vo2`; otherwise fall through to the current
  chain. Each adds a `reason` quoting the number. Thresholds live as named
  constants next to `_LONG_RIDE_SECONDS`, with a comment on where each
  came from.
- `training/generator.py`: `_prompt()` includes a compact load snapshot
  (CTL, ATL, TSB, form label) so the model's rationale can cite it, and
  the system prompt tells it not to restate numbers it wasn't given.
- Coach: new `get_training_load` tool in `coach/tools.py` (spec plus a
  branch in `run_tool`); `coach/prompts.py` tells the coach to call it
  before advising on rest, intensity or "should I ride hard". Also
  exposed as an MCP tool (`mcp_server.py`) and `GET /api/training/load`
  in `http_api.py`, per AGENTS.md's thin-adapter rule.
- Web: a `LoadCard` on the Dashboard — three numbers with a form label
  and an eight-week chart of CTL/ATL/TSB, with the `notes` shown under
  it. Strings in `i18n/en.ts` and `es.ts`. Build the chart with the
  `dataviz` skill so light/dark colors and accessibility match.

**Deliberately out of scope here:** persisting per-ride load (see
*Deferred*), auto-detecting FTP/LTHR, power-duration curves, and
per-bike or per-discipline load splits.

## Steps

1. Review `v0-legacy`'s `src/coach/metrics/compute.py` and `zones.py`
   (git tag `v0-legacy`) per the signal doc's salvage note; port what
   fits, with their hand-computed test values.
   *Done.* Ported to `metrics/zones.py`: `make_zones`, `zone_for_hr` and
   the time-in-zone loop (as `time_in_zones`), plus a `lthr_from_max_hr`
   helper (v0's 0.87 ratio, inverted), with v0's zone tests in
   `tests/test_metrics.py`. Left behind because load doesn't use them:
   HR drift, decoupling, GAP and VAM. v0's Banister-Morton TRIMP
   (`tss_proxy`) is *not* ported; `hr_avg` uses hours·(avg_hr/LTHR)²·100
   instead, so HR-based load lands on the same scale as power TSS.
   `training/sanitize.py` keeps its own %LTHR table (it needs a floor and
   ceiling per zone for device targets); unifying the two is not worth it
   now.
2. `metrics/load.py`: per-ride load and basis selection, pure functions
   over plain inputs (duration, avg power/HR, optional record arrays,
   FTP, LTHR) so they test without a database.
3. `metrics/service.py`: daily series, CTL/ATL/TSB, confidence, basis
   counts, notes, and the `TrainingLoadOut` model. Reads `activity` and
   `record` through the same per-ride gate as `get_training_summary`.
4. Coach tool, MCP tool and REST route; register the tool in `TOOLS`,
   `run_tool` and `mcp_server.py`; update the coach system prompt.
5. `intent.py` load rules and the generator prompt snapshot.
6. Dashboard `LoadCard`, `api/client.ts` + `api/types.ts`, i18n.
7. Docs: mark the implemented formulas in
   `docs/design-docs/training-signal-model.md`, add a `training-load`
   product spec, and record deferred items in the tech-debt tracker.

## Verification

- Unit tests (`tests/test_metrics.py`) with hand-computed expectations: a
  constant-power ride (NP = power), a variable ride (NP > average), each
  HR zone boundary, an EWMA over a short known series, and rest days
  decaying ATL faster than CTL.
- Sensor-honesty tests: a ride with `has_power_data=False` never gets a
  `power_*` basis even if the profile has an FTP; `fit_status="parse_failed"`
  falls to `duration`; no FTP means no `power_*` basis; `basis_counts` and
  `notes` reflect it.
- `intent.py` tests: very tired → recovery with the number in `reasons`;
  `confidence="low"` → the load rules are skipped entirely.
- Coach test with the scripted `FakeLLM` (as in `tests/test_coach.py`):
  `get_training_load` is callable, and its JSON matches the REST route
  (extend the MCP-vs-REST agreement test).
- `make check` (ruff, `pnpm run typecheck` so missing `es` keys fail, and
  pytest).
- Against the real dev database (`data/soft-floyd-accounts.db`): call the
  REST route and time it. If computing NP over recent rides takes more
  than about a second, that triggers the persistence item under
  *Deferred*. Sanity-check that CTL is plausible next to the rider's
  actual weekly hours.
- Manual: open the Dashboard and read the card; in Coach ask "am I fresh
  enough for intervals tomorrow?" and confirm the answer cites the load
  numbers and says which are estimated.

## Deferred (record in the tech-debt tracker)

- Persist per-ride load (an `Activity.load` / `load_basis` pair or a
  side table), computed at sync time and recomputed when FTP/LTHR change.
  Skipped now to avoid a schema change before we know the on-demand cost.
- Auto-detect FTP/LTHR from the power curve; until then the rider's
  declared anchors are the only ones used.
- HR-based TSS weights per zone are a fixed table; personalizing them
  needs longer history than most riders have.

## What follows

Each gets its own exec-plan; listed here so 0012's design leaves room for
them.

- **0013 — Multi-week plan.** Periodized plan (base/build/peak/taper)
  toward `target_event_date`, stored in the database and tied to
  `TrainingSession` rows, with weekly load targets expressed in this
  plan's units. The coach and Training page read and adjust it.
- **0014 — Plan-vs-actual loop.** After a ride syncs, match it to the
  planned session, compare adherence and load, re-plan the coming weeks
  when the rider skips or overshoots, and save what worked as coach
  memory.
- **0015 — Proactive coach.** A scheduled job that opens coach
  conversations: weekly review, rest-day nudge when form is very tired,
  event countdown. Needs an inbox/badge in the web app to surface them.
