# Reliability

## Garmin Connect is unofficial

There is no supported public API for Garmin Connect; ingestion (when
built) will use an unofficial client library. That means:

- Garmin can change behavior or rate-limit without notice. Map `401`s to
  a `ReauthRequired`-style error and surface it to the rider (CLI message
  or notification) rather than silently retrying forever.
- Map `429`/`5xx` to backoff, not immediate retry. The v0 implementation
  used a 10-minute poll interval with backoff up to 60 minutes — a
  reasonable default to reuse when sync is rebuilt.
- Never treat "Garmin is down" as "the rider has no data" — distinguish
  a sync failure from an empty result.

## LLM calls (once the coach agent exists)

- Every call goes through `packages/core/src/soft_floyd_core/llm/client.py`
  so cost accounting (`Usage.cost_usd`) is never bypassed.
- A failed LLM call should degrade to "I couldn't generate an analysis
  right now" — never to a fabricated response.

## Local server

- Single process, single SQLite file. No HA requirements — this runs on
  one machine for one rider. Restart-safe means: `Base.metadata.create_all()`
  (or, once it exists, Alembic) runs on boot and is idempotent.
- `soft-floyd serve` binds to `127.0.0.1` — a bind failure (port in use)
  should error clearly, not silently pick another port.
