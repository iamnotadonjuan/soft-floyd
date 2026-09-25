import { type ReactNode, useState } from "react";

import { api } from "../api/client";
import type { ProfileOut, SelfRatedLevel, Weekday, WorkoutDevice } from "../api/types";
import AvailabilityPicker, { type AvailabilityValue } from "../components/AvailabilityPicker";
import BikeEditor from "../components/BikeEditor";
import ConnectionsPanel from "../components/connections/ConnectionsPanel";
import FocusPicker from "../components/FocusPicker";
import LanguageToggle from "../components/LanguageToggle";
import { useI18n } from "../i18n/I18nProvider";

interface Props {
  profile: ProfileOut;
  onProfileChange: (profile: ProfileOut) => void;
  onBack: () => void;
  onOpenProfile: () => void;
}

const LEVELS: SelfRatedLevel[] = ["beginner", "recreational", "enthusiast", "competitive"];
const DEVICES: WorkoutDevice[] = ["garmin", "wahoo", "zwift", "other"];

function numberField(raw: string): number | null {
  return raw.trim() === "" ? null : Number(raw);
}

// Each section below owns its own fields and saves independently with a
// PUT /api/profile partial update — the same components (pickers,
// BikeEditor, ConnectionsPanel) onboarding walks as steps, here stacked
// as always-visible sections instead. See docs/FRONTEND.md.
export default function Settings({ profile, onProfileChange, onBack, onOpenProfile }: Props) {
  const { m } = useI18n();
  async function save(patch: Record<string, unknown>) {
    const updated = await api.updateProfile(patch);
    onProfileChange(updated);
    return updated;
  }

  return (
    <main className="app-shell">
      <div className="page-wrap">
        <header className="mb-10 flex flex-wrap items-center justify-between gap-4">
          <span className="brand">{m.settings.brand}</span>
          <div className="flex items-center gap-4">
            <button onClick={onBack} className="text-button">{m.common.backToRides}</button>
            <button onClick={onOpenProfile} className="text-button">{m.auth.profile}</button>
            <LanguageToggle />
          </div>
        </header>
        <div className="mb-10 max-w-2xl">
          <p className="eyebrow mb-3">{m.settings.eyebrow}</p>
          <h1 className="display-title">{m.settings.title}</h1>
          <p className="body-muted mt-4">{m.settings.intro}</p>
        </div>
        <div className="settings-panel mx-auto max-w-3xl space-y-5">
          <HabitsSection profile={profile} save={save} />
          <GoalsSection profile={profile} save={save} />

          <SettingsSection title={m.settings.garage.title} description={m.settings.garage.description}>
            <BikeEditor onBikesChange={() => api.getProfile().then(onProfileChange)} />
          </SettingsSection>

          <AboutYouSection profile={profile} save={save} />
          <SensorsAndAnchorsSection profile={profile} save={save} />
          <DevicesSection profile={profile} save={save} />

          <SettingsSection title={m.settings.connections.title} description={m.settings.connections.description}>
            <ConnectionsPanel />
          </SettingsSection>
        </div>
      </div>
    </main>
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
    <section className="surface space-y-5 p-5 sm:p-7">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {description && <p className="body-muted mt-1 text-sm">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function SaveButton({ onSave }: { onSave: () => Promise<unknown> }) {
  const { m } = useI18n();
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
        className="primary-button"
      >
        {saving ? m.common.saving : m.common.save}
      </button>
      {saved && <span className="text-sm text-green-700" role="status">{m.common.saved}</span>}
      {error && <span className="notice-error" role="alert">{error}</span>}
    </div>
  );
}

interface SectionProps {
  profile: ProfileOut;
  save: (patch: Record<string, unknown>) => Promise<ProfileOut>;
}

function HabitsSection({ profile, save }: SectionProps) {
  const { m } = useI18n();
  const [hours, setHours] = useState(profile.weekly_hours ? String(profile.weekly_hours) : "");
  const [availability, setAvailability] = useState<AvailabilityValue>({
    available_days: profile.available_days as Weekday[],
    weekday_max_minutes: profile.weekday_max_minutes,
    weekend_max_minutes: profile.weekend_max_minutes,
  });

  return (
    <SettingsSection title={m.settings.habits.title} description={m.settings.habits.description}>
      <div className="max-w-xs">
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.fields.hoursPerWeek}</span>
          <input
            type="number"
            min={0}
            step={0.5}
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>
      <AvailabilityPicker value={availability} onChange={setAvailability} />
      <SaveButton
        onSave={() => save({ weekly_hours: Number(hours), ...availability })}
      />
    </SettingsSection>
  );
}

function GoalsSection({ profile, save }: SectionProps) {
  const { m } = useI18n();
  const [goal, setGoal] = useState(profile.goal_text);
  const [focusAreas, setFocusAreas] = useState<string[]>(profile.focus_areas);
  const [eventName, setEventName] = useState(profile.target_event_name ?? "");
  const [eventDate, setEventDate] = useState(profile.target_event_date ?? "");

  return (
    <SettingsSection title={m.settings.goals.title} description={m.settings.goals.description}>
      <FocusPicker value={focusAreas} onChange={setFocusAreas} />
      <label className="block space-y-1">
        <span className="text-sm font-medium">{m.fields.ownWords}</span>
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
          placeholder={m.fields.eventName}
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
  const { m } = useI18n();
  const [birthYear, setBirthYear] = useState(profile.birth_year);
  const [weightKg, setWeightKg] = useState(profile.weight_kg);
  const [maxHr, setMaxHr] = useState(profile.max_hr);
  const [yearsRiding, setYearsRiding] = useState(profile.years_riding);
  const [longestRide, setLongestRide] = useState(profile.longest_recent_ride_km);
  const [level, setLevel] = useState(profile.self_rated_level);
  const [followedPlan, setFollowedPlan] = useState(profile.followed_plan_before === true);
  const [healthNotes, setHealthNotes] = useState(profile.health_notes ?? "");

  return (
    <SettingsSection title={m.settings.about.title} description={m.settings.about.description}>
      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.fields.birthYear}</span>
          <input
            type="number"
            value={birthYear ?? ""}
            onChange={(e) => setBirthYear(numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.fields.weightKg}</span>
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
          <span className="text-sm font-medium">{m.fields.maxHr}</span>
          <input
            type="number"
            value={maxHr ?? ""}
            onChange={(e) => setMaxHr(numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.fields.yearsRiding}</span>
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
        <span className="text-sm font-medium">{m.fields.longestRide}</span>
        <input
          type="number"
          value={longestRide ?? ""}
          onChange={(e) => setLongestRide(numberField(e.target.value))}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        {LEVELS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setLevel(level === key ? null : key)}
            aria-pressed={level === key}
            className="choice-chip"
          >
            {m.levels[key]}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={followedPlan}
          onChange={(e) => setFollowedPlan(e.target.checked)}
        />
        {m.fields.followedPlan}
      </label>
      <label className="block space-y-1">
        <span className="text-sm font-medium">{m.fields.healthNotes}</span>
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
  const { m } = useI18n();
  const [hasHrMonitor, setHasHrMonitor] = useState(profile.has_hr_monitor);
  const [ftp, setFtp] = useState(profile.ftp_watts?.toString() ?? "");
  const [lthr, setLthr] = useState(profile.lthr?.toString() ?? "");

  return (
    <SettingsSection
      title={m.settings.anchors.title}
      description={m.settings.anchors.description}
    >
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={hasHrMonitor}
          onChange={(e) => setHasHrMonitor(e.target.checked)}
        />
        {m.settings.hrMonitor}
      </label>

      {profile.has_power_meter && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.fields.ftp}</span>
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
          <span className="text-sm font-medium">{m.fields.lthr}</span>
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

function DevicesSection({ profile, save }: SectionProps) {
  const { m } = useI18n();
  const [devices, setDevices] = useState<string[]>(profile.workout_devices);

  const toggle = (device: WorkoutDevice) =>
    setDevices((items) => (items.includes(device) ? items.filter((d) => d !== device) : [...items, device]));

  return (
    <SettingsSection title={m.settings.devices.title} description={m.settings.devices.description}>
      <div className="flex flex-wrap gap-2">
        {DEVICES.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => toggle(key)}
            aria-pressed={devices.includes(key)}
            className="choice-chip"
          >
            {m.training.devices[key]}
          </button>
        ))}
      </div>
      <SaveButton onSave={() => save({ workout_devices: devices })} />
    </SettingsSection>
  );
}
