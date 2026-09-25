# Security

## Threat model and boundary

Soft Floyd accepts multiple Google accounts but still binds to `127.0.0.1`
by default. Every rider-data REST route requires a revocable web JWT; every
`/mcp` request requires a separate, short-lived Bearer JWT. The web coach
obtains its MCP token on the server after verifying the browser session.
Books and passages are shared; profiles, rides, Garmin state, conversations,
notes and usage attribution are account-owned.

The web JWT is kept in an HttpOnly, SameSite=Lax cookie. State-changing
cookie requests require the configured web Origin. The Google authorization
code flow uses state, nonce and PKCE; the backend verifies the signed Google
ID token and uses its stable `sub` as the account identity. Sign-out revokes
the server-side session record, which also invalidates its MCP grants.
Google client credentials and the JWT signing secret come from environment
or local config; they must not be committed or logged. The signing secret
must contain at least 32 characters. Local HTTP is only for localhost;
future remote hosting requires HTTPS and secure cookies.

## Account data

ORM reads and writes of rider-owned tables are scoped to the authenticated
account in `packages/core/account_scope.py`; no request may choose an owner
ID. Garmin token caches live in separate directories under
`SOFT_FLOYD_GARMIN_TOKEN_DIR/<account-id>/`, and FIT files under
`SOFT_FLOYD_FIT_DIR/<account-id>/`. The unofficial Garmin library owns token
refresh and persistence. Tokens must remain in private local directories.
Garmin passwords are used only for the login request or CLI prompt and are
never stored. Login and rate-limit failures surface as actionable errors.

The old single-rider database is preserved. The account-era database starts
with fresh rider tables and a verified copy of complete books/passages. An
attempt to migrate a populated legacy database in place is rejected.

## Operational limits

`/api/health` and Google login start/callback are public. Keep CORS restricted
to the local web origin, never use wildcard origins, and do not bind the app
publicly as a shortcut. External MCP client setup and production hardening
are future work; no long-lived MCP token is issued in this release. The
OpenAI cost cap is global across all accounts using the configured API key.
