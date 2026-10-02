# 0015 — Help and first-use guide

## Context

The setup wizard collects rider context, but new riders have no concise path through the signed-in app, and Settings and training load terms lack explanations. Done means riders can find a short starting guide, a persistent Help/FAQ page, and contextual explanations without changing coaching or sensor logic.

## Design

Follow `docs/product-specs/help-and-first-use.md`, `docs/product-specs/new-user-onboarding.md`, `docs/design-docs/core-beliefs.md`, and `docs/design-docs/sensor-capability-model.md`. Keep all help copy in the existing English and Spanish dictionaries. The first-use guide is a dashboard card with account-keyed browser storage; no API or schema changes. Reuse the dashboard's existing data to show which prerequisites are ready. Use native disclosure controls for contextual help and FAQ.

## Steps

1. Add the Help view, signed-in and onboarding entry points, and translated guide and FAQ copy.
2. Show the first-use dashboard guide after onboarding, with dismiss and reopen behavior scoped to the account.
3. Add contextual help beside Settings groups and training load metrics.
4. Verify build and interaction states, update frontend docs, and self-score against `docs/QUALITY_SCORE.md`.

## Verification

- Run web typecheck and build.
- Check new and existing accounts, account switching, reload, dismissal, and reopening.
- Check empty/disconnected and synced states, English/Spanish, touch width, and keyboard disclosures.

## Result

- `pnpm typecheck` and `pnpm build` passed. `git diff --check` passed.
- Code review covered account-keyed guide state, onboarding answer preservation while Help is open, disconnected and no-ride actions, and translated copy. Native `details`/`summary` controls provide click, touch, and keyboard behavior.
- Signed-in visual review remains pending because the in-app browser connection failed before a page could open. Tracked in the tech-debt tracker.
- Quality self-score: correct to the spec by code review and build; no new core rules or cross-surface contracts; sensor wording follows existing specs; docs and account-scoped browser state are updated. Live visual interaction remains the only unverified item.
