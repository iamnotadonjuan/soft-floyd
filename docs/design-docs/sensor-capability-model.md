# Sensor Capability Model

The single rule that keeps the coach from making things up: **a metric is
available only if the sensor it requires is actually present.** This doc
is the source of truth; `packages/core/src/soft_floyd_core/profile/service.py`
(`capability_tier()`, `capability_tier_for_bike()`, `available_metrics()`)
is its one implementation — consulted by both the MCP tools and the REST
routes, and eventually the metrics/coaching layer.

Since exec-plan 0004, sensors are declared in two places with different
scopes: bike-mounted sensors (power, cadence, speed) live on `Bike` — one
row per bike in the rider's garage — while the body-worn HR monitor
stays on `RiderProfile`. `capability_tier()` is the *union* across every
bike plus the HR flag; `capability_tier_for_bike()` is the tier for one
specific bike (its own sensors plus the rider's HR monitor, which comes
along regardless of which bike is ridden).

## Why this exists

v0 of this project hardcoded a single rider with no power meter, so every
metric was HR-based by fiat. Real riders vary: some have a power meter,
most ride with just a wrist HR or a chest strap, some have neither and
just use the Edge's GPS. A coach that assumes one sensor profile either
under-uses riders who have more data, or — worse — fabricates data riders
don't have (estimating watts from speed and grade and presenting it as
measured power). Neither is acceptable; see
[core-beliefs.md](core-beliefs.md) belief 1.

## The tiers

| Rider has | Tier | Available metrics | Anchor value |
|---|---|---|---|
| Power meter (+ HR, almost always) | `power` | FTP, normalized power, intensity factor, TSS, power curve — **plus** all HR metrics below | FTP (watts) |
| HR monitor only | `hr` | HR zones (time-in-zone), HR drift, decoupling, TRIMP, GAP, VAM | LTHR (bpm), default 165 |
| Cadence and/or speed sensor only | `cadence` | Cadence distribution, duration, distance, elevation gain | — |
| Nothing beyond the head unit's GPS/barometer | `basic` | Duration, distance, elevation gain, avg speed | — |

Tier selection is priority-ordered top to bottom: power meter wins
regardless of what else is present; HR monitor is the next fallback; then
cadence/speed; `basic` is the floor. Gaining a sensor only ever adds
metrics — see `tests/test_capability_tier.py::test_power_tier_still_includes_hr_metrics`.

**A rider's overall tier is a union across their whole garage**, not an
intersection: a power meter on any one bike is enough to grant the
`power` tier profile-wide, even if every other bike is bare
(`test_power_meter_on_any_one_bike_is_enough`). This is deliberately
generous at the profile level — the *per-ride* view narrows back down
via `capability_tier_for_bike()` (garage summary, core belief 4: "power
on the road bike, heart rate only on the gravel bike") and, for an
actual recorded ride, `available_metrics_for_activity()` below (rule 1:
what that ride's FIT stream actually contains).

## Binding rules

1. **A metric is computed only if every sensor it needs is present in
   that specific activity's recorded data — not merely declared in the
   rider profile.** The profile's `has_power_meter` etc. are a *planning*
   signal (what to expect, what to ask about in onboarding); the FIT
   stream for a given ride is the *analysis* signal (what actually got
   recorded). A dead battery or a dropped strap on ride day means that
   ride analysis downgrades for that ride alone, even if the profile
   still says the sensor exists.
2. **Never estimate watts from HR, speed, or grade and present it as
   power.** If a derived/estimated value is ever shown for any reason, it
   must be visually and textually labeled as an estimate and must never
   feed load accounting (TSS, CTL/ATL, etc.).
3. **`ftp_watts` and `lthr` are anchor values, not capability flags.** A
   stale `ftp_watts` left over from a rider whose garage no longer has
   any power-meter bike must not grant the `power` tier — the sensor
   flag (a `Bike.has_power_meter=True` somewhere in the garage) is what
   gates the tier; the anchor is only used once the tier already permits
   it. Enforced by
   `test_ftp_alone_without_any_power_meter_bike_does_not_grant_power_tier`.
4. **Downgrade gracefully, and say so.** "No power meter today, so I'm
   reading this ride through HR drift and time in zone" is good coaching.
   Silently switching the model rider-to-rider or ride-to-ride, without
   naming the switch, is not.
5. **Sensors are editable, and the tier moves immediately.** A rider who
   adds a power meter to a bike (or a whole new bike) mid-season updates
   it via the bikes endpoints and the very next `get_rider_profile()` /
   `GET /api/profile` call reflects the new tier and expanded allowlist
   — there is no migration step for this.

## Where this shows up

- `packages/core/src/soft_floyd_core/models.py` — `Bike`'s
  `has_power_meter`/`has_cadence_sensor`/`has_speed_sensor` plus
  `RiderProfile.has_hr_monitor` and `ftp_watts`/`lthr` (the *planning*
  signal, split across a garage of bikes and the rider themself); the
  five `has_*_data` bool columns plus `fit_status` on `Activity` (the
  *analysis* signal, per rule 1).
- `packages/core/src/soft_floyd_core/profile/service.py` —
  `capability_tier()` (garage-wide union), `capability_tier_for_bike()`
  (one bike), `available_metrics()`, `METRICS_BY_TIER`.
- `packages/core/src/soft_floyd_core/bikes/service.py` — `BikeOut`
  carries its own `capability_tier` per bike, computed the same way.
- `packages/core/src/soft_floyd_core/activities/sensors.py` —
  `detect_sensor_streams()`, the one function that derives rule 1's
  per-ride analysis signal from actual parsed FIT records. Never imports
  `RiderProfile`/`profile`/`Settings` — enforced by a static-scan test.
- `packages/core/src/soft_floyd_core/activities/service.py` —
  `available_metrics_for_activity()`, which intersects the two signals:
  the profile's general allowlist with what this specific ride's streams
  support. This is the function an agent should consult before discussing
  metrics for one ride — narrower than the profile-level
  `get_available_metrics`.
- `apps/web`'s onboarding `GarageStep`/`AnchorsStep` (and their Settings
  equivalents) — see `docs/product-specs/new-user-onboarding.md`.
- The (future) coach system prompt must state this model explicitly and
  treat `available_metrics_for_activity` (per-ride) as the hard allowlist
  when discussing a specific ride, not the profile-level
  `get_available_metrics`.
