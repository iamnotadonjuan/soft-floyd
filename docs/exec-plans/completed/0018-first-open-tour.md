# 0018 — First-open app tour

## Context

The existing first-use checklist gives riders tasks after setup, but it does not show where the main parts of the app are. A new rider should get a short, optional spotlight tour immediately after completing onboarding. Existing riders should only see it if they launch it from Help.

## Design

Follow `docs/product-specs/help-and-first-use.md`, `docs/design-docs/core-beliefs.md`, and `docs/FRONTEND.md`. Keep this entirely in the React app: a six-step overlay points to Overview, Garmin status, Training, Coach, Settings, and Help. It may navigate between signed-in views but never changes rider data. English and Spanish copy stays in the i18n dictionaries. The setup-completion event starts the tour, so even a new account whose numeric ID was reused after local deletion gets it. The existing Overview checklist remains separate.

## Steps

1. Document the tour behavior and add translated copy.
2. Build the accessible spotlight and stable targets for desktop and mobile navigation and relevant screens.
3. Start after onboarding, add Help replay, and keep tour state separate from the existing guide state.
4. Verify layouts and interaction states, then update docs and self-score.

## Verification

- Run the web typecheck and build.
- Check automatic launch only after new onboarding; Skip, Finish, replay, reload, and account switching.
- Check no Garmin connection, connected Garmin, English and Spanish, desktop and mobile, keyboard focus/Escape, and unavailable targets.
- Run `git diff --check` and self-score against `docs/QUALITY_SCORE.md`.

## Result

- Web typecheck, production build, and `git diff --check` passed.
- Code review covered onboarding-only automatic launch, Help replay, keyboard focus trapping, missing targets, both nav layouts, and disconnected Coach wording.
- Signed-in visual review remains pending because the in-app browser connection failed before a page could open; tracked in the tech-debt tracker.
- Quality self-score: the implementation follows the spec, keeps UI-only state outside core, makes no sensor claims beyond existing capability rules, adds no API or schema surface, updates docs, and preserves account separation. Live visual interaction is the unverified item.
