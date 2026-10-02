import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "../api/client";
import type {
  BikeOut,
  ConnectionOut,
  Discipline,
  Feel,
  ProfileOut,
  SessionSetting,
  SessionRequestIn,
  SuggestionOut,
  Terrain,
  TrainingSessionOut,
  WorkoutDevice,
} from "../api/types";
import SessionFields from "../components/training/SessionFields";
import WorkoutCard from "../components/training/WorkoutCard";
import HelpDisclosure from "../components/HelpDisclosure";
import { rideDuration } from "../components/activityFormat";
import { useI18n } from "../i18n/I18nProvider";

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

const DEVICE_OPTIONS: WorkoutDevice[] = ["garmin", "wahoo", "zwift", "other"];

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
}

export default function Training({ profile, onProfileChange }: Props) {
  const { m, intlLocale } = useI18n();
  const [bikes, setBikes] = useState<BikeOut[] | null>(null);
  const [connections, setConnections] = useState<ConnectionOut[] | null>(null);
  const [sessions, setSessions] = useState<TrainingSessionOut[] | null>(null);
  const [active, setActive] = useState<TrainingSessionOut | null>(null);
  const [suggestion, setSuggestion] = useState<SuggestionOut | null>(null);
  const [restRequest, setRestRequest] = useState<SessionRequestIn | null>(null);
  const [planningEasyRide, setPlanningEasyRide] = useState(false);
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

  async function planEasyRide() {
    if (!restRequest) return;
    setPlanningEasyRide(true);
    setLoadError(null);
    try {
      const created = await api.planTrainingSession({
        ...restRequest, feel: "tired", route_idea: "easy recovery ride",
      });
      setActive(created);
      setSuggestion(null);
      setRestRequest(null);
      refreshSessions();
    } catch (e) {
      setLoadError(errorText(e));
    } finally {
      setPlanningEasyRide(false);
    }
  }

  return (
    <main className="app-shell">
      <div className="page-wrap max-w-3xl">
        <div className="page-intro mb-8 max-w-2xl">
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
                setSuggestion(null);
                setRestRequest(null);
                refreshSessions();
              }}
              onSuggested={(result, request) => {
                setSuggestion(result);
                setRestRequest(result.kind === "rest" ? request : null);
                setActive(result.session);
                if (result.session) refreshSessions();
              }}
            />

            {suggestion && <section className="surface mt-8 space-y-4 p-5 sm:p-7" aria-label={m.training.suggestion.resultAria}>
              <div className="flex items-center gap-2">
                <h2 className="section-title">{suggestion.kind === "rest" ? m.training.suggestion.restTitle : m.training.suggestion.evidenceTitle}</h2>
                <HelpDisclosure title={m.training.suggestion.evidenceTitle}>{m.training.help.evidence}</HelpDisclosure>
              </div>
              {suggestion.kind === "rest" && <p className="body-muted">{suggestion.rationale}</p>}
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {suggestion.reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
              {suggestion.load_confidence !== "ok" && <p className="body-muted text-sm">{m.training.suggestion.limitedHistory(suggestion.days_of_history)}</p>}
              {suggestion.rides.length > 0 ? <div>
                <p className="text-sm font-semibold">{m.training.suggestion.recentRides(suggestion.rides.length)}</p>
                <ul className="mt-2 space-y-2">
                  {suggestion.rides.slice(0, 3).map((ride) => <li key={ride.activity_id} className="surface-soft p-3 text-sm">
                    <strong>{new Date(ride.start_time).toLocaleDateString(intlLocale, { month: "short", day: "numeric" })}</strong>
                    {` · ${rideDuration(ride.duration_s)} · ${m.rides.climbing(Math.round(ride.elev_gain_m))}`}
                    {ride.avg_hr !== null && ` · ${m.rideDetail.avgHr} ${ride.avg_hr} bpm`}
                    {ride.avg_power_w !== null && ` · ${m.rideDetail.avgPower} ${ride.avg_power_w} W`}
                    {ride.data_note && <p className="body-muted mt-1">{ride.data_note}</p>}
                  </li>)}
                </ul>
              </div> :
                <p className="body-muted text-sm">{m.training.suggestion.noRides}</p>}
              {suggestion.kind === "rest" && <>
                {suggestion.sources.length > 0 && <ul className="flex flex-wrap gap-2" aria-label={m.training.sourcesAria}>
                  {suggestion.sources.map((source) => <li key={`${source.book_id}-${source.page_start}`} className="status-pill" data-tone="neutral">
                    {source.title}, p.{source.page_start}
                  </li>)}
                </ul>}
                <button className="secondary-button" disabled={planningEasyRide} onClick={planEasyRide}>
                  {planningEasyRide ? m.training.form.building : m.training.suggestion.easyRide}
                </button>
              </>}
            </section>}

            {active && (
              <div className="mt-8">
                <WorkoutCard
                  session={active}
                  garminConnected={garminConnected}
                  onChange={(updated) => { setActive(updated); refreshSessions(); }}
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
    <div className="surface flow-panel training-form space-y-5 p-5 sm:p-8">
      <div>
        <div className="flex items-center gap-2"><h2 className="text-xl font-semibold">{m.training.devices.title}</h2>
          <HelpDisclosure title={m.training.devices.title}>{m.training.help.devices}</HelpDisclosure></div>
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
  profile, bikes, onCreated, onSuggested,
}: {
  profile: ProfileOut;
  bikes: BikeOut[];
  onCreated: (session: TrainingSessionOut) => void;
  onSuggested: (result: SuggestionOut, request: SessionRequestIn) => void;
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
  const [trainingArea, setTrainingArea] = useState("");
  const [terrain, setTerrain] = useState<Terrain | null>(null);
  const [startingAltitudeM, setStartingAltitudeM] = useState<number | "">("");
  const [mode, setMode] = useState<"idea" | "suggested">("idea");
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const defaultMinutes = useMemo(() => {
    const code = weekdayCode(plannedDate);
    const isWeekend = code === "sat" || code === "sun";
    return (isWeekend ? profile.weekend_max_minutes : profile.weekday_max_minutes) ?? 60;
  }, [plannedDate, profile.weekday_max_minutes, profile.weekend_max_minutes]);
  const [minutesOverride, setMinutesOverride] = useState<number | null>(null);
  const availableMinutes = minutesOverride ?? defaultMinutes;

  async function submit() {
    setBuilding(true);
    setError(null);
    try {
      const request: SessionRequestIn = {
        planned_date: plannedDate,
        available_minutes: availableMinutes,
        setting,
        discipline,
        bike_id: bikeId === "" ? null : bikeId,
        route_idea: mode === "idea" ? routeIdea : "",
        feel,
        training_area: setting === "outdoor" ? trainingArea : "",
        terrain: setting === "outdoor" ? terrain : null,
        starting_altitude_m: setting === "outdoor" && startingAltitudeM !== "" ? startingAltitudeM : null,
      };
      if (mode === "suggested") {
        onSuggested(await api.suggestTrainingSession(request), request);
      } else {
        onCreated(await api.planTrainingSession(request));
        setRouteIdea("");
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="surface training-form space-y-5 p-5 sm:p-7">
      <div>
        <div className="flex items-center gap-2"><h2 className="text-xl font-semibold">{m.training.suggestion.modeTitle}</h2>
          <HelpDisclosure title={m.training.suggestion.modeTitle}>{m.training.help.mode}</HelpDisclosure></div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="choice-chip" aria-pressed={mode === "idea"} onClick={() => setMode("idea")}>{m.training.suggestion.myIdea}</button>
          <button type="button" className="choice-chip" aria-pressed={mode === "suggested"} onClick={() => setMode("suggested")}>{m.training.suggestion.suggestForMe}</button>
        </div>
      </div>
      <SessionFields
        value={{ plannedDate, minutes: availableMinutes, setting, discipline, bikeId, routeIdea, feel, trainingArea, terrain, startingAltitudeM }}
        bikes={bikes}
        showIdea={mode === "idea"}
        onChange={(patch) => {
          if (patch.plannedDate !== undefined) setPlannedDate(patch.plannedDate);
          if (patch.minutes !== undefined) setMinutesOverride(patch.minutes);
          if (patch.setting !== undefined) setSetting(patch.setting);
          if (patch.discipline !== undefined) setDiscipline(patch.discipline);
          if (patch.bikeId !== undefined) setBikeId(patch.bikeId);
          if (patch.routeIdea !== undefined) setRouteIdea(patch.routeIdea);
          if (patch.feel !== undefined) setFeel(patch.feel);
          if (patch.trainingArea !== undefined) setTrainingArea(patch.trainingArea);
          if (patch.terrain !== undefined) setTerrain(patch.terrain);
          if (patch.startingAltitudeM !== undefined) setStartingAltitudeM(patch.startingAltitudeM);
        }}
      />

      {error && <p className="notice-error" role="alert">{m.training.planError(error)}</p>}

      <button className="primary-button" disabled={building} onClick={submit}>
        {building ? m.training.form.building : mode === "suggested" ? m.training.suggestion.suggestForMe : m.training.form.submit}
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
              {new Date(`${s.planned_date}T00:00:00`).toLocaleDateString(intlLocale, { month: "short", day: "numeric" })}
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
