# 0008 — UI Language (English / Spanish)

## Context

All the web UI's copy was hardcoded in English. The rider wanted the UI to be available in English
(the default) or Spanish, chosen by the user. There is no settings field on the profile yet, so for
now the choice is stored in the browser.

Decisions made with the rider:
- Only the UI's own copy is translated. The coach's replies and server messages are unchanged, and
  core, REST and MCP are untouched.
- An EN / ES toggle appears in every page header, including onboarding.

Done means:
- every string the UI itself renders (visible text, aria labels, placeholders) exists in both
  languages,
- dates and decimal separators follow the chosen language,
- the choice survives a reload,
- `tsc` fails if the two languages drift apart.

## Design

- There is no new dependency: a typed dictionary plus a React context. `src/i18n/en.ts` is the
  source of truth and `Messages = typeof en`. `src/i18n/es.ts` is typed as `Messages`.
- `src/i18n/I18nProvider.tsx` provides `{ locale, intlLocale, m, setLocale }` and syncs
  `<html lang>`. It stores the choice in `localStorage["soft-floyd.locale"]`, with try/catch so a
  blocked storage still works. It is the single place to change when the profile gets settings.
- `components/LanguageToggle.tsx` is added to each page header (Dashboard, RideDetail, Coach,
  Settings, Onboarding, and the server-error screen).
- Enum label maps that used to live in components (focus areas, levels, weekdays, bike kinds, tiers,
  connection status) moved into the dictionaries. The components now keep only the ordered keys.
- `activityFormat.ts` helpers take `m` and `intlLocale`. The shared `bikeKindLabel` lives there too.
- The conventions are documented in `docs/FRONTEND.md` under "Localization".

## Steps

1. Add the dictionaries, the provider and the toggle, and wrap `<App/>` in `main.tsx`.
2. Convert pages and components to `useI18n()`.
3. Update the docs and the tech-debt tracker.

## Verification

- `pnpm typecheck` and `pnpm build` in `apps/web` both pass. The type check proves `es.ts` covers
  every key.
- A grep for leftover JSX text and literal `placeholder`/`aria-label` values finds none outside
  `src/i18n/`. The one English string left in `api/client.ts` is an API-level error, which is out
  of scope.
- Manual check: switch EN → ES on the dashboard, a ride, the coach and settings, then reload and
  confirm Spanish persists.
