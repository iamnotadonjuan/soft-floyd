# New User Onboarding

Status: **implemented** (scaffold). Backing model: `RiderProfile`
(`packages/core/src/soft_floyd_core/models.py`). UI:
`apps/web/src/pages/Onboarding.tsx` and its step components.

## Flow

Shown whenever `GET /api/profile` (equivalently, MCP `get_rider_profile`)
returns a profile with no `goal_text` set — i.e., a rider who hasn't
completed onboarding yet. Four steps, one screen each:

1. **Volume** — "How much do you ride now?" Two numeric inputs:
   rides per week, hours per week. (`weekly_rides`, `weekly_hours`.)
2. **Goal** — "What do you want to improve?" A free-text goal
   (`goal_text`) plus a primary discipline choice, road or mtb
   (`primary_discipline`). Optional target event date
   (`target_event_date`) if they have one in mind.
3. **Sensors** — "What do you ride with?" Plain-language checkboxes, no
   jargon in the label itself (a short explanatory line is fine):
   power meter, heart rate monitor, cadence sensor, speed sensor
   (`has_power_meter`, `has_hr_monitor`, `has_cadence_sensor`,
   `has_speed_sensor`). Include an "I'm not sure" affordance that, if
   chosen, defaults to HR-monitor-only (the common Garmin Edge + chest/wrist
   strap setup) rather than leaving all four unchecked.
4. **Anchors** — conditionally rendered based on step 3's answers:
   - FTP (`ftp_watts`) is asked **only if** `has_power_meter` is checked.
   - LTHR (`lthr`) is asked **only if** `has_hr_monitor` is checked,
     pre-filled with the default of 165 and clearly marked skippable.
   - If neither box is checked, this step is skipped entirely — never
     ask for a number the rider has no way to produce.

After submit, show a one-line summary of what the coach will use, sourced
from the response's `capability_tier`/`available_metrics` — e.g. *"No
power meter, so I'll read your rides through heart rate drift and time in
zone."* This is the rider's first encounter with
[sensor-capability-model.md](../design-docs/sensor-capability-model.md)
and should make the tradeoff legible immediately, including that adding a
power meter later changes it.

## Persistence

Each step's "Next" issues a `PUT /api/profile` with only that step's
fields (partial update — `ProfileIn` in
`packages/core/src/soft_floyd_core/profile/service.py` treats unset
fields as "leave alone"). The rider can navigate back without losing
earlier answers.

## Editability

Sensors (and everything else) are editable later from a settings screen,
not just at first run — a rider who buys a power meter mid-season must be
able to update `has_power_meter`/`ftp_watts` and see `capability_tier`
flip on the very next read. (Scaffold ships onboarding; the settings
screen for post-onboarding edits is not yet built — `PUT /api/profile`
already supports it via the same partial-update mechanism.)

## Acceptance

- Completing all four steps produces a `RiderProfile` row with all
  declared fields, and `GET /api/profile` returns a `capability_tier`
  consistent with the sensor answers (see
  `tests/test_capability_tier.py` for the full matrix).
- Unchecking the only sensor that unlocked an anchor step removes that
  step from view without breaking navigation.
- The MCP tool `get_rider_profile` returns the identical profile written
  through the web UI (`tests/test_mcp_tools.py`).
