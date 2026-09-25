import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "../api/client";
import type {
  BikeOut,
  ConnectionOut,
  Discipline,
  Feel,
  ProfileOut,
  SessionSetting,
  TrainingSessionOut,
  WorkoutDevice,
} from "../api/types";
import LanguageToggle from "../components/LanguageToggle";
import WorkoutCard from "../components/training/WorkoutCard";
import { useI18n } from "../i18n/I18nProvider";

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

const DEVICE_OPTIONS: WorkoutDevice[] = ["garmin", "wahoo", "zwift", "other"];
const DISCIPLINES: Discipline[] = ["road", "mtb", "gravel"];
const FEELS: Feel[] = ["fresh", "normal", "tired"];

function tomorrow(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

// A weekday code ("mon".."sun") for a date input's value, matching
// RiderProfile.available_days — see AvailabilityPicker.
function weekdayCode(dateStr: string): string {
  const codes = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
  return codes[new Date(`${dateStr}T00:00:00`).getDay()];
}

interface Props {
  profile: ProfileOut;
  onProfileChange: (profile: ProfileOut) => void;
  onBack: () => void;
}

export default function Training({ profile, onProfileChange, onBack }: Props) {
  const { m } = useI18n();
  const [bikes, setBikes] = useState<BikeOut[] | null>(null);
  const [connections, setConnections] = useState<ConnectionOut[] | null>(null);
  const [sessions, setSessions] = useState<TrainingSessionOut[] | null>(null);
  const [active, setActive] = useState<TrainingSessionOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.listBikes(), api.listConnections(), api.listTrainingSessions()])
      .then(([b, c, s]) => {
        if (cancelled) return;
        setBikes(b);
        setConnections(c);
        setSessions(s);
      })
      .catch((e) => { if (!cancelled) setLoadError(errorText(e)); });
    return () => { cancelled = true; };
  }, []);

  const garminConnected = connections?.some((c) => c.provider === "garmin" && c.status === "connected") ?? false;

  function refreshSessions() {
    api.listTrainingSessions().then(setSessions).catch((e) => setLoadError(errorText(e)));
  }

  const upcoming = sessions?.filter((s) => s.status === "planned") ?? [];
  const past = sessions?.filter((s) => s.status !== "planned") ?? [];

  return (
    <main className="app-shell">
      <div className="page-wrap max-w-3xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <span className="brand">{m.training.brand}</span>
          <div className="flex items-center gap-4">
            <button onClick={onBack} className="text-button">{m.training.backToDashboard}</button>
            <LanguageToggle />
          </div>
        </header>

        <div className="mb-8 max-w-2xl">
          <p className="eyebrow mb-3">{m.training.eyebrow}</p>
          <h1 className="display-title">{m.training.title}</h1>
          <p className="body-muted mt-4">{m.training.intro}</p>
        </div>

        {loadError && <p className="notice-error mb-6" role="alert">{loadError}</p>}

        {profile.workout_devices.length === 0 ? (
          <DevicesStep onProfileChange={onProfileChange} />
        ) : (
          <>
            <PlanForm
              profile={profile}
              bikes={bikes ?? []}
              onCreated={(created) => {
                setActive(created);
                refreshSessions();
              }}
            />

            {active && (
              <div className="mt-8">
                <WorkoutCard
                  session={active}
                  garminConnected={garminConnected}
                  onChange={setActive}
                  onDeleted={() => { setActive(null); refreshSessions(); }}
                />
              </div>
            )}

            <SessionList
              heading={m.training.upcomingHeading}
              sessions={upcoming}
              activeId={active?.id ?? null}
              onSelect={setActive}
            />
            <SessionList
              heading={m.training.historyHeading}
              sessions={past}
              activeId={active?.id ?? null}
              onSelect={setActive}
            />
          </>
        )}
      </div>
    </main>
  );
}

