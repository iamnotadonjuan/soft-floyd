# Connected Apps

Status: **implemented** (exec-plan 0004). Backing: no new table — a
provider-shaped read model over the existing `GarminSyncState`
(`packages/core/src/soft_floyd_core/connections/service.py`). UI:
`apps/web/src/components/connections/` (`ConnectionsPanel`,
`ConnectionCard`, `GarminLoginForm`), mounted by both onboarding's
Connect step and Settings.

## Why this exists

Garmin is the only data source today, but it won't be the only one
forever (Strava, Wahoo, a second head unit). The rider should see one
"Connected apps" section that lists whatever is hooked up and its health
— not Garmin-specific chrome — so a second provider is a backend addition
plus one new login-form component, not a UI redesign.

## What a connection is

```
ConnectionOut
  provider               "garmin"
  display_name           "Garmin Connect"
  status                 connected | disconnected | reauth_required
                          | rate_limited | error
  last_sync_at           datetime | null
  last_error             human-readable string | null — never a token
  supports_login_in_app  bool
  detail                 short free-text, e.g. "Polls every 10 min"
```

`GET /api/connections` / MCP `get_connections` return the full list.
Status is derived from `GarminSyncState` + whether a token file exists
at `settings.garmin_token_dir` — no token at all always means
`disconnected`, even if `last_status` says something else (a stale
status from before the rider disconnected shouldn't outlive the token).

## Connecting Garmin from the browser

A rider without a Garmin token, or whose token needs re-auth, sees a
login form (email + password, then an MFA code if Garmin asks for one)
inline in the connection card. This is a genuine two-request handshake
against a real synchronous SSO login running on a background thread:

1. `POST /api/connections/garmin/login {email, password}` → either
   `{"state": "connected"}` (no MFA needed) or `{"state":
   "mfa_required"}`.
2. If MFA was required: `POST /api/connections/garmin/mfa {code}` →
   `{"state": "connected"}`, or the login's error (wrong code, timeout)
   surfaced as an HTTP error with a human-readable message.
3. `DELETE /api/connections/garmin` disconnects (clears the token and
   the login cooldown).

The password is never persisted — it lives only in the request body and
the login worker thread's stack, and is discarded once the login
finishes. A prior 429 rate-limit's cooldown (exec-plan 0003) applies here
exactly as it does to the CLI's `soft-floyd garmin-login`, since both go
through the same `perform_login`. See
[garmin-sync.md](garmin-sync.md) and `docs/SECURITY.md` for the full
tradeoff of doing this over HTTP instead of a TTY prompt.

While a login is in flight (including mid-MFA-handshake), the shared
`SyncRunner` lock is held, so a background poll cycle can never race a
login attempt — see `packages/core/src/soft_floyd_core/garmin/sync.py`'s
`SyncRunner.login`/`submit_mfa`.

## MCP surface

Read-only: `get_connections` mirrors `GET /api/connections` exactly.
There is deliberately no MCP tool to start a login — a Garmin password
has no business flowing through an LLM tool-call, so that flow is
browser-only.

## Acceptance

- `GET /api/connections` and MCP `get_connections` agree
  (`tests/test_mcp_tools.py::test_mcp_and_rest_agree_on_connections`).
- Every `GarminSyncState.last_status` value maps to the documented
  `ConnectionOut.status`, and a missing token always wins as
  `disconnected` regardless of `last_status`
  (`tests/test_connections.py::test_status_mapping`).
- The login handshake — no MFA, correct MFA, wrong MFA, an abandoned MFA
  wait, and a concurrent second login attempt — behaves as specced
  against a fake Garmin client (`tests/test_connections.py`).
- A disconnect uses the same in-process `GarminClient` the background
  poller uses, not a second one, so sync resumes correctly on
  reconnection without a server restart
  (`tests/test_connections.py::test_logout_uses_the_runners_own_client_not_a_second_one`).
