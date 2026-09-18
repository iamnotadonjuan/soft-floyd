# 0003 — Garmin Auth Repair

## Context

Soft Floyd's Garmin sync was dead: `~/.soft-floyd/garmin/` existed but
was empty — no `garmin_tokens.json` had ever landed there. Meanwhile the
upstream `python-garminconnect` repo's own `demo.py`, run standalone,
logged in cleanly and wrote a valid token to `~/.garminconnect/`.

The library itself was not the problem — the checked-out reference copy
of `garminconnect` and the version installed in this project's `.venv`
are the same version (0.3.15) and byte-identical (only `.pyc` files
differ). Three defects in our own wrapper code caused the breakage:

1. **`GarminClient.login()` could report success without persisting a
   token.** `garminconnect`'s own `Garmin.login()` wraps its token
   `dump()` in `contextlib.suppress(Exception)` — a failed write is
   silent upstream. Our wrapper didn't check afterward, so
   `soft-floyd garmin-login` could print "Logged in" while leaving the
   token directory empty. The next sync then reported `ReauthRequired`,
   prompting another interactive login — and repeating that loop is what
   walks straight into Garmin's login rate limit (each login runs a full
   5-strategy SSO chain against Cloudflare-protected endpoints).
2. **A stale/corrupt token file was mis-classified as a generic error,
   not a re-auth signal.** `garminconnect` re-wraps a structurally bad
   token load into `GarminConnectConnectionError`, not an auth error.
   Our `map_garmin_exception` checked class name and HTTP status only,
   so this fell through to a generic `GarminApiError` — the poller then
   grew `consecutive_errors` and backed off indefinitely instead of
   surfacing `ReauthRequired` and notifying the user.
3. **A small server `Retry-After` could shrink an already-large earned
   backoff** in the poller's rate-limited branch.

**Done means:** one `soft-floyd garmin-login` writes a verified token,
`soft-floyd garmin-sync` ingests the latest ride, and a login attempt
made while a prior 429 cooldown is still active is refused locally
(no network call) rather than retried against Garmin.

## Design

All logic lives in `packages/core`; `apps/server`'s `cli.py` stays a
thin prompt/print adapter (per `AGENTS.md`). Follows
`docs/RELIABILITY.md`'s existing rule: map auth/rate-limit failures to
actionable errors, never silently retry forever.

- `GarminClient.login()` verifies the token file actually exists after
  a successful-looking library call, closing defect (1) at the source.
- `map_garmin_exception` gets a message-shape check for the library's
  stale-token wording, ahead of status-code sniffing, closing (2).
- A new `garmin/login.py::perform_login` owns a login cooldown, backed
  by a new `GarminSyncState.login_blocked_until` column (single-row
  state, alongside the existing `last_status`/`consecutive_errors`).
  On a 429 it sets the block to `now + (retry_after_s or
  garmin_login_cooldown_minutes)`; a call while blocked raises
  `GarminRateLimited` without touching the network; success clears the
  block and resets error counters so the poller resumes immediately.
- `SyncRunner.run_forever`'s rate-limited branch takes
  `max(retry_after_s, backoff_seconds(...))` instead of preferring
  `retry_after_s` unconditionally, closing (3).

## Steps

1. `packages/core/src/soft_floyd_core/garmin/client.py`: verify
   `has_token()` after `client.login()`; raise `GarminApiError` if
   absent.
2. `packages/core/src/soft_floyd_core/garmin/errors.py`: recognize
   `GarminConnectConnectionError` messages shaped like a stale-token
   load failure as `ReauthRequired`.
3. `models.py`: add `GarminSyncState.login_blocked_until`; generate and
   review the Alembic migration.
4. `config.py` / `.env.example`: add `garmin_login_cooldown_minutes`
   (default 30).
5. New `garmin/login.py`: `perform_login()` and `clear_login_block()`.
6. `apps/server/src/soft_floyd_server/cli.py`: `garmin-login` calls
   `perform_login`; validate an existing token with `client.load()`
   before short-circuiting; add `--verbose`; `garmin-logout` clears the
   block.
7. `garmin/sync.py`: fix the rate-limited delay calculation.
8. Tests: `test_garmin_client.py`, `test_garmin_errors.py`,
   `test_sync_cycle.py`, new `test_garmin_login.py`.
9. Docs: correct `docs/references/garminconnect-notes.md`,
   `docs/RELIABILITY.md`, `docs/product-specs/garmin-sync.md`.

## Verification

```bash
make check
uv run alembic upgrade head
uv run soft-floyd garmin-login --force --verbose
ls -l ~/.soft-floyd/garmin/garmin_tokens.json
uv run soft-floyd garmin-sync
ls data/fit/
```

Re-running `garmin-login --force` twice in a row after a 429: the
second attempt must be refused locally with the cooldown message, no
network call made.
