import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ActivitySummaryOut, ConnectionOut, ProfileOut } from "../api/types";
import { rideDate, rideDistance, rideDuration, rideTitle } from "../components/activityFormat";
import LanguageToggle from "../components/LanguageToggle";
import { useI18n } from "../i18n/I18nProvider";

function connectionTone(status: ConnectionOut["status"]): string {
  if (status === "connected") return "good";
  if (status === "disconnected") return "neutral";
  if (status === "error") return "error";
  return "warning";
}

export default function Dashboard({
  profile, onOpenSettings, onOpenProfile, onOpenCoach, onOpenRide,
}: {
  profile: ProfileOut;
  onOpenSettings: () => void;
  onOpenProfile: () => void;
  onOpenCoach: () => void;
  onOpenRide: (id: number) => void;
}) {
  const { m, intlLocale } = useI18n();
  const [rides, setRides] = useState<ActivitySummaryOut[] | null>(null);
  const [connections, setConnections] = useState<ConnectionOut[] | null>(null);
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
        <header className="mb-12 flex flex-wrap items-start justify-between gap-4">
          <span className="brand">{m.dashboard.brand}</span>
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={onOpenCoach} className="primary-button" disabled={!coachReady}
              aria-describedby={coachReady ? undefined : "coach-hint"}>{m.dashboard.askCoach}</button>
            <button onClick={onOpenSettings} className="secondary-button">{m.dashboard.settings}</button>
            <button onClick={onOpenProfile} className="text-button">{m.auth.profile}</button>
            <LanguageToggle />
          </div>
          {connections !== null && !coachReady &&
            <p id="coach-hint" className="body-muted w-full text-right text-sm">{m.dashboard.coachHint}</p>}
        </header>

        <section className="mb-9 grid gap-6 lg:grid-cols-[1.5fr_1fr] lg:items-end">
          <div>
            <p className="eyebrow mb-3">{m.dashboard.eyebrow}</p>
            <h1 className="display-title">{m.dashboard.title}</h1>
            <p className="body-muted mt-4 max-w-xl text-lg">{m.dashboard.subtitle}</p>
          </div>
          <div className="surface p-5 sm:p-6">
            <p className="eyebrow mb-2">{m.dashboard.goalEyebrow}</p>
            <p className="text-lg font-semibold leading-snug">{profile.goal_text}</p>
            <p className="body-muted mt-3 text-sm">{m.dashboard.weeklySummary(profile.weekly_rides, profile.weekly_hours)}{profile.primary_discipline ? ` · ${profile.primary_discipline}` : ""}</p>
            <span className="status-pill mt-4" data-tone="good">{m.dashboard.tierView[profile.capability_tier]}</span>
          </div>
        </section>

        <section className="surface-soft mb-12 flex flex-wrap items-center justify-between gap-4 p-5" aria-label={m.dashboard.connectionsAria}>
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

        <section aria-labelledby="latest-heading">
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
  return <button id={`ride-${ride.id}`} onClick={() => onOpen(ride.id)} className={`ride-tile surface p-5 ${featured ? "sm:p-7" : ""}`}>
    <span className="eyebrow">{rideDate(ride.start_time, intlLocale)} · {ride.is_indoor ? m.rides.indoor : m.rides.outdoor}</span>
    <span className={`block font-semibold text-[#243e2c] ${featured ? "mt-3 text-2xl sm:text-3xl" : "mt-2 text-xl"}`}>{rideTitle(ride, m)}</span>
    <span className="body-muted mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm">
      <span>{rideDistance(ride.distance_m, intlLocale)}</span><span>{rideDuration(ride.duration_s)}</span><span>{m.rides.climbing(Math.round(ride.elev_gain_m))}</span>
    </span>
    <span className="mt-5 block text-sm font-semibold text-[#31563e]">{m.dashboard.viewRide}</span>
  </button>;
}
