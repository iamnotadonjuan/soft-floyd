# Frontend Conventions

Stack: Vite + React 18 + TypeScript + Tailwind. No state-management
library yet — the app is small enough for `useState`/`fetch` plus one
context for the rider profile. Reach for a library only when the
scaffold's approach visibly strains, not preemptively.

## Structure

```
apps/web/src/
  api/client.ts     Typed fetch wrapper. One function per endpoint.
  api/types.ts      Types mirroring packages/core's Pydantic models —
                     keep field names identical to the API response.
  components/       Presentational pieces (forms, cards, charts).
  pages/            Route-level components (Onboarding, Dashboard).
  App.tsx           Routing + the "has a profile?" gate.
```

## Rules

- `api/types.ts` types must match the FastAPI response shape exactly —
  when `packages/core/.../profile/service.py`'s `ProfileOut` changes,
  update this file in the same change.
- Onboarding steps are separate components (`VolumeStep`, `GoalStep`,
  `SensorsStep`, `AnchorsStep`), not one giant form — `AnchorsStep`'s
  fields are conditionally rendered based on `SensorsStep`'s answers, and
  keeping them separate keeps that conditional logic legible.
  See [product-specs/new-user-onboarding.md](product-specs/new-user-onboarding.md).
- No component reaches for `fetch` directly; go through `api/client.ts`
  so there is one place that knows the API shape.
- Follow `.agents/skills/vercel-react-best-practices` rules where they
  apply (already vendored in this repo) — derived state without effects,
  functional `setState`, avoiding inline component definitions, etc.
