import { useState } from "react";

import { api } from "../api/client";
import type { ProfileIn, ProfileOut, Weekday } from "../api/types";
import type { AboutYouValue } from "../components/onboarding/AboutYouStep";
import AboutYouStep from "../components/onboarding/AboutYouStep";
import AnchorsStep from "../components/onboarding/AnchorsStep";
import CapabilitySummary from "../components/CapabilitySummary";
import ConnectStep from "../components/onboarding/ConnectStep";
import GarageStep from "../components/onboarding/GarageStep";
import GoalsStep from "../components/onboarding/GoalsStep";
import HabitsStep from "../components/onboarding/HabitsStep";

type Step = "habits" | "goals" | "garage" | "about" | "anchors" | "connect" | "summary";

// Fixed order for the progress indicator below — "anchors" is sometimes
// skipped in navigation (no sensor to ask an anchor for), so this is a
// display approximation, not a strict traversal record.
const STEP_ORDER: Step[] = ["habits", "goals", "garage", "about", "anchors", "connect", "summary"];

interface Props {
  initialProfile: ProfileOut;
  onComplete: (profile: ProfileOut) => void;
}

// Order follows docs/DESIGN.md: volume and goals before sensors, and
// never ask for a number the rider can't produce. See
// docs/product-specs/new-user-onboarding.md for the full flow.
export default function Onboarding({ initialProfile, onComplete }: Props) {
  const [step, setStep] = useState<Step>("habits");
  const [profile, setProfile] = useState<ProfileOut>(initialProfile);

  async function submitAndAdvance(patch: ProfileIn, next: Step) {
    const updated = await api.updateProfile(patch);
    setProfile(updated);
    setStep(next);
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-4">
      <div className="w-full py-12">
        <p className="mb-2 text-sm font-medium tracking-wide text-neutral-400">SOFT FLOYD</p>

        {step !== "summary" && (
          <div className="mb-6">
            <p className="mb-1 text-xs text-neutral-400">
              Step {STEP_ORDER.indexOf(step) + 1} of {STEP_ORDER.length - 1}
            </p>
            <div className="h-1 w-full rounded-full bg-neutral-100">
              <div
                className="h-1 rounded-full bg-neutral-900 transition-all"
                style={{
                  width: `${((STEP_ORDER.indexOf(step) + 1) / (STEP_ORDER.length - 1)) * 100}%`,
                }}
              />
            </div>
          </div>
        )}

        {step === "habits" && (
          <HabitsStep
            initialRides={profile.weekly_rides}
            initialHours={profile.weekly_hours}
            initialAvailability={{
              available_days: profile.available_days as Weekday[],
              weekday_max_minutes: profile.weekday_max_minutes,
              weekend_max_minutes: profile.weekend_max_minutes,
            }}
            onNext={(values) => submitAndAdvance(values, "goals")}
          />
        )}

        {step === "goals" && (
          <GoalsStep
            initialGoal={profile.goal_text}
            initialFocusAreas={profile.focus_areas}
            initialTargetEventName={profile.target_event_name}
            initialTargetEventDate={profile.target_event_date}
            onNext={(values) => submitAndAdvance(values, "garage")}
          />
        )}

        {step === "garage" && (
          <GarageStep
            onNext={async () => {
              // Bikes don't live on the profile — refetch so
              // has_power_meter/primary_discipline (derived from the
              // garage) are current before Anchors/Summary need them.
              const refreshed = await api.getProfile();
              setProfile(refreshed);
              setStep("about");
            }}
          />
        )}

        {step === "about" && (
          <AboutYouStep
            initial={{
              birth_year: profile.birth_year,
              weight_kg: profile.weight_kg,
              max_hr: profile.max_hr,
              years_riding: profile.years_riding,
              longest_recent_ride_km: profile.longest_recent_ride_km,
              self_rated_level: profile.self_rated_level,
              followed_plan_before: profile.followed_plan_before,
              health_notes: profile.health_notes,
            }}
            onNext={(values: AboutYouValue) => {
              const needsAnchors = profile.has_power_meter || profile.has_hr_monitor;
              submitAndAdvance(values, needsAnchors ? "anchors" : "connect");
            }}
          />
        )}

        {step === "anchors" && (
          <AnchorsStep
            hasPowerMeter={profile.has_power_meter}
            hasHrMonitor={profile.has_hr_monitor}
            initialFtp={profile.ftp_watts}
            initialLthr={profile.lthr}
            onNext={(values) => submitAndAdvance(values, "connect")}
          />
        )}

        {step === "connect" && <ConnectStep onNext={() => setStep("summary")} />}

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
