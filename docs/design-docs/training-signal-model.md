# Training Signal Model

Partly implemented (exec-plan 0012, `packages/core/src/soft_floyd_core/metrics/`):
NP, IF, TSS, HR zones, time in zone, and the CTL/ATL/TSB load model built
on them. Each section below says what is built and what is not. This
records the formulas so later work doesn't have to re-derive them. Gated by
[sensor-capability-model.md](sensor-capability-model.md) — only compute
the family the rider's hardware (and that activity's recorded streams)
support.

## Power-based (`power` tier)

Built in `metrics/load.py`: NP, IF and TSS. FTP stays rider-declared and
the power curve is not built.

- **FTP (Functional Threshold Power)** — rider-declared anchor,
  `ftp_watts` on the profile, until auto-detection is built.
- **Normalized Power (NP)** — 30s rolling average of power, raised to the
  4th power, averaged, 4th-rooted. Standard Coggan formula.
- **Intensity Factor (IF)** — `NP / FTP`.
- **Training Stress Score (TSS)** — `(duration_seconds * NP * IF) / (FTP * 3600) * 100`.
- **Power curve** — best mean-max power for standard durations
  (5s/1min/5min/20min/60min).

## HR-based (`hr` tier)

Carried forward from v0, correct and worth reusing as-is. **Built:** HR
zones and time-in-zone (`metrics/zones.py`, with `lthr_from_max_hr` for
riders who only declared a max HR). **Not built:** HR drift, decoupling,
GAP, VAM, and v0's Banister-Morton TRIMP (0012 uses the hrTSS scheme
below instead, so HR-based load sits on the same scale as power TSS):

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

## Training load (built, exec-plan 0012)

Per-ride load, on a TSS-like scale, from the best stream the ride's own
data verified (`metrics/load.py`):

- `power_np`: TSS from NP as above (30 s rolling mean on a 1 Hz grid that
  holds the last valid value across gaps; under 30 s of data falls back).
- `power_avg`: the same formula with average power standing in for NP.
- `hr_zones`: hours in each zone times a per-hour weight (Coggan's hrTSS:
  Z1 20, Z2 40, Z3 60, Z4 80, Z5 100 — his Z5a/b/c collapsed, so the very
  hardest efforts are undercounted a little). Needs HR samples covering at
  least half the ride.
- `hr_avg`: hours · (avg HR / LTHR)² · 100.
- `duration`: hours · 40, an estimate, always labelled as one.

Daily load is the sum of the day's rides. Then, with alpha = 1 − exp(−1/τ):

- **CTL** (fitness): exponentially-weighted average, τ = 42 days
- **ATL** (fatigue): the same, τ = 7 days
- **TSB** (form): CTL − ATL; **ramp rate**: CTL now minus CTL 7 days ago

Form labels (`metrics/service.py`): TSB ≥ 5 fresh, ≥ −10 neutral, ≥ −30
tired, below that very tired. `training/intent.py` treats a ramp above 8
points a week as too steep. All of these cut-offs are starting points, not
validated against riders' data yet. See
`docs/product-specs/training-load.md`.

## Cadence/basic tiers

No dedicated formulas yet beyond raw cadence distribution and standard
ride summary stats (duration, distance, elevation gain, avg speed). These
tiers exist so the coach has *something* honest to say rather than
nothing, not to approximate the tiers above.

## Salvage note

v0's `src/coach/metrics/compute.py` and `zones.py` (preserved at git tag
`v0-legacy`) implement the HR-based formulas above with tests using
hand-computed expected values. Exec-plan 0012 ported the zones and the
time-in-zone loop. Drift, decoupling, GAP and VAM are still only in the
tag: review them there rather than re-deriving from scratch — see
`docs/exec-plans/tech-debt-tracker.md`.
