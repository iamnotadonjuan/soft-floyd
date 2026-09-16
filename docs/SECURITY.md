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
- Secrets (`SOFT_FLOYD_OPENAI_API_KEY`, and later Garmin credentials/tokens)
  come from `~/.soft-floyd/config.toml` or environment/`.env`, never
  hardcoded, never logged. `structlog` output must not include secret
  values — review new log lines that touch config.
- On macOS, prefer OS Keychain (`keyring`) over a plaintext token file for
  anything long-lived, once Garmin auth is rebuilt — this was the v0
  approach and is worth keeping.
- `.env`, `data/` (the SQLite file), and any token cache are gitignored
  and must stay that way — check `.gitignore` before adding a new local
  secret/data path.
- CORS in `apps/server/src/soft_floyd_server/main.py` is restricted to
  the Vite dev origin; don't widen it to `*` for convenience.
