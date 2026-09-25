# Training Sessions

Status: **implemented** (exec-plan 0010). An optional "what should I ride
next" flow, separate from the coach chat, that turns a rider's own idea
for their next ride into one structured, sensor-honest workout — and
gets it onto their device.

## The flow

From the dashboard, "Plan a session" opens Training:

1. **Devices** (asked once, then remembered on the profile): Garmin Edge,
   Wahoo, Zwift, other. This decides which export options later appear.
2. **When and how long**: a date (defaults to tomorrow) and available
   minutes (defaults from `weekday_max_minutes`/`weekend_max_minutes`). A
   notice appears if the date falls outside the rider's usual
   `available_days` — it doesn't block planning, riders go off-schedule.
3. **Where**: indoor or outdoor, and discipline — road, MTB, or gravel.
   Pre-filled from the rider's garage (the matching bike, or the
   `indoor` bike for an indoor session) with a picker if more than one
   bike matches.
4. **The idea**: free text ("hill repeats at Patios, Bogotá", "just
   spin"), and how they feel (fresh/normal/tired).

The result is one `Workout`: a name, a rationale in the coach's voice
explaining what it kept from the rider's idea and what it adjusted (and
why — recent load, the goal, how they said they feel), and the step list
(warmup/interval/recovery/cooldown, optionally repeated) with an
intensity target and an end condition each.

Sessions are listed (upcoming and past) below the flow; each can be
regenerated, marked done/skipped, or deleted.

## What it blends

Two inputs, not one:
- **What the rider asked for** — their route idea, available time,
  discipline, and how they feel that day.
- **What the plan says they should do** — computed from
  `activities.service.get_training_summary` (rides/hours this week vs.
  target), recent ride recency and intensity, `focus_areas`, and how
  close `target_event_date` is. This is deterministic, not an LLM guess
  — see `training/intent.py`.

The LLM's job is narrow: turn that intent plus the rider's own words into
one concrete, well-formed workout and explain the trade-off in plain
language — never to invent the intent itself or a sensor value.

## Sensor honesty

Same rule as everywhere else in this app (see
`docs/design-docs/sensor-capability-model.md`): a workout step only gets
a power target if the chosen bike has a power meter *and* the rider has
set `ftp_watts`; only gets an HR-zone target if `has_hr_monitor` *and*
`lthr`/`max_hr` is set; only gets a cadence target with a cadence sensor.
Without the matching sensor, the step still exists but its target becomes
a plain-language RPE cue ("hard, steady effort") instead. This is
enforced in `training/sanitize.py`, independent of what the LLM returns.

## Getting it onto a device

- **Garmin**: "Send to Garmin" pushes the workout to Garmin Connect and
  schedules it on the planned date, so it syncs to the Edge (or a paired
  smart trainer) on its own. Only shown when Garmin is a connected app.
  Sending again updates the same Garmin workout rather than duplicating
  it.
- **Download**: a `.fit` workout file (any head unit, including Wahoo
  ELEMNT) always available; `.zwo` (Zwift, Wahoo SYSTM) and `.erg`
  (absolute watts, common ERG-mode trainer software) only when the rider
  has a power meter and FTP set — an ERG-style file without real watts
  would be a fabricated signal.

Wahoo's own cloud push (needs partner API approval) is deferred — see
`docs/exec-plans/tech-debt-tracker.md`.

## Cost

Planning a session is one LLM call, subject to the same
`SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD` cap as the coach
(`docs/product-specs/coach-chat.md`); over budget returns a 402 with a
clear message instead of a silent failure.
