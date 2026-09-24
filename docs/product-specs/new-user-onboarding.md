# New User Onboarding

Status: **implemented** (exec-plan 0004). Backing models: `RiderProfile`
and `Bike` (`packages/core/src/soft_floyd_core/models.py`). UI:
`apps/web/src/pages/Onboarding.tsx` and its step components, reusing
shared field components (`FocusPicker`, `AvailabilityPicker`,
`BikeEditor`, `ConnectionsPanel`) also mounted by
`apps/web/src/pages/Settings.tsx`.

## Flow

Shown whenever `GET /api/profile` (equivalently, MCP `get_rider_profile`)
returns a profile with no `goal_text` set — i.e., a rider who hasn't
completed onboarding yet. Seven steps, one screen each, in this order
(per `docs/DESIGN.md`: volume and goals before sensors; never ask for a
number the rider can't produce):

1. **Habits** — "How do you ride now?" Rides per week, hours per week
   (`weekly_rides`, `weekly_hours`), plus which days the rider can
   usually ride and a weekday/weekend max duration
   (`available_days`, `weekday_max_minutes`, `weekend_max_minutes`).
2. **Goals** — "What do you want to get better at?" A fixed set of
   focus chips (`focus_areas`: `endurance`, `climbing`, `flat_speed`,
   `sprint`, `technical_skill`, `weight`, `first_event`, `consistency`,
   `enjoy` — multi-select), a free-text goal (`goal_text`, required —
   this is what gates onboarding completion), and an optional target
   event name/date (`target_event_name`, `target_event_date`).
3. **Garage** — "What do you ride?" Add one or more bikes
   (`BikeEditor`): a kind (road/gravel/mtb/tt/indoor), an optional
   nickname, and per-bike power/cadence/speed sensor checkboxes. The
   first bike added is always primary. An indoor trainer is just a bike
   with `kind="indoor"` — there is no separate trainer concept. Not
   skippable (at least one bike is required); bikes save immediately as
   they're added/edited, there's no "Next" patch to submit for this step.
4. **About you** — whether the rider wears a heart rate monitor, birth year,
   weight, max heart rate, years riding,
   longest recent ride, a self-rated level
   (`beginner`/`recreational`/`enthusiast`/`competitive`), whether
   they've followed a structured plan before, and free-text health
   notes. Every field is individually skippable. The HR monitor choice
   sets `has_hr_monitor` before the conditional Anchors step.
5. **Anchors** — conditionally rendered based on the garage and the
   rider's HR flag (both read from `ProfileOut`, refreshed right after
   the Garage step so its derived fields are current):
   - FTP (`ftp_watts`) is asked **only if** any bike has a power meter
     (`has_power_meter`, derived — see sensor-capability-model.md).
   - LTHR (`lthr`) is asked **only if** `has_hr_monitor` is set,
     pre-filled with the default of 165 and clearly marked skippable.
   - If neither applies, this step is skipped entirely.
6. **Connect** — the Connected Apps panel (`ConnectionsPanel`), today
   just Garmin, with an in-browser login form. Skippable — a rider can
   connect later from Settings. See
   [connected-apps.md](connected-apps.md).
7. **Summary** — a one-line explanation of what the coach will use,
   sourced from `capability_tier`/`available_metrics` — e.g. *"No power
   meter, so I'll read your rides through heart rate drift and time in
   zone."* When the garage has more than one bike, a per-bike line is
   added underneath (e.g. *"Tarmac — read through power (primary)"*,
   *"MTB — read through heart rate"*) so a mixed garage's tradeoff is
   legible immediately, not just the overall union. This is the rider's
   first encounter with
   [sensor-capability-model.md](../design-docs/sensor-capability-model.md).

## Persistence

Each profile-owning step's "Next" issues a `PUT /api/profile` with only
that step's fields (partial update — `ProfileIn` in
`packages/core/src/soft_floyd_core/profile/service.py` treats unset
fields as "leave alone", and rejects
`has_power_meter`/`has_cadence_sensor`/`has_speed_sensor`/
`primary_discipline` outright since those are derived from the garage).
The Garage step instead mutates bikes directly through
`POST`/`PATCH`/`DELETE /api/bikes` as the rider edits them. The rider can
navigate back without losing earlier answers.

## Editability

Everything asked during onboarding — habits, goals, garage/sensors,
about-you fields, anchors, and connected apps — is editable later from
`apps/web/src/pages/Settings.tsx`, reached via a "Settings" link on the
dashboard. Settings mounts the same shared field components
(`FocusPicker`, `AvailabilityPicker`, `BikeEditor`, `ConnectionsPanel`)
as always-visible sections instead of a step-by-step wizard, each saving
independently. A rider who buys a power meter mid-season adds it to a
bike from Settings' Garage section and sees `capability_tier` flip on
the very next read — no migration step, per
`sensor-capability-model.md` rule 5.

## Acceptance

- Completing the required steps (Habits, Goals, Garage) produces a
  `RiderProfile` row plus at least one `Bike` row, and `GET /api/profile`
  returns a `capability_tier` consistent with the garage and HR flag
  (see `tests/test_capability_tier.py` for the full matrix).
- Removing the only sensor that unlocked the Anchors step's FTP field
  (across the whole garage) removes that field from view without
  breaking navigation.
- The MCP tools `get_rider_profile`/`list_bikes`/`get_connections`
  return output identical to the equivalent REST calls
  (`tests/test_mcp_tools.py`).
- Adding a power-meter bike from Settings flips `capability_tier` to
  `power` on the very next `GET /api/profile`, without a page reload
  being required for correctness (`tests/test_bikes_api.py`).
