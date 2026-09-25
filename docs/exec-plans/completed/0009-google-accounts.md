# 0009 — Google accounts and protected coach

## Context

The current local app has one implicit rider and unauthenticated REST/MCP surfaces. Add open Google registration and account-owned rider data, while keeping the imported book corpus shared. The web coach must use an authenticated MCP request for its tools. The server remains local; external MCP client setup and billing are deferred.

## Design

- Google OIDC authorization-code login identifies accounts by `sub`. A revocable, seven-day app JWT lives in an HttpOnly cookie; auth-only REST endpoints are public and every rider-data endpoint requires an account.
- Account IDs scope profiles, bikes, rides, Garmin state, conversations, memory, and usage attribution in core. Books and passages are shared; the configured monthly LLM budget remains global.
- MCP accepts only short-lived Bearer JWTs issued server-side for the authenticated web coach. Its tools resolve the same account as REST.
- A new database starts empty for rider data. A repeatable copy script preserves complete books and passages from the old database without modifying it.
- The web adds a bilingual sign-in page with product benefits and a simple identity/sign-out Profile screen.

## Steps

1. Add account/session tables, owner keys, Alembic migration, and book-copy command; make core queries and Garmin paths account-safe.
2. Add Google callback, signed sessions, request authentication, CSRF checks, and protected MCP transport; route coach tools through MCP.
3. Add sign-in/Profile UI, auth-aware API client, and bilingual copy.
4. Update architecture/security/product docs and verify two-account isolation, login/logout, MCP, coach, migration, and UI.

## Verification

Run `make check`, regenerate the schema reference, test two distinct Google accounts against every rider-data surface, and verify book retrieval in the fresh database. Review the rendered sign-in and Profile screens at desktop/mobile widths. Self-score against `docs/QUALITY_SCORE.md`.

## Result

- Added Google OIDC with PKCE, state, nonce and verified ID token; revocable web JWT cookies; account-scoped, short-lived MCP JWTs; origin checks for mutating browser requests.
- Added account ownership to profiles, bikes, rides, Garmin state, coach data and usage attribution. The ORM enforces account filtering and write ownership. Garmin token and FIT paths are separate per account, including background polling and CLI commands.
- Routed the website coach's context and data tools through authenticated MCP. Added bilingual sign-in and simple Profile screens.
- Generated and reviewed the account migration. The new `data/soft-floyd-accounts.db` contains zero rider rows and a copy of all 3 complete training books and 2,582 passages from the old database. The old database remains available.
- `make check`: 166 tests passed, Python lint/format and web typecheck passed. `pnpm run build` passed. `make docs-schema` regenerated the reference. Authentication tests cover two accounts, REST and MCP access, logout revocation, Google callback state, and ID token signature/claims.
- The in-app browser connection failed before navigation, so rendered desktop/mobile review remains unverified. Live Google login also requires local Google OAuth credentials and was tested with a mocked Google token exchange.

## Quality self-score

1. Correctness: yes for automated behavior; manual visual and live OAuth verification remain as above.
2. Single source of truth: yes; account and coach rules live in core, with REST/MCP as adapters.
3. Sensor honesty: yes; no sensor metric logic changed.
4. Tests: yes; auth, account isolation, migration/copy, and MCP bridge are exercised.
5. Docs kept honest: yes; architecture, security, product spec, schema and setup are updated.
6. Scope discipline: yes; external MCP clients, remote hosting, billing and a richer Profile are tracked as deferred work.
7. Local-only, account-safe: yes; loopback binding remains, and protected rider routes/tools resolve a verified account.
