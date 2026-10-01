# 0014 — Signed-in UI redesign

## Context

The login has a clear identity, but the signed-in experience gives nearly every section the same pale card and visual weight. The first visit does not make the rider's next action obvious. Done means the signed-in app feels like one distinctive cycling product across desktop and mobile, while preserving every existing workflow and honest sensor label.

## Design

Use a premium cycling editorial language: warm paper, deep forest, lime and terracotta accents, expressive display type, and decorative route graphics. Establish shared tokens and a persistent navigation shell. Prioritize the rider's goal, next session, latest ride, and the step needed to start syncing on the dashboard. Carry the system through onboarding, training, coach, ride detail, settings, and profile. Keep login and backend contracts unchanged. Follow `docs/design-docs/core-beliefs.md`, `sensor-capability-model.md`, and the existing product specs; drawn routes are decoration, never a representation of an activity.

## Steps

1. Add theme tokens, reusable primitives, responsive navigation, and translated navigation labels.
2. Recompose the dashboard and its connected, disconnected, and no-ride states around clear actions.
3. Restyle the remaining signed-in screens and shared components, including the load chart and workout card, without changing data rules or persistence.
4. Verify interaction and layout across widths, then update docs and self-score against `docs/QUALITY_SCORE.md`.

## Verification

- Run the web typecheck and build.
- Review onboarding, dashboard, coach, training, ride detail, settings, and profile at mobile, tablet, and desktop widths in English and Spanish.
- Check keyboard focus, reduced motion, contrast, long text, and empty, loading, error, and disconnected states.
- Confirm sensor values still appear only when the activity verified their streams.

## Result

- `make check`: 274 tests passed; Python lint/format and web typecheck passed. `pnpm build` passed.
- Reviewed headless-Chrome screenshots at 1440px and a true 390px mobile viewport with mock ride data: Dashboard, Training, Coach, Settings, Profile, Ride detail, and onboarding. Checked Spanish onboarding and the disconnected/no-rides dashboard. Fixed the first-use hero to lead with Connect Garmin when disconnected.
- Checked text contrast for muted and hero colors and kept the load chart's distinct blue/orange series. No data or sensor rules changed.
- Quality self-score: correctness, single source of truth, sensor honesty, tests, docs, scope, and account safety are satisfied for this UI-only change. Live-account visual review is tracked in the tech-debt tracker.
