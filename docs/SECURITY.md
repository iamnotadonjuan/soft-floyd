# Security

## Threat model

Single-user, local-only application. The primary risks are: leaking the
rider's Garmin credentials/tokens or OpenAI API key, and accidentally
exposing the local server beyond the machine it runs on.

## Rules

- `soft-floyd serve` binds `127.0.0.1` by default. Do not change this
  default or add a `0.0.0.0` option without an explicit request — this
  app has no auth layer and is not meant to be reachable off-machine.
- No authentication layer, no multi-tenancy. If a future request asks for
  either, treat it as a significant scope change worth confirming, not a
  routine addition.
- Secrets (`SOFT_FLOYD_OPENAI_API_KEY`, Garmin credentials) come from
  `~/.soft-floyd/config.toml` or environment/`.env`, never hardcoded,
  never logged. `structlog` output must not include secret values —
  review new log lines that touch config. The Garmin **password** is
  never persisted at all — only the resulting token survives, whether
  login happens via `soft-floyd garmin-login` (hidden TTY prompt) or the
  browser (below).
- **Garmin login from the browser** (`POST
  /api/connections/garmin/login`, exec-plan 0004) is a deliberate,
  considered change from the CLI-only original design: the password now
  crosses a loopback HTTP boundary in a POST body instead of staying in
  a TTY prompt inside one process. On this app's actual threat model —
  bound to `127.0.0.1`, no TLS to strip on loopback, CORS still pinned to
  the Vite dev origin, nothing persisted beyond the request — the added
  exposure is small, but it is real, so the rule is: the password must
  never be written to the DB, `~/.soft-floyd/config.toml`, a log line, or
  browser storage (`localStorage`/`sessionStorage`/IndexedDB); it may
  live only in the request body and the login worker thread's stack
  (`soft_floyd_core.garmin.login.PendingLogin` / `run_login_in_background`),
  discarded once the login finishes or times out. The CLI's
  `soft-floyd garmin-login` stays available as the lower-exposure
  fallback. Do not add a browser-login flow for any future secret
  (an OpenAI key, a second provider's credentials) without this same
  review — treat it as a deliberate tradeoff each time, not a precedent
  that makes the next one automatic.
- **Garmin tokens are deliberately NOT Keychain/Fernet-wrapped**, unlike
  v0. `python-garminconnect` manages its own token cache at
  `settings.garmin_token_dir` (default `~/.soft-floyd/garmin/`) —
  `garmin_tokens.json`, written 0600 in a 0700 directory, auto-refreshed
  in place before it expires. Wrapping that file in our own encryption
  (v0's approach) would break the library's ability to silently
  re-persist a refreshed token, forcing a full SSO login against a
  Cloudflare-protected endpoint on every process restart — worse
  reliability for no real security gain in this threat model (Fernet key
  in the login Keychain vs. 0600 file both boil down to "readable by
  this same logged-in user"). Do not reintroduce the Keychain wrapper;
  if Garmin's token format changes such that this becomes riskier,
  revisit deliberately rather than defaulting back to v0's approach.
- `.env`, `data/` (the SQLite file and `data/fit/` FIT downloads), and the
  Garmin token directory are gitignored and must stay that way — check
  `.gitignore` before adding a new local secret/data path.
- CORS in `apps/server/src/soft_floyd_server/main.py` is restricted to
  the Vite dev origin; don't widen it to `*` for convenience.
