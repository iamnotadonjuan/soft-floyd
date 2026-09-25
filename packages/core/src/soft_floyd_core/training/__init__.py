"""Training sessions (exec-plan 0010): turn a rider's own idea for their
next ride into one structured, sensor-honest workout they can push to
Garmin or download for another device.

See docs/product-specs/training-sessions.md for the user-facing behavior
and docs/design-docs/sensor-capability-model.md for the rule every
module here defers to: `sanitize.py` is the single place a numeric
target is allowed into a workout, and it never invents one.
"""
