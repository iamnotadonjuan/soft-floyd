import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { BikeOut, CapabilityTier, ProfileOut } from "../api/types";

function capabilityCopy(profile: ProfileOut): string {
  if (profile.capability_tier === "power") {
    return `Your garage includes a power meter${profile.has_hr_monitor ? " and you wear a heart rate monitor" : ""}. I’ll only use those signals on rides where Garmin actually recorded them.`;
  }
  if (profile.capability_tier === "hr") {
    return "You ride with a heart rate monitor. I’ll use heart rate on rides where it was recorded, alongside time, distance, and elevation.";
  }
  if (profile.capability_tier === "cadence") {
    return `Your garage includes ${profile.has_cadence_sensor ? "a cadence sensor" : "a speed sensor"}. I’ll work from the signals recorded on each ride, plus time, distance, and elevation.`;
  }
  return "With your current setup I can use ride time, distance, and elevation. I won’t invent heart rate or power readings.";
}

const TIER_LABEL: Record<CapabilityTier, string> = {
  power: "power",
  hr: "heart rate",
  cadence: "cadence",
  basic: "GPS only",
};

export default function CapabilitySummary({ profile }: { profile: ProfileOut }) {
  const [bikes, setBikes] = useState<BikeOut[] | null>(null);

  useEffect(() => {
    api
      .listBikes()
      .then(setBikes)
      .catch(() => setBikes([]));
  }, []);

  return (
    <div className="space-y-2">
      <div className="surface-soft px-5 py-4 text-sm leading-relaxed">
        {capabilityCopy(profile)}
      </div>

      {/* Only worth breaking out per-bike once there's more than one —
          a single-bike garage's tier already matches this summary
          exactly, so a second line would just repeat it. Core belief 4. */}
      {bikes && bikes.length > 1 && (
        <div className="body-muted space-y-1 px-1 text-sm">
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
