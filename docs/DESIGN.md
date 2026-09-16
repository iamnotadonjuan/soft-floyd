# Design Principles

Soft Floyd's UI is small on purpose — it exists to onboard the rider,
show what the coach currently knows, and (later) hold a conversation and
a ride chart. It is not a Strava competitor.

## Principles

- **Calm over dense.** One primary action per screen during onboarding.
  The dashboard, once activities exist, favors a handful of legible
  numbers over a wall of stats.
- **No fake precision.** Never show a metric to more decimal places than
  the source sensor supports, and never show a metric the rider's
  hardware can't produce — see
  [design-docs/sensor-capability-model.md](design-docs/sensor-capability-model.md).
  A missing signal is an empty state with an honest explanation ("no
  power meter — reading this ride off HR drift"), not a guess.
- **The tier is visible.** The rider's capability tier (`power` / `hr` /
  `cadence` / `basic`) is shown, not hidden — it explains why the coach
  says what it says, and it should update the moment they add hardware.
- **Progressive onboarding.** Ask for training volume and goals before
  sensors, and only ask for an anchor value (FTP, LTHR) once its sensor
  is confirmed present. Never ask for a number the rider can't supply.

See [FRONTEND.md](FRONTEND.md) for how these principles map to components.
