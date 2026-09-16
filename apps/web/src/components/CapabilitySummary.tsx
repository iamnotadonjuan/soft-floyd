import type { CapabilityTier } from "../api/types";

// Plain-language framing for each tier — see
// docs/design-docs/sensor-capability-model.md. Keep this in sync with
// packages/core/src/soft_floyd_core/profile/service.py's METRICS_BY_TIER
// if the tiers themselves ever change.
const TIER_COPY: Record<CapabilityTier, string> = {
  power: "You have a power meter, so I'll read your rides through FTP, normalized power, and " +
    "training stress — plus heart rate drift and time in zone.",
  hr: "No power meter, so I'll read your rides through heart rate drift and time in zone rather " +
    "than power.",
  cadence: "No power meter or HR monitor, so I'll work from cadence, duration, and elevation — " +
    "add a heart rate monitor for a much clearer picture of effort.",
  basic: "No sensors beyond your head unit's GPS, so I can only track duration, distance, and " +
    "elevation for now.",
};

export default function CapabilitySummary({ tier }: { tier: CapabilityTier }) {
  return (
    <div className="rounded-md border border-neutral-200 bg-neutral-100 px-4 py-3 text-sm">
      {TIER_COPY[tier]}
    </div>
  );
}
