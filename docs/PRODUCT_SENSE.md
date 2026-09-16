# Product Sense

## Who this is for

One rider (initially the repo owner), riding road and/or MTB on a Garmin
Edge device, who wants a coach that notices patterns across rides rather
than a dashboard that just shows numbers back. Hardware varies rider to
rider and even ride to ride — some have a power meter, most don't, all
have *something* on the Edge.

## What "good coaching" means here

- **Honest about what it can see.** A coach that says "I can't tell you
  TSS without a power meter, but your HR drift on the back half of that
  climb was high" is trustworthy. A coach that quietly estimates power
  from speed and grade is not — see
  [design-docs/sensor-capability-model.md](design-docs/sensor-capability-model.md).
- **Long-term over hero-session.** Celebrate consistency and recovery,
  not just a big number on one ride. See
  [design-docs/core-beliefs.md](design-docs/core-beliefs.md).
- **Actionable, not just descriptive.** "Your decoupling was 8% today,
  higher than your rolling average" is a fact. "That suggests your
  aerobic base needs another few weeks before adding more Z4" is
  coaching. Aim for the second.
- **Respects the goal the rider actually stated.** A rider training for a
  gran fondo and a rider training for enduro racing need different
  framing even off similar raw metrics.

## What we refuse to build

- Anything that fabricates a sensor reading and presents it as measured.
- A public/multi-tenant product — this is a personal tool, not a SaaS.
  Don't add auth, billing, or a second user without an explicit ask.
- A dashboard that outgrows the rider's actual sensors — no power-focused
  UI chrome (power curves, W′ balance) shown to a rider without a power
  meter, even as a grayed-out teaser. If they don't have it, it doesn't
  appear.
