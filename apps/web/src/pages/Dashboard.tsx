import { useEffect, useState } from "react";

import { api } from "../api/client";
import type {
  ActivitySummaryOut, ConnectionOut, ProfileOut, TrainingLoadOut, TrainingSessionOut,
} from "../api/types";
import { rideDate, rideDistance, rideDuration, rideTitle } from "../components/activityFormat";
import LoadCard from "../components/LoadCard";
import { useI18n } from "../i18n/I18nProvider";

function connectionTone(status: ConnectionOut["status"]): string {
  if (status === "connected") return "good";
  if (status === "disconnected") return "neutral";
  if (status === "error") return "error";
  return "warning";
}

export default function Dashboard({
  profile, onOpenSettings, onOpenCoach, onOpenTraining, onOpenRide,
  showGuide, onDismissGuide, onOpenHelp,
}: {
  profile: ProfileOut;
  onOpenSettings: () => void;
  onOpenCoach: () => void;
  onOpenTraining: () => void;
  onOpenRide: (id: number) => void;
  showGuide: boolean;
  onDismissGuide: () => void;
  onOpenHelp: () => void;
}) {
  const { m, intlLocale } = useI18n();
  const [rides, setRides] = useState<ActivitySummaryOut[] | null>(null);
  const [connections, setConnections] = useState<ConnectionOut[] | null>(null);
  const [nextSession, setNextSession] = useState<TrainingSessionOut | null>(null);
  const [hasSession, setHasSession] = useState(false);
  const [load, setLoad] = useState<TrainingLoadOut | null>(null);
  const [rideError, setRideError] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);

  useEffect(() => {
    let active = true;
    api.listActivities()
      .then((page) => { if (active) { setRides(page); setHasMore(page.length === 20); } })
      .catch((reason) => { if (active) setRideError(String(reason)); });
    api.listConnections()
      .then((items) => { if (active) setConnections(items); })
      .catch((reason) => { if (active) setConnectionError(String(reason)); });
    api.listTrainingSessions()
      .then((items) => {
        if (!active) return;
        setHasSession(items.length > 0);
        const today = new Date().toISOString().slice(0, 10);
        const upcoming = items
          .filter((s) => s.status === "planned" && s.planned_date >= today)
          .sort((a, b) => a.planned_date.localeCompare(b.planned_date));
        setNextSession(upcoming[0] ?? null);
      })
      .catch(() => { /* the training card is optional on the dashboard */ });
    api.getTrainingLoad()
      .then((result) => { if (active) setLoad(result); })
      .catch(() => { /* the load card is optional too; it just doesn't render */ });
    return () => { active = false; };
  }, []);

  async function loadMore() {
    if (!rides?.length || loadingMore) return;
    setLoadingMore(true);
    setRideError(null);
    try {
      const page = await api.listActivities(rides[rides.length - 1]);
      setRides((current) => {
        const seen = new Set((current ?? []).map((ride) => ride.id));
        return [...(current ?? []), ...page.filter((ride) => !seen.has(ride.id))];
      });
      setHasMore(page.length === 20);
    } catch (reason) {
      setRideError(String(reason));
    } finally {
      setLoadingMore(false);
    }
  }

  // The coach needs a ride source to coach from; see docs/product-specs/coach-chat.md.
  const coachReady = connections?.some((c) => c.status === "connected") ?? false;
  const newest = rides?.[0];
  const history = rides?.slice(1) ?? [];

  return (
    <main className="app-shell">
      <div className="page-wrap">
        <section className="dashboard-hero mb-8 grid gap-8 lg:grid-cols-[1.4fr_1fr] lg:items-end">
          <svg className="hero-route" viewBox="0 0 570 360" fill="none" aria-hidden="true">
            <path d="M-34 294C72 281 38 155 160 189C260 217 246 51 356 99C444 138 444 202 605 -20" stroke="currentColor" strokeWidth="2" strokeDasharray="5 11" strokeLinecap="round" />
            <circle cx="356" cy="99" r="7" fill="currentColor" />
          </svg>
          <div className="relative z-10">
            <p className="eyebrow mb-3">{m.dashboard.eyebrow}</p>
            <h1 className="display-title">{m.dashboard.title}</h1>
            <p className="body-muted mt-4 max-w-xl text-lg">{m.dashboard.subtitle}</p>
            <div className="mt-7 flex flex-wrap gap-3">
              {connections !== null && !coachReady ? <>
                <button onClick={onOpenSettings} className="primary-button">{m.dashboard.connectGarmin}<span aria-hidden="true" className="ml-3">↗</span></button>
                <button onClick={onOpenTraining} className="secondary-button">{m.dashboard.planSession}</button>
              </> : <>
                <button onClick={onOpenTraining} className="primary-button">{m.dashboard.planSession}<span aria-hidden="true" className="ml-3">↗</span></button>
                <button onClick={onOpenCoach} className="secondary-button" disabled={!coachReady}
                  aria-describedby={coachReady ? undefined : "coach-hint"}>{m.dashboard.askCoach}</button>
              </>}
            </div>
            {connections !== null && !coachReady && <p id="coach-hint" className="body-muted mt-3 text-sm">{m.dashboard.coachHint}</p>}
          </div>
          <div className="goal-feature relative z-10 p-5 sm:p-7">
            <p className="eyebrow mb-2">{m.dashboard.goalEyebrow}</p>
            <p className="goal-feature-text text-2xl font-semibold leading-snug">{profile.goal_text}</p>
            <p className="body-muted mt-3 text-sm">{m.dashboard.weeklySummary(profile.weekly_rides, profile.weekly_hours)}{profile.primary_discipline ? ` · ${profile.primary_discipline}` : ""}</p>
            <span className="status-pill mt-4" data-tone="good">{m.dashboard.tierView[profile.capability_tier]}</span>
          </div>
        </section>

        {showGuide && <section className="surface first-use-guide mb-8 p-5 sm:p-7" aria-labelledby="first-use-heading">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow mb-2">{m.help.eyebrow}</p>
              <h2 id="first-use-heading" className="section-title">{m.help.guideTitle}</h2>
              <p className="body-muted mt-2">{m.help.guideIntro}</p>
            </div>
            <button className="text-button text-sm" onClick={onDismissGuide}>{m.help.dismissGuide}</button>
          </div>
          <ol className="mt-6 grid gap-3 md:grid-cols-3">
            {([
              { copy: m.help.connect, ready: coachReady, action: onOpenSettings },
              { copy: { ...m.help.ride, action: newest ? m.dashboard.viewRide : m.help.connect.action }, ready: Boolean(newest), action: newest ? () => onOpenRide(newest.id) : onOpenSettings },
              { copy: m.help.session, ready: hasSession, action: onOpenTraining },
            ] as const).map((step, index) => <li key={step.copy.title} className="surface-soft p-5">
              <span className="eyebrow">0{index + 1}{step.ready ? ` · ${m.help.ready}` : ""}</span>
              <h3 className="mt-2 text-lg font-semibold">{step.copy.title}</h3>
              <p className="body-muted mt-2 text-sm">{step.copy.body}</p>
              <button className="text-button mt-4 text-sm" onClick={step.action}>{step.copy.action} →</button>
            </li>)}
          </ol>
          <button className="text-button mt-5 text-sm" onClick={onOpenHelp}>{m.help.moreHelp} →</button>
        </section>}

        <section className="connection-band mb-8 flex flex-wrap items-center justify-between gap-4 p-5" aria-label={m.dashboard.connectionsAria}>
          <div>
            <p className="eyebrow mb-1">{m.dashboard.connectedApps}</p>
            {connectionError ? <p className="text-sm text-red-700">{m.dashboard.connectionsError(connectionError)}</p> :
              connections === null ? <p className="body-muted text-sm">{m.dashboard.checkingConnections}</p> :
              connections.length === 0 ? <p className="body-muted text-sm">{m.common.noAppsYet}</p> :
              <div className="flex flex-wrap gap-2">
                {connections.map((connection) => <span key={connection.provider} className="status-pill" data-tone={connectionTone(connection.status)}>
                  {connection.display_name}: {m.dashboard.connectionStatus[connection.status]}
                </span>)}
              </div>}
          </div>
          <button onClick={onOpenSettings} className="text-button">{m.dashboard.manageConnections}</button>
        </section>

        {nextSession && (
          <button onClick={onOpenTraining} className="ride-tile surface mb-12 block w-full p-5 text-left">
            <span className="eyebrow">
              {m.dashboard.upcomingSessionEyebrow} ·{" "}
              {new Date(`${nextSession.planned_date}T00:00:00`).toLocaleDateString(intlLocale, { weekday: "short", month: "short", day: "numeric" })}
            </span>
            <span className="mt-2 block text-xl font-semibold text-[#243e2c]">{nextSession.workout.name}</span>
            <span className="mt-3 block text-sm font-semibold text-[#31563e]">{m.dashboard.viewSession}</span>
          </button>
        )}

        <section className="mb-12" aria-labelledby="latest-heading">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
            <div><p className="eyebrow mb-2">{m.dashboard.latestEyebrow}</p><h2 id="latest-heading" className="section-title">{m.dashboard.newestRide}</h2></div>
            {newest && <span className="body-muted text-sm">{rideDate(newest.start_time, intlLocale)}</span>}
          </div>
          {rides === null && !rideError && <div className="surface p-8 body-muted">{m.dashboard.loadingRides}</div>}
          {rides?.length === 0 && <div className="surface p-8">
            <h3 className="text-lg font-semibold">{m.dashboard.emptyTitle}</h3>
            <p className="body-muted mt-2">{m.dashboard.emptyBody}</p>
            <button onClick={onOpenSettings} className="primary-button mt-5">{m.dashboard.connectGarmin}</button>
          </div>}
          {newest && <RideTile ride={newest} onOpen={onOpenRide} featured />}
          {rideError && <div className="notice-error mt-3" role="alert">{m.dashboard.ridesError(rideError)}</div>}
        </section>

        {load && <LoadCard load={load} />}

        {rides !== null && rides.length > 1 && <section className="mt-12" aria-labelledby="history-heading">
          <p className="eyebrow mb-2">{m.dashboard.lookBack}</p>
          <h2 id="history-heading" className="section-title mb-5">{m.dashboard.rideHistory}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {history.map((ride) => <RideTile key={ride.id} ride={ride} onOpen={onOpenRide} />)}
          </div>
        </section>}
        {hasMore && <div className="mt-7 flex justify-center">
          <button className="secondary-button" disabled={loadingMore} onClick={loadMore}>
            {loadingMore ? m.dashboard.loadingMore : m.dashboard.showOlder}
          </button>
        </div>}
      </div>
    </main>
  );
}

function RideTile({ ride, onOpen, featured = false }: {
  ride: ActivitySummaryOut; onOpen: (id: number) => void; featured?: boolean;
}) {
  const { m, intlLocale } = useI18n();
  return <button id={`ride-${ride.id}`} onClick={() => onOpen(ride.id)} className={`ride-tile surface p-5 ${featured ? "ride-tile-featured sm:p-7" : ""}`}>
    <span className="eyebrow">{rideDate(ride.start_time, intlLocale)} · {ride.is_indoor ? m.rides.indoor : m.rides.outdoor}</span>
    <span className={`block font-semibold text-[#243e2c] ${featured ? "mt-3 text-2xl sm:text-3xl" : "mt-2 text-xl"}`}>{rideTitle(ride, m)}</span>
    <span className="body-muted mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm">
      <span>{rideDistance(ride.distance_m, intlLocale)}</span><span>{rideDuration(ride.duration_s)}</span><span>{m.rides.climbing(Math.round(ride.elev_gain_m))}</span>
    </span>
    <span className="mt-5 block text-sm font-semibold text-[#31563e]">{m.dashboard.viewRide}</span>
  </button>;
}
