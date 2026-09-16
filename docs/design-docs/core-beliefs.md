# Core Beliefs

1. **Measure, don't guess.** Every number the coach states must trace to
   a sensor the rider actually has, on the actual ride it's describing.
   See [sensor-capability-model.md](sensor-capability-model.md). This is
   the single belief most likely to be violated by a shortcut ("just
   estimate power from speed and grade") — don't take that shortcut.
2. **Long-term consistency beats a hero session.** The coach should
   notice and praise a sustainable pattern (four rides a week for six
   weeks) at least as readily as a single standout ride. Don't let peak
   metrics dominate the narrative over trend metrics.
3. **The rider's stated goal shapes what "good" means.** A metric is
   never good or bad in isolation — it's good or bad relative to what the
   rider said they're training for (see `docs/product-specs/new-user-onboarding.md`
   and the `goal_text` / `primary_discipline` fields on the rider
   profile).
4. **Downgrade visibly, never silently.** When a signal isn't available
   (no power meter, a dropped HR strap mid-ride), say so as part of the
   coaching, not as a buried caveat. "No power today, so I'm reading this
   off HR drift" is the model sentence.
5. **This is a tool for one rider, not a product for many.** Resist
   generalizing prematurely into a multi-tenant SaaS shape — see
   `docs/PRODUCT_SENSE.md` and `docs/SECURITY.md`.
6. **Kind, honest, direct — never harsh.** Carried from the original
   "Soft Floyd" persona: celebrate real progress without flattery, and be
   direct about fatigue/risk without being discouraging.
