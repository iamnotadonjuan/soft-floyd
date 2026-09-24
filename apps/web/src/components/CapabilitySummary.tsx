import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { BikeOut, ProfileOut } from "../api/types";
import type { Messages } from "../i18n/en";
import { bikeKindLabel } from "./activityFormat";
import { useI18n } from "../i18n/I18nProvider";

function capabilityCopy(profile: ProfileOut, m: Messages): string {
  if (profile.capability_tier === "power") return m.capability.power(profile.has_hr_monitor);
  if (profile.capability_tier === "hr") return m.capability.hr;
  if (profile.capability_tier === "cadence") return m.capability.cadence(profile.has_cadence_sensor);
  return m.capability.basic;
}

export default function CapabilitySummary({ profile }: { profile: ProfileOut }) {
  const { m } = useI18n();
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
        {capabilityCopy(profile, m)}
      </div>

      {/* Only worth breaking out per-bike once there's more than one —
          a single-bike garage's tier already matches this summary
          exactly, so a second line would just repeat it. Core belief 4. */}
      {bikes && bikes.length > 1 && (
        <div className="body-muted space-y-1 px-1 text-sm">
          {bikes.map((bike) => (
            <p key={bike.id}>
              {m.capability.bikeLine(
                bike.nickname || bikeKindLabel(bike.kind, m),
                m.capability.tierLabel[bike.capability_tier],
                bike.is_primary,
              )}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
