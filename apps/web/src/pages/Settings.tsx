import { type ReactNode, useState } from "react";

import { api } from "../api/client";
import type { ProfileOut, SelfRatedLevel, Weekday } from "../api/types";
import AvailabilityPicker, { type AvailabilityValue } from "../components/AvailabilityPicker";
import BikeEditor from "../components/BikeEditor";
import ConnectionsPanel from "../components/connections/ConnectionsPanel";
import FocusPicker from "../components/FocusPicker";

interface Props {
  profile: ProfileOut;
  onProfileChange: (profile: ProfileOut) => void;
  onBack: () => void;
}

const LEVEL_OPTIONS: { key: SelfRatedLevel; label: string }[] = [
  { key: "beginner", label: "Just starting out" },
  { key: "recreational", label: "Recreational" },
  { key: "enthusiast", label: "Enthusiast" },
  { key: "competitive", label: "Competitive / racing" },
];

function numberField(raw: string): number | null {
  return raw.trim() === "" ? null : Number(raw);
}

// Each section below owns its own fields and saves independently with a
// PUT /api/profile partial update — the same components (pickers,
// BikeEditor, ConnectionsPanel) onboarding walks as steps, here stacked
// as always-visible sections instead. See docs/FRONTEND.md.
export default function Settings({ profile, onProfileChange, onBack }: Props) {
  async function save(patch: Record<string, unknown>) {
    const updated = await api.updateProfile(patch);
    onProfileChange(updated);
    return updated;
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium tracking-wide text-neutral-400">SOFT FLOYD</p>
          <h1 className="text-2xl font-semibold">Settings</h1>
        </div>
        <button onClick={onBack} className="text-sm text-neutral-500 underline">
          Back to dashboard
        </button>
      </div>

      <div className="space-y-6">
        <HabitsSection profile={profile} save={save} />
        <GoalsSection profile={profile} save={save} />

        <SettingsSection title="Garage" description="Bikes and the sensors mounted on each one.">
          <BikeEditor onBikesChange={() => api.getProfile().then(onProfileChange)} />
        </SettingsSection>

        <AboutYouSection profile={profile} save={save} />
        <SensorsAndAnchorsSection profile={profile} save={save} />

        <SettingsSection
          title="Connected apps"
          description="Garmin today; other providers can be added the same way."
        >
          <ConnectionsPanel />
        </SettingsSection>
      </div>
    </div>
  );
}

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-4 rounded-md border border-neutral-200 p-4">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {description && <p className="text-sm text-neutral-500">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function SaveButton({ onSave }: { onSave: () => Promise<unknown> }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await onSave();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleClick}
        disabled={saving}
        className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
      >
        {saving ? "Saving…" : "Save"}
      </button>
      {saved && <span className="text-sm text-green-600">Saved</span>}
      {error && <span className="text-sm text-red-600">{error}</span>}
    </div>
  );
}

interface SectionProps {
  profile: ProfileOut;
  save: (patch: Record<string, unknown>) => Promise<ProfileOut>;
}

