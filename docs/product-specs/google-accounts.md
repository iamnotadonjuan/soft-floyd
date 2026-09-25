# Google accounts

Status: implemented in exec-plan 0009. Soft Floyd still runs on loopback;
Google sign-in is its only website registration and sign-in method.

## Visitor and rider flow

- An unauthenticated visitor sees a responsive English/Spanish sign-in page
  describing the ride journal, sensor-honest coach, and personal training
  context. "Continue with Google" creates an account on first use and signs
  into an existing account on later visits.
- After Google sign-in, the app resumes its existing onboarding gate and
  dashboard. Profile shows the Google name, picture, email and local account
  ID, and offers sign-out. Training details remain in Settings.
- The browser session is a seven-day, revocable JWT in an HttpOnly cookie.
  Reloads keep the rider signed in until expiry or sign-out. An expired or
  revoked session returns the UI to sign-in.

## Data and coach

- A rider sees only their own profile, bikes, Garmin connection and sync
  state, FIT data, ride journal, coach conversations and memory. Another
  account's object ID returns 404. Garmin token and FIT paths are separate
  per account, including background polling and manual CLI operations.
- Complete imported training books and passages form one shared library.
  Incomplete imports remain hidden from retrieval.
- The website coach obtains its rider context and data tools through the
  authenticated `/mcp` endpoint. MCP requires a short-lived, account-scoped
  Bearer JWT; the browser's cookie is not accepted there. External MCP client
  token issuance is deferred.
- The configured OpenAI monthly cap remains global across accounts.

## Development database reset

`soft-floyd prepare-account-db` copies complete books and passages from
`data/soft-floyd.db` into an empty `data/soft-floyd-accounts.db`. Rider-owned
rows start empty. The source database is never deleted or modified by this
command. A populated old database cannot migrate in place into account mode.
