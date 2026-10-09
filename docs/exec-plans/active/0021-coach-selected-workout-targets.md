# Coach-selected workout targets

## Context

Workout steps already store concrete power, HR and cadence ranges, but the
planner is not explicit about choosing each step's effort from the rider's
request and verified ride history. Garmin Connect upload and FIT download
also need to preserve the displayed custom range. Done means a rider can
follow the same sensor-backed step target on screen and on their device.

## Design

Keep the saved FTP and LTHR as anchors; never infer new thresholds from
rides. The shared core generator chooses effort per step from the request,
intent, load and verified recent rides. It supplies an HR alternative for a
power step when suitable. The sanitizer remains the only place numeric
targets enter a stored workout, using the selected bike and rider sensors.
Power is the usual effort target when available; HR is next. Cadence is
only a target for cadence-specific drills, never a proxy for effort. Other
steps retain a plain-language cue. Follow the sensor capability model.

Export custom absolute ranges to Garmin Connect and FIT. FIT's absolute
power and HR values require their specified encoding offsets. Keep the
public workout shape and database schema unchanged.

## Steps

1. Refine the generator prompt and its available sensor context, then add
   an optional HR fallback to the private draft target shape.
2. Resolve fallback targets and reject unsupported targets in the core
   sanitizer.
3. Correct Garmin Connect and FIT target encoding and show both numeric
   target and effort cue in the shared workout card.
4. Update the training product specification and verify the behavior.

## Verification

- Test differing step intensities, sensor and missing-anchor fallbacks, and
  coach/Training use of the same core generator.
- Check Garmin payload ranges and FIT round trips for power and HR, including
  repeat steps.
- With a connected account, compare one sent workout in Garmin Connect and
  on an Edge with the card in Soft Floyd.
- Run `make check` and self-score against `docs/QUALITY_SCORE.md`.

## Build status

Implemented and checked on 2026-10-08. `make check` passed (303 Python
tests, web lint and TypeScript); existing web lint warnings remain. The
normal Training and coach planning paths now both provide verified recent
ride details to the generator. FIT round-trip tests check custom absolute
power and HR values, and payload tests check Garmin custom ranges. Live
Garmin Connect and Edge review remains pending, so this plan stays active.

Quality self-score: correctness passes automated checks, with live Garmin
behavior still unverified; single source of truth, sensor honesty, tests,
docs, scope, and account isolation pass. No schema or public API changes.
