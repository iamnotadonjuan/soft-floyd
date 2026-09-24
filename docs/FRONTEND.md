# Frontend Conventions

Stack: Vite + React 18 + TypeScript + Tailwind. No state-management
library yet — the app is small enough for `useState`/`fetch` and a local
view toggle in `App.tsx`. Dashboard, Settings, and ride detail do not
have distinct URLs. Revisit routing when deep links or browser history
navigation become a real need.

## Structure

```
apps/web/src/
  api/client.ts     Typed fetch wrapper. One function per endpoint.
  api/types.ts      Types mirroring packages/core's Pydantic models —
                     keep field names identical to the API response.
  components/       Presentational pieces (forms, cards, pickers) shared
                     between pages — e.g. FocusPicker, AvailabilityPicker,
                     BikeEditor, connections/ (ConnectionsPanel,
                     ConnectionCard, GarminLoginForm).
  components/onboarding/  Onboarding-wizard-specific step shells (Habits/
                     Goals/Garage/AboutYou/Anchors/ConnectStep) — each a
                     thin "Next"-gated wrapper around the shared
                     components above plus its own fields.
  pages/            Onboarding, Dashboard, RideDetail, Settings, Coach.
  App.tsx           The "has a profile?" onboarding gate, plus the
                     dashboard/settings/ride/coach view toggle.
```

## Rules

- `api/types.ts` types must match the FastAPI response shape exactly —
  when `packages/core/.../profile/service.py`'s `ProfileOut` (or
  `bikes/service.py`'s `BikeOut`, or `connections/service.py`'s
  `ConnectionOut`) changes, update this file in the same change.
- Onboarding steps are separate components (`HabitsStep`, `GoalsStep`,
  `GarageStep`, `AboutYouStep`, `AnchorsStep`, `ConnectStep`), not one
  giant form — `AnchorsStep`'s fields are conditionally rendered based on
  the garage's declared sensors, and keeping them separate keeps that
  conditional logic legible.
  See [product-specs/new-user-onboarding.md](product-specs/new-user-onboarding.md).
- **Shared field components are written once and mounted twice.**
  `FocusPicker`, `AvailabilityPicker`, `BikeEditor`, and
  `connections/ConnectionsPanel` are plain presentational/self-fetching
  components with no onboarding-specific assumptions — `Onboarding.tsx`
  wraps them in step shells with a "Next" button, `Settings.tsx` stacks
  them as always-visible sections that each save independently. Adding a
  field to one of these components should never require onboarding-only
  or settings-only branching inside the component itself; put that in
  the page that mounts it instead.
- `BikeEditor` and `ConnectionsPanel` mutate through `api/client.ts`
  directly and manage their own local state (there's no single-profile
  "patch to submit" for a garage of bikes or a list of connections) —
  every other onboarding step instead reports a values object up to
  `Onboarding.tsx`/`Settings.tsx`, which owns the actual `PUT
  /api/profile` call. Don't blur this: a component either owns its own
  persistence (bikes, connections) or is a pure controlled input
  (everything else) — never both.
- No component reaches for `fetch` directly; go through `api/client.ts`
  so there is one place that knows the API shape. That includes the
  coach's Server-Sent Events stream: `api.streamCoachMessage` POSTs and
  parses SSE frames from the response body (EventSource can't POST).
- Coach replies are model output: `components/CoachText.tsx` renders
  their small Markdown subset as React elements — never
  `dangerouslySetInnerHTML`.
- Ride history uses the last page item's `(start_time, id)` cursor, not an
  offset; this keeps browsing stable when a new Garmin ride arrives.
- Follow `.agents/skills/vercel-react-best-practices` rules where they
  apply (already vendored in this repo) — derived state without effects,
  functional `setState`, avoiding inline component definitions, etc.
