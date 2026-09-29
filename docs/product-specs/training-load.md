# Training Load

Status: **implemented** (exec-plan 0012). Three numbers and a chart that
say how loaded the rider is — fitness, fatigue and form — computed from
their own synced rides, and honest about how each ride was measured.

## What the rider sees

On the dashboard, a "Fitness, fatigue and form" card:

- **Fitness** — average daily load over roughly the last 6 weeks, with
  how much it changed in the last 7 days.
- **Fatigue** — average daily load over the last 7 days.
- **Form** — fitness minus fatigue, with a plain label: fresh, neutral,
  tired or very tired.
- A two-line chart of fitness and fatigue for the last 8 weeks. Hovering
  or arrowing along it shows both values and that day's ride load; a
  "View as a table" section lists every day.
- Notes underneath when the numbers rest on shaky ground (see below).

With no synced rides the card says so instead of showing zeros. Under 42
days of ride history it says the baseline is still being built.

## How a ride is scored

Each ride gets one load number on a TSS-like scale (an hour at threshold
is about 100), from the best stream *that ride's own FIT data* verified:

1. **Power, NP** — needs verified power, a set FTP and stored records.
2. **Power, average** — same, without stored records (understates
   variable rides).
3. **HR, zones** — needs verified HR, an LTHR (or max HR to derive one)
   and stored records; time in each zone is weighted per hour.
4. **HR, average** — same, without records, or when HR covers under half
   the ride.
5. **Duration** — nothing verified: an estimate, 40 per hour, and always
   labelled as one.

The profile's sensor flags never decide this; a stream the ride did not
record is never read, whatever FTP or LTHR say (see
`docs/design-docs/sensor-capability-model.md`). A ride whose FIT data
failed to download or parse is scored from duration.

## When to trust it

Fitness, fatigue and form are exponentially-weighted averages of daily
load with 42-day and 7-day time constants, starting from zero at the
first ride in the last 180 days. So:

- **Confidence** is `low` under 21 days of history, `partial` from 21,
  `ok` from 42. Only `ok` numbers steer anything: the session planner and
  coach ignore load below it.
- Notes say when at least half of the last 42 days' load is estimated from
  duration, and when power or HR rides could not be scored because FTP or
  LTHR/max HR is missing.

## Where it is used

- **Session planning** (`training/intent.py`): very tired form, or fitness
  rising faster than 8 points a week, means a recovery session; tired
  means keep it aerobic; fresh with fitness slipping means tempo, or
  threshold for enthusiast and competitive riders. The reason shown to the
  rider quotes the numbers, and says "partly estimated" when most rides
  were scored from duration. Feel, a long ride yesterday and a taper
  (event within 3 days) still take priority. See `training-sessions.md`.
- **Coach chat**: the `get_training_load` tool. The coach is told to use
  it before advising on rest or intensity, to say how figures were
  measured, and not to lean on them unless confidence is `ok`.

## Surfaces

- REST: `GET /api/training/load?days=` (default 56, clamped 7–180).
- MCP: `get_training_load(days)`.
- Coach tool: `get_training_load(days)`, default 14 days of series.
- All return `TrainingLoadOut`: `as_of`, `ctl`, `atl`, `tsb`, `form`,
  `ramp_rate_7d`, `days_of_history`, `confidence`, `basis_counts`,
  `series` (per day: `date`, `load`, `ctl`, `atl`, `tsb`) and `notes`.

## Not yet

Load is recomputed on demand rather than stored, FTP and LTHR are only
what the rider declared, and the server's notes are English-only. See
`docs/exec-plans/tech-debt-tracker.md`.
