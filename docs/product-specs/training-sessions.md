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
regenerated, edited, marked done/skipped, or deleted.

## Editing a session

A session that is still planned has an Edit button. It reopens the same
inputs as the flow above (date, minutes, indoor/outdoor, discipline, bike,
idea, how they feel), prefilled:

- Changing **only the date** just moves the session: the workout stays as
  it is and no AI call is made.
- Changing **anything else** rebuilds the workout from the edited request,
  one LLM call under the same monthly cap (see Cost). If the setting or
  discipline changed and no bike was picked, the bike is chosen again.
- Done and skipped sessions can't be edited. Plan a new one instead.
- If the session had already been sent to Garmin, the form warns that the
  old copy stays in Garmin Connect until the rider deletes it there, and the
  rebuilt or moved session has to be sent again.

The coach can make the same edits in chat ("make tomorrow's session 45
minutes", "move it to Saturday"); the updated card appears in the
conversation. Over REST it is `PATCH /api/training/sessions/{id}` with the
changed fields; over MCP, `update_training_session`.

## What it blends

Two inputs, not one:
- **What the rider asked for** — their route idea, available time,
  discipline, and how they feel that day.
- **What the plan says they should do** — computed from
  `activities.service.get_training_summary` (rides/hours this week vs.
  target), recent ride recency and intensity, `focus_areas`, and how
  close `target_event_date` is. This is deterministic, not an LLM guess
  — see `training/intent.py`.
- **How loaded the rider is** — once there is enough ride history
  (confidence `ok`), form and the 7-day fitness ramp from
  `metrics.service.get_training_load` steer the emphasis: very tired or a
  steep ramp means recovery, tired means keep it aerobic, fresh with
  fitness slipping means tempo or threshold. See `training-load.md`.

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

Planning a session, or rebuilding one after an edit, is one LLM call, subject to the same
`SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD` cap as the coach
(`docs/product-specs/coach-chat.md`); over budget returns a 402 with a
clear message instead of a silent failure.

## From the coach chat

The coach chat is a second way in: asking it for a workout collects the
same inputs, then shows the resulting session as a card in the
conversation. The session is the same record, so it also appears on the
Training page.
