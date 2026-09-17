# python-garminconnect (`garminconnect` package)

Verified 2026-09-16 against the installed `garminconnect==0.3.15` by
reading its source and calling `inspect.signature` on its public API
directly — not from memory or documentation, since this library is
under active churn (see the `garth` deprecation below).

## Status

Actively maintained, unofficial (reverse-engineered Garmin Connect
mobile-app API), free. It **no longer depends on `garth`** — `garth` was
declared deprecated 2026-03-27 after Garmin added Cloudflare TLS
fingerprinting that broke garth's mobile-auth User-Agent. `garminconnect`
moved to its own `curl_cffi`-based login (TLS fingerprint impersonation)
with a multi-strategy, self-validating auth flow.

**This is why `respx` (an `httpx` mock) is useless here** — this
package transports over `curl_cffi`, not `httpx`. Every test of Garmin
behavior in this repo mocks at the `garminconnect.Garmin` object
boundary instead (a `client_factory` constructor param — see
`packages/core/src/soft_floyd_core/garmin/client.py`), which is
independent of whatever HTTP library the package uses internally.

## Key API facts (verified against 0.3.15)

```python
Garmin(
    email: str | None = None,
    password: str | None = None,
    is_cn: bool = False,
    prompt_mfa: Callable[[], str] | None = None,
    return_on_mfa: bool = False,
    retry_attempts: int = 3,
    retry_min_wait: float = 1.0,
    retry_max_wait: float = 10.0,
    verify_login: bool = True,
)

Garmin.login(tokenstore: str | None = None) -> tuple[str | None, str | None]
Garmin.get_activities(start=0, limit=20, activitytype=None, activitysubtype=None) -> dict | list
Garmin.download_activity(activity_id: str, dl_fmt=ActivityDownloadFormat.TCX) -> bytes
```

- **`login(tokenstore)` manages its own token cache.** Point it at a
  directory path (e.g. `~/.soft-floyd/garmin/`); the library writes/reads
  `garmin_tokens.json` there itself, refreshing it in place before
  expiry. No manual `save()`/`resume()` calls, no separate encryption
  layer needed or wanted — see `docs/SECURITY.md`.
- **`verify_login=True` (the default) means construction/login makes a
  real network call.** Never construct or call `.load()` on a
  `GarminClient` from an event loop or an app lifespan hook — only from a
  background worker thread (`anyio.to_thread.run_sync` in this repo).
- **`download_activity(dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)`
  returns zip bytes**, not a raw FIT file — the archive must be unzipped
  to find the `.fit` member inside (confirmed, not assumed; ported v0's
  unzip helper unchanged).
- **The library retries internally**: 3 attempts (configurable), 5xx and
  network errors only, exponential backoff with jitter — it deliberately
  never retries 401/429. Our own `run_sync_cycle`/`SyncRunner` backoff
  sits on top of this; don't add a third retry layer.
- The `GARMINTOKENS` environment variable is a fallback token-dir
  location the library supports — deliberately unused here; the token
  dir always comes from `Settings.garmin_token_dir` (one settings
  mechanism, not two).

## Exception classes (verified present, by name, in 0.3.15)

`GarminConnectAuthenticationError`, `GarminConnectTooManyRequestsError`,
`GarminConnectNotFoundError`, `GarminConnectConnectionError`,
`GarminConnectInvalidFileFormatError`. The first two carry **no
`.response` attribute** — status-sniffing on them finds nothing, so
`soft_floyd_core.garmin.errors.map_garmin_exception` checks these by
class name first, before falling back to status-code inspection. Some
`GarminConnectConnectionError` messages are shaped like
`"API Error 503 - ..."` — the status-sniffing regex matches that pattern
too, not just a bare `\d{3}`.

## Re-verify if `garminconnect` is upgraded

This library is under active development post-garth-deprecation. Before
trusting this note against a newer version, re-run:

```bash
uv run python -c "import garminconnect; print(garminconnect.__file__)"
uv run python -c "import inspect; from garminconnect import Garmin; print(inspect.signature(Garmin.login))"
```
