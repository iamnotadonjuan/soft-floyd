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
import LanguageToggle from "../components/LanguageToggle";
import { useI18n } from "../i18n/I18nProvider";

type Step = "habits" | "goals" | "garage" | "about" | "anchors" | "connect" | "summary";

const STEP_ORDER: Step[] = ["habits", "goals", "garage", "about", "anchors", "connect", "summary"];

interface Props {
  initialProfile: ProfileOut;
  onComplete: (profile: ProfileOut) => void;
  onOpenProfile: () => void;
}

// Order follows docs/DESIGN.md: volume and goals before sensors, and
// never ask for a number the rider can't produce. See
// docs/product-specs/new-user-onboarding.md for the full flow.
export default function Onboarding({ initialProfile, onComplete, onOpenProfile }: Props) {
  const { m } = useI18n();
  const [step, setStep] = useState<Step>("habits");
  const [profile, setProfile] = useState<ProfileOut>(initialProfile);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const steps = (profile.has_power_meter || profile.has_hr_monitor)
    ? STEP_ORDER : STEP_ORDER.filter((item) => item !== "anchors");
  const stepIndex = steps.indexOf(step);

  async function submitAndAdvance(patch: ProfileIn, next: Step) {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateProfile(patch);
      setProfile(updated);
      setStep(next);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setSaving(false);
    }
  }

  function goBack() {
    if (stepIndex > 0) {
      setError(null);
      setStep(steps[stepIndex - 1]);
    }
  }

  return (
    <main className="app-shell min-h-screen">
      <div className="page-wrap max-w-4xl">
        <header className="mb-10 flex flex-wrap items-center justify-between gap-4">
          <span className="brand">{m.onboarding.brand}</span>
          <div className="flex items-center gap-4">
            <span className="body-muted text-sm">{m.onboarding.tagline}</span>
            <button onClick={onOpenProfile} className="text-button">{m.auth.profile}</button>
            <LanguageToggle />
          </div>
        </header>
        <div className="mb-8 max-w-2xl">
          <p className="eyebrow mb-3">{m.onboarding.eyebrow}</p>
          <h1 className="display-title">{m.onboarding.title}</h1>
        </div>
        <div className="surface flow-panel mx-auto max-w-2xl p-5 sm:p-8">

        {step !== "summary" && (
          <div className="mb-6">
            <p className="eyebrow mb-2">
              {m.onboarding.stepOf(stepIndex + 1, steps.length - 1)}
            </p>
            <div className="h-1.5 w-full rounded-full bg-[#e7ebe2]" role="progressbar" aria-valuenow={stepIndex + 1} aria-valuemin={1} aria-valuemax={steps.length - 1} aria-label={m.onboarding.progressAria}>
              <div
                className="h-1.5 rounded-full bg-[#30553c] transition-all"
                style={{
                  width: `${((stepIndex + 1) / (steps.length - 1)) * 100}%`,
                }}
              />
            </div>
          </div>
        )}
        {error && <div className="notice-error mb-5" role="alert">{m.onboarding.saveError(error)}</div>}
        {saving && <p className="body-muted mb-4 text-sm" role="status">{m.onboarding.savingAnswers}</p>}

        {step === "habits" && (
          <HabitsStep
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
              setSaving(true);
              setError(null);
              try {
                const refreshed = await api.getProfile();
                setProfile(refreshed);
                setStep("about");
              } catch (reason) {
                setError(String(reason));
              } finally {
                setSaving(false);
              }
            }}
          />
        )}

        {step === "about" && (
          <AboutYouStep
            initial={{
              has_hr_monitor: profile.has_hr_monitor,
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
              const needsAnchors = profile.has_power_meter || values.has_hr_monitor;
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
            <div><p className="eyebrow mb-2">{m.onboarding.readyEyebrow}</p><h2 className="section-title">{m.onboarding.readyTitle}</h2><p className="body-muted mt-2 text-sm">{m.onboarding.readyBody}</p></div>
            <CapabilitySummary profile={profile} />
            <button
              onClick={() => onComplete(profile)}
              className="primary-button w-full"
            >
              {m.onboarding.goToDashboard}
            </button>
          </div>
        )}
        {stepIndex > 0 && <button type="button" onClick={goBack} disabled={saving} className="text-button mt-6 text-sm">{m.common.back}</button>}
        </div>
      </div>
    </main>
  );
}
