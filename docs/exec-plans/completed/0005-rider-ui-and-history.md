# 0005 — Rider UI and Ride History

## Context

The current UI has the right onboarding fields and connection endpoints, but its
visual hierarchy is thin, the dashboard claims Garmin sync is unfinished, and it
does not show synced rides. The rider needs a calm, usable path from setup to
their latest ride and then through all already synced rides.

Done means onboarding, Settings, connections, dashboard, and ride detail share a
responsive visual system; the newest ride is first; every synced ride can be
reached through history; and all displayed values come from recorded data.

## Design

Follow `docs/DESIGN.md`, the onboarding and connected-app specs, and the sensor
capability model. Use a warm, restrained cycling-journal style without a new UI
library. Preserve the seven-step order and the existing field/API ownership.
Expose stable cursor pagination on the existing activity list using
`(start_time DESC, id DESC)` and optional `before_start_time` plus `before_id`
arguments on both REST and MCP. Keep the response as a list. The web fetches
pages of 20 on demand and opens `/api/activities/{id}` for detail. It shows
recorded summary/lap values only, never uncomputed training metrics.

## Steps

1. Add pagination in core and identical REST/MCP arguments; test ordering and
   page boundaries.
2. Add typed activity API calls and the shared visual styles/components.
3. Refine onboarding, shared bike and connection controls, and Settings with
   responsive layout, navigation, status, and error states.
4. Build dashboard, history, and ride detail from existing API data.
5. Update product and frontend docs, verify, and score against QUALITY_SCORE.

## Verification

- Run backend activity and MCP tests, web typecheck/build, and `make check`.
- Check onboarding, Settings, connection states, empty and populated history,
  pagination, and ride detail in the browser at mobile and desktop widths.
- Confirm keyboard operation, no horizontal overflow, and sensor-honest output.

Completed: `make check` passed (130 Python tests, Ruff, web typecheck), and
the web production build passed. Browser QA used an isolated local database
and headless Chrome because the in-app browser connection failed before page
load. Screenshots at 390px and 1440px showed onboarding, dashboard, Settings,
the Garmin login panel, and ride detail without horizontal overflow. A browser
interaction loaded all 24 fictional rides across two pages (20 + 4), then
returned from a detail view with all 24 tiles retained and focus restored to
the selected tile. Real Garmin credential/MFA submission was not exercised;
the existing fake-client backend tests cover that handshake.

## Quality self-score

Correctness: yes for implemented behavior and completed checks. Single source
of truth: yes; pagination lives in core and both adapters share it. Sensor
honesty: yes; ride detail gates sensor values on each FIT stream. Tests: yes
for cursor ordering and REST/MCP agreement. Docs: yes. Scope discipline: yes;
manual web sync and historical backfill remain separate. Local-only: yes;
the QA server used an isolated database bound to loopback.
