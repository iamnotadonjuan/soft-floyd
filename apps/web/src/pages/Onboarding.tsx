import { useState } from "react";

import { api } from "../api/client";
import type { Discipline, ProfileOut } from "../api/types";
import AnchorsStep from "../components/onboarding/AnchorsStep";
import CapabilitySummary from "../components/CapabilitySummary";
import GoalStep from "../components/onboarding/GoalStep";
import SensorsStep, { type SensorAnswers } from "../components/onboarding/SensorsStep";
import VolumeStep from "../components/onboarding/VolumeStep";

type Step = "volume" | "goal" | "sensors" | "anchors" | "summary";

interface Props {
  initialProfile: ProfileOut;
  onComplete: (profile: ProfileOut) => void;
}

export default function Onboarding({ initialProfile, onComplete }: Props) {
  const [step, setStep] = useState<Step>("volume");
  const [profile, setProfile] = useState<ProfileOut>(initialProfile);

  async function submitAndAdvance(patch: Record<string, unknown>, next: Step) {
    const updated = await api.updateProfile(patch);
    setProfile(updated);
    setStep(next);
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-4">
      <div className="w-full py-12">
        <p className="mb-2 text-sm font-medium tracking-wide text-neutral-400">SOFT FLOYD</p>

        {step === "volume" && (
          <VolumeStep
            initialRides={profile.weekly_rides}
            initialHours={profile.weekly_hours}
            onNext={(values) => submitAndAdvance(values, "goal")}
          />
        )}

        {step === "goal" && (
          <GoalStep
            initialGoal={profile.goal_text}
            initialDiscipline={profile.primary_discipline as Discipline}
            onNext={(values) => submitAndAdvance(values, "sensors")}
          />
        )}

        {step === "sensors" && (
          <SensorsStep
            initial={{
              has_power_meter: profile.has_power_meter,
              has_hr_monitor: profile.has_hr_monitor,
              has_cadence_sensor: profile.has_cadence_sensor,
              has_speed_sensor: profile.has_speed_sensor,
            }}
            onNext={async (values: SensorAnswers) => {
              const updated = await api.updateProfile(values);
              setProfile(updated);
              // Never ask for an anchor the rider has no way to produce.
              const needsAnchors = values.has_power_meter || values.has_hr_monitor;
              setStep(needsAnchors ? "anchors" : "summary");
            }}
          />
        )}

        {step === "anchors" && (
          <AnchorsStep
            hasPowerMeter={profile.has_power_meter}
            hasHrMonitor={profile.has_hr_monitor}
            initialFtp={profile.ftp_watts}
            initialLthr={profile.lthr}
            onNext={(values) => submitAndAdvance(values, "summary")}
          />
        )}

        {step === "summary" && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold">You're set up.</h2>
              <p className="text-neutral-500 text-sm">Here's what I'll coach you on:</p>
            </div>
            <CapabilitySummary tier={profile.capability_tier} />
            <button
              onClick={() => onComplete(profile)}
              className="w-full rounded-md bg-neutral-900 py-2 text-white font-medium"
            >
              Go to dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
