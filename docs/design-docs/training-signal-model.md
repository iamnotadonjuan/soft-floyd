# Training Signal Model

Not yet implemented (metrics computation is out of scope for the
scaffold — see `docs/exec-plans/tech-debt-tracker.md`). This records the
formulas so the next exec-plan that builds `packages/core`'s metrics
module doesn't have to re-derive them. Gated by
[sensor-capability-model.md](sensor-capability-model.md) — only compute
the family the rider's hardware (and that activity's recorded streams)
support.

## Power-based (`power` tier)

- **FTP (Functional Threshold Power)** — rider-declared anchor,
  `ftp_watts` on the profile, until auto-detection is built.
- **Normalized Power (NP)** — 30s rolling average of power, raised to the
  4th power, averaged, 4th-rooted. Standard Coggan formula.
- **Intensity Factor (IF)** — `NP / FTP`.
- **Training Stress Score (TSS)** — `(duration_seconds * NP * IF) / (FTP * 3600) * 100`.
- **Power curve** — best mean-max power for standard durations
  (5s/1min/5min/20min/60min).

## HR-based (`hr` tier)

Carried forward from v0, correct and worth reusing as-is:

- **HR zones**, off configured LTHR (default 165 bpm):
  - Z1: below 80% LTHR
  - Z2: 80–89% LTHR
  - Z3: 90–94% LTHR
  - Z4: 95–99% LTHR
  - Z5: at least 100% LTHR
- **HR drift** — % increase in HR for the same output (pace/power) from
  the first half of a steady effort to the second half; a proxy for
  aerobic fitness/fatigue when power isn't available.
- **Decoupling** — ratio of (HR:pace or HR:power) in the second half of a
  ride vs. the first half; high decoupling suggests fading aerobic
  efficiency.
- **TRIMP (Training Impulse)** — HR-based training load, weighting time
  in each zone.
- **GAP (Grade-Adjusted Pace)** — pace normalized for elevation, used
  alongside HR to interpret effort without power.
- **VAM (Velocità Ascensionale Media)** — vertical meters climbed per
  hour, a climbing-specific effort proxy.

## Cadence/basic tiers

No dedicated formulas yet beyond raw cadence distribution and standard
ride summary stats (duration, distance, elevation gain, avg speed). These
tiers exist so the coach has *something* honest to say rather than
nothing, not to approximate the tiers above.

## Salvage note

v0's `src/coach/metrics/compute.py` and `zones.py` (preserved at git tag
`v0-legacy`) implement the HR-based formulas above with tests using
hand-computed expected values. When the metrics module is built, start by
reviewing those files rather than re-deriving from scratch — see
`docs/exec-plans/tech-debt-tracker.md`.
