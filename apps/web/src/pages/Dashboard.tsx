import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ProfileOut } from "../api/types";

const TIER_LABEL: Record<ProfileOut["capability_tier"], string> = {
  power: "Power",
  hr: "Heart rate",
  cadence: "Cadence",
  basic: "Basic",
};

export default function Dashboard({
  profile,
  onOpenSettings,
}: {
  profile: ProfileOut;
  onOpenSettings: () => void;
}) {
  const [activityCount, setActivityCount] = useState<number | null>(null);

  useEffect(() => {
    api.listActivities().then((activities) => setActivityCount(activities.length));
  }, []);

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium tracking-wide text-neutral-400">SOFT FLOYD</p>
          <h1 className="text-2xl font-semibold">Welcome back</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-full border border-neutral-300 px-3 py-1 text-sm">
            {TIER_LABEL[profile.capability_tier]} tier
          </span>
          <button onClick={onOpenSettings} className="text-sm text-neutral-500 underline">
            Settings
          </button>
        </div>
      </div>

      <div className="mb-6 rounded-md border border-neutral-200 p-4">
        <p className="text-sm text-neutral-500">Goal</p>
        <p className="font-medium">{profile.goal_text}</p>
        <p className="mt-2 text-sm text-neutral-500">
          {profile.weekly_rides} rides / {profile.weekly_hours}h per week
          {profile.primary_discipline && <> &middot; {profile.primary_discipline}</>}
        </p>
      </div>

      <div className="rounded-md border border-dashed border-neutral-300 p-8 text-center text-neutral-500">
        {activityCount === null ? (
          "Loading activities…"
        ) : (
          <>
            <p className="font-medium">No rides synced yet.</p>
            <p className="mt-1 text-sm">
              Garmin sync isn't built yet — see docs/product-specs/garmin-sync.md.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
