import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { BikeOut, CapabilityTier } from "../api/types";

// Plain-language framing for each tier — see
// docs/design-docs/sensor-capability-model.md. Keep this in sync with
// packages/core/src/soft_floyd_core/profile/service.py's METRICS_BY_TIER
// if the tiers themselves ever change.
const TIER_COPY: Record<CapabilityTier, string> = {
  power:
    "You have a power meter, so I'll read your rides through FTP, normalized power, and " +
    "training stress — plus heart rate drift and time in zone.",
  hr: "No power meter, so I'll read your rides through heart rate drift and time in zone rather " +
    "than power.",
  cadence:
    "No power meter or HR monitor, so I'll work from cadence, duration, and elevation — " +
    "add a heart rate monitor for a much clearer picture of effort.",
  basic:
    "No sensors beyond your head unit's GPS, so I can only track duration, distance, and " +
    "elevation for now.",
};

const TIER_LABEL: Record<CapabilityTier, string> = {
  power: "power",
  hr: "heart rate",
  cadence: "cadence",
  basic: "GPS only",
};

export default function CapabilitySummary({ tier }: { tier: CapabilityTier }) {
  const [bikes, setBikes] = useState<BikeOut[] | null>(null);

  useEffect(() => {
    api
      .listBikes()
      .then(setBikes)
      .catch(() => setBikes([]));
  }, []);

  return (
    <div className="space-y-2">
      <div className="rounded-md border border-neutral-200 bg-neutral-100 px-4 py-3 text-sm">
        {TIER_COPY[tier]}
      </div>

      {/* Only worth breaking out per-bike once there's more than one —
          a single-bike garage's tier already matches this summary
          exactly, so a second line would just repeat it. Core belief 4. */}
      {bikes && bikes.length > 1 && (
        <div className="space-y-1 px-1 text-xs text-neutral-500">
          {bikes.map((bike) => (
            <p key={bike.id}>
              {bike.nickname || bike.kind} — read through {TIER_LABEL[bike.capability_tier]}
              {bike.is_primary ? " (primary)" : ""}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