function DevicesStep({
  onProfileChange,
}: {
  onProfileChange: (profile: ProfileOut) => void;
}) {
  const { m } = useI18n();
  const [selected, setSelected] = useState<WorkoutDevice[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(device: WorkoutDevice) {
    setSelected((items) => (items.includes(device) ? items.filter((d) => d !== device) : [...items, device]));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      onProfileChange(await api.updateProfile({ workout_devices: selected }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="surface flow-panel space-y-5 p-5 sm:p-8">
      <div>
        <h2 className="text-xl font-semibold">{m.training.devices.title}</h2>
        <p className="body-muted mt-1 text-sm">{m.training.devices.body}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {DEVICE_OPTIONS.map((device) => (
          <button
            key={device}
            type="button"
            onClick={() => toggle(device)}
            aria-pressed={selected.includes(device)}
            className="choice-chip"
          >
            {m.training.devices[device]}
          </button>
        ))}
      </div>
      {error && <p className="notice-error" role="alert">{error}</p>}
      <button className="primary-button" disabled={selected.length === 0 || saving} onClick={save}>
        {m.training.devices.continue}
      </button>
    </div>
  );
}

function PlanForm({
  profile, bikes, onCreated,
}: {
  profile: ProfileOut;
  bikes: BikeOut[];
  onCreated: (session: TrainingSessionOut) => void;
}) {
  const { m } = useI18n();
  const [plannedDate, setPlannedDate] = useState(tomorrow());
  const [setting, setSetting] = useState<SessionSetting>("outdoor");
  const [discipline, setDiscipline] = useState<Discipline>(
    (profile.primary_discipline as Discipline) || "road"
  );
  const [bikeId, setBikeId] = useState<number | "">("");
  const [routeIdea, setRouteIdea] = useState("");
  const [feel, setFeel] = useState<Feel>("normal");
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const defaultMinutes = useMemo(() => {
    const code = weekdayCode(plannedDate);
    const isWeekend = code === "sat" || code === "sun";
    return (isWeekend ? profile.weekend_max_minutes : profile.weekday_max_minutes) ?? 60;
  }, [plannedDate, profile.weekday_max_minutes, profile.weekend_max_minutes]);
  const [minutesOverride, setMinutesOverride] = useState<number | null>(null);
  const availableMinutes = minutesOverride ?? defaultMinutes;

  const matchingBikes = bikes.filter((b) => (setting === "indoor" ? b.kind === "indoor" : b.kind === discipline));

  async function submit() {
    setBuilding(true);
    setError(null);
    try {
      const created = await api.planTrainingSession({
        planned_date: plannedDate,
        available_minutes: availableMinutes,
        setting,
        discipline,
        bike_id: bikeId === "" ? null : bikeId,
        route_idea: routeIdea,
        feel,
      });
      onCreated(created);
      setRouteIdea("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="surface space-y-5 p-5 sm:p-7">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.training.form.dateLabel}</span>
          <input
            type="date"
            value={plannedDate}
            onChange={(e) => setPlannedDate(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.training.form.minutesLabel}</span>
          <input
            type="number"
            min={10}
            max={600}
            value={availableMinutes}
            onChange={(e) => setMinutesOverride(Number(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>

      <div>
        <span className="text-sm font-medium">{m.training.form.settingLabel}</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {(["outdoor", "indoor"] as SessionSetting[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setSetting(key)}
              aria-pressed={setting === key}
              className="choice-chip"
            >
              {m.training.form[key]}
            </button>
          ))}
        </div>
      </div>

      <div>
        <span className="text-sm font-medium">{m.training.form.disciplineLabel}</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {DISCIPLINES.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setDiscipline(key)}
              aria-pressed={discipline === key}
              className="choice-chip"
            >
              {m.bikes.kinds[key]}
            </button>
          ))}
        </div>
      </div>

      {matchingBikes.length > 1 && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.training.form.bikeLabel}</span>
          <select
            value={bikeId}
            onChange={(e) => setBikeId(e.target.value === "" ? "" : Number(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          >
            <option value="" />
            {matchingBikes.map((b) => (
              <option key={b.id} value={b.id}>{b.nickname || m.bikes.kinds[b.kind as Discipline]}</option>
            ))}
          </select>
        </label>
      )}

      <label className="block space-y-1">
        <span className="text-sm font-medium">{m.training.form.ideaLabel}</span>
        <textarea
          value={routeIdea}
          onChange={(e) => setRouteIdea(e.target.value)}
          rows={2}
          placeholder={m.training.form.ideaPlaceholder}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>

      <div>
        <span className="text-sm font-medium">{m.training.form.feelLabel}</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {FEELS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setFeel(key)}
              aria-pressed={feel === key}
              className="choice-chip"
            >
              {m.training.form[key]}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="notice-error" role="alert">{m.training.planError(error)}</p>}

      <button className="primary-button" disabled={building} onClick={submit}>
        {building ? m.training.form.building : m.training.form.submit}
      </button>
    </div>
  );
}

function SessionList({
  heading, sessions, activeId, onSelect,
}: {
  heading: string;
  sessions: TrainingSessionOut[];
  activeId: number | null;
  onSelect: (session: TrainingSessionOut) => void;
}) {
  const { m, intlLocale } = useI18n();
  if (sessions.length === 0) return null;
  return (
    <section className="mt-10">
      <h2 className="section-title mb-4">{heading}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {sessions.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s)}
            className={`ride-tile surface p-4 text-left ${activeId === s.id ? "ring-2 ring-[#31563e]" : ""}`}
          >
            <span className="eyebrow">
              {new Date(s.planned_date).toLocaleDateString(intlLocale, { month: "short", day: "numeric" })}
            </span>
            <span className="mt-1 block font-semibold">{s.workout.name}</span>
            <span className="status-pill mt-2" data-tone={s.status === "done" ? "good" : s.status === "skipped" ? "neutral" : "warning"}>
              {m.training.status[s.status]}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