function HabitsSection({ profile, save }: SectionProps) {
  const [rides, setRides] = useState(profile.weekly_rides);
  const [hours, setHours] = useState(profile.weekly_hours);
  const [availability, setAvailability] = useState<AvailabilityValue>({
    available_days: profile.available_days as Weekday[],
    weekday_max_minutes: profile.weekday_max_minutes,
    weekend_max_minutes: profile.weekend_max_minutes,
  });

  return (
    <SettingsSection title="Habits" description="How much and when you ride.">
      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Rides per week</span>
          <input
            type="number"
            min={0}
            value={rides}
            onChange={(e) => setRides(Number(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Hours per week</span>
          <input
            type="number"
            min={0}
            step={0.5}
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>
      <AvailabilityPicker value={availability} onChange={setAvailability} />
      <SaveButton
        onSave={() => save({ weekly_rides: rides, weekly_hours: hours, ...availability })}
      />
    </SettingsSection>
  );
}

function GoalsSection({ profile, save }: SectionProps) {
  const [goal, setGoal] = useState(profile.goal_text);
  const [focusAreas, setFocusAreas] = useState<string[]>(profile.focus_areas);
  const [eventName, setEventName] = useState(profile.target_event_name ?? "");
  const [eventDate, setEventDate] = useState(profile.target_event_date ?? "");

  return (
    <SettingsSection title="Goals" description="What you're training for.">
      <FocusPicker value={focusAreas} onChange={setFocusAreas} />
      <label className="block space-y-1">
        <span className="text-sm font-medium">In your own words</span>
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          rows={3}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <input
          value={eventName}
          onChange={(e) => setEventName(e.target.value)}
          placeholder="Event name"
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
        <input
          type="date"
          value={eventDate}
          onChange={(e) => setEventDate(e.target.value)}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </div>
      <SaveButton
        onSave={() =>
          save({
            goal_text: goal,
            focus_areas: focusAreas,
            target_event_name: eventName.trim() === "" ? null : eventName,
            target_event_date: eventDate.trim() === "" ? null : eventDate,
          })
        }
      />
    </SettingsSection>
  );
}

function AboutYouSection({ profile, save }: SectionProps) {
  const [birthYear, setBirthYear] = useState(profile.birth_year);
  const [weightKg, setWeightKg] = useState(profile.weight_kg);
  const [maxHr, setMaxHr] = useState(profile.max_hr);
  const [yearsRiding, setYearsRiding] = useState(profile.years_riding);
  const [longestRide, setLongestRide] = useState(profile.longest_recent_ride_km);
  const [level, setLevel] = useState(profile.self_rated_level);
  const [followedPlan, setFollowedPlan] = useState(profile.followed_plan_before === true);
  const [healthNotes, setHealthNotes] = useState(profile.health_notes ?? "");

  return (
    <SettingsSection title="About you" description="Body and experience — all optional.">
      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Birth year</span>
          <input
            type="number"
            value={birthYear ?? ""}
            onChange={(e) => setBirthYear(numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Weight (kg)</span>
          <input
            type="number"
            step={0.1}
            value={weightKg ?? ""}
            onChange={(e) => setWeightKg(numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Max heart rate (bpm)</span>
          <input
            type="number"
            value={maxHr ?? ""}
            onChange={(e) => setMaxHr(numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Years riding</span>
          <input
            type="number"
            step={0.5}
            value={yearsRiding ?? ""}
            onChange={(e) => setYearsRiding(numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>
      <label className="block space-y-1">
        <span className="text-sm font-medium">Longest ride in the last few months (km)</span>
        <input
          type="number"
          value={longestRide ?? ""}
          onChange={(e) => setLongestRide(numberField(e.target.value))}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        {LEVEL_OPTIONS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setLevel(level === key ? null : key)}
            className={`rounded-full border px-3 py-1.5 text-sm ${
              level === key ? "border-neutral-900 bg-neutral-900 text-white" : "border-neutral-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={followedPlan}
          onChange={(e) => setFollowedPlan(e.target.checked)}
        />
        I've followed a structured training plan before
      </label>
      <label className="block space-y-1">
        <span className="text-sm font-medium">Anything to know — injuries, limits, etc.</span>
        <textarea
          value={healthNotes}
          onChange={(e) => setHealthNotes(e.target.value)}
          rows={2}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>
      <SaveButton
        onSave={() =>
          save({
            birth_year: birthYear,
            weight_kg: weightKg,
            max_hr: maxHr,
            years_riding: yearsRiding,
            longest_recent_ride_km: longestRide,
            self_rated_level: level,
            followed_plan_before: followedPlan,
            health_notes: healthNotes.trim() === "" ? null : healthNotes,
          })
        }
      />
    </SettingsSection>
  );
}

function SensorsAndAnchorsSection({ profile, save }: SectionProps) {
  const [hasHrMonitor, setHasHrMonitor] = useState(profile.has_hr_monitor);
  const [ftp, setFtp] = useState(profile.ftp_watts?.toString() ?? "");
  const [lthr, setLthr] = useState(profile.lthr?.toString() ?? "");

  return (
    <SettingsSection
      title="Heart rate & anchors"
      description="Power/cadence/speed sensors live per-bike in the garage above."
    >
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={hasHrMonitor}
          onChange={(e) => setHasHrMonitor(e.target.checked)}
        />
        I wear a heart rate monitor
      </label>

      {profile.has_power_meter && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">FTP (watts)</span>
          <input
            type="number"
            min={0}
            value={ftp}
            onChange={(e) => setFtp(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      )}

      {hasHrMonitor && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">Lactate threshold HR (bpm)</span>
          <input
            type="number"
            min={0}
            value={lthr}
            onChange={(e) => setLthr(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      )}

      <SaveButton
        onSave={() =>
          save({
            has_hr_monitor: hasHrMonitor,
            ftp_watts: ftp.trim() === "" ? null : Number(ftp),
            lthr: lthr.trim() === "" ? null : Number(lthr),
          })
        }
      />
    </SettingsSection>
  );
}
