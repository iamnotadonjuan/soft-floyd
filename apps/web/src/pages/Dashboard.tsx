import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ActivitySummaryOut, ConnectionOut, ProfileOut } from "../api/types";
import { rideDate, rideDistance, rideDuration, rideTitle } from "../components/activityFormat";

const TIER_LABEL: Record<ProfileOut["capability_tier"], string> = {
  power: "Power + available signals", hr: "Heart rate", cadence: "Cadence", basic: "GPS basics",
};

function connectionTone(status: ConnectionOut["status"]): string {
  if (status === "connected") return "good";
  if (status === "disconnected") return "neutral";
  if (status === "error") return "error";
  return "warning";
}

function connectionCopy(status: ConnectionOut["status"]): string {
  return {
    connected: "Connected", disconnected: "Not connected", reauth_required: "Sign in again",
    rate_limited: "Temporarily limited", error: "Needs attention",
  }[status];
}

export default function Dashboard({
  profile, onOpenSettings, onOpenCoach, onOpenRide,
}: {
  profile: ProfileOut;
  onOpenSettings: () => void;
  onOpenCoach: () => void;
  onOpenRide: (id: number) => void;
}) {
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
          <span className="brand">Soft Floyd / Ride journal</span>
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={onOpenCoach} className="primary-button" disabled={!coachReady}
              aria-describedby={coachReady ? undefined : "coach-hint"}>Ask your coach</button>
            <button onClick={onOpenSettings} className="secondary-button">Settings</button>
          </div>
          {connections !== null && !coachReady &&
            <p id="coach-hint" className="body-muted w-full text-right text-sm">Connect Garmin in Settings to unlock your coach.</p>}
        </header>

        <section className="mb-9 grid gap-6 lg:grid-cols-[1.5fr_1fr] lg:items-end">
          <div>
            <p className="eyebrow mb-3">Your cycling home</p>
            <h1 className="display-title">Ride with intention.</h1>
            <p className="body-muted mt-4 max-w-xl text-lg">Your goal, your equipment, and the rides you actually recorded—in one place.</p>
          </div>
          <div className="surface p-5 sm:p-6">
            <p className="eyebrow mb-2">What you’re riding toward</p>
            <p className="text-lg font-semibold leading-snug">{profile.goal_text}</p>
            <p className="body-muted mt-3 text-sm">{profile.weekly_rides} ride {profile.weekly_rides === 1 ? "day" : "days"} · {profile.weekly_hours} hours each week{profile.primary_discipline ? ` · ${profile.primary_discipline}` : ""}</p>
            <span className="status-pill mt-4" data-tone="good">{TIER_LABEL[profile.capability_tier]} view</span>
          </div>
        </section>

        <section className="surface-soft mb-12 flex flex-wrap items-center justify-between gap-4 p-5" aria-label="Connected apps status">
          <div>
            <p className="eyebrow mb-1">Connected apps</p>
            {connectionError ? <p className="text-sm text-red-700">Could not load connection status: {connectionError}</p> :
              connections === null ? <p className="body-muted text-sm">Checking connections…</p> :
              connections.length === 0 ? <p className="body-muted text-sm">No apps available yet.</p> :
              <div className="flex flex-wrap gap-2">
                {connections.map((connection) => <span key={connection.provider} className="status-pill" data-tone={connectionTone(connection.status)}>
                  {connection.display_name}: {connectionCopy(connection.status)}
                </span>)}
              </div>}
          </div>
          <button onClick={onOpenSettings} className="text-button">Manage connections →</button>
        </section>

        <section aria-labelledby="latest-heading">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
            <div><p className="eyebrow mb-2">The latest</p><h2 id="latest-heading" className="section-title">Your newest ride</h2></div>
            {newest && <span className="body-muted text-sm">{rideDate(newest.start_time)}</span>}
          </div>
          {rides === null && !rideError && <div className="surface p-8 body-muted">Loading your rides…</div>}
          {rides?.length === 0 && <div className="surface p-8">
            <h3 className="text-lg font-semibold">Your ride journal starts here.</h3>
            <p className="body-muted mt-2">Connect Garmin in Settings to sync new rides automatically. The first connection brings in the latest activity; older Garmin rides need a separate backfill.</p>
            <button onClick={onOpenSettings} className="primary-button mt-5">Connect Garmin</button>
          </div>}
          {newest && <RideTile ride={newest} onOpen={onOpenRide} featured />}
          {rideError && <div className="notice-error mt-3" role="alert">Could not load rides: {rideError}</div>}
        </section>

        {rides !== null && rides.length > 1 && <section className="mt-12" aria-labelledby="history-heading">
          <p className="eyebrow mb-2">Look back</p>
          <h2 id="history-heading" className="section-title mb-5">Ride history</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {history.map((ride) => <RideTile key={ride.id} ride={ride} onOpen={onOpenRide} />)}
          </div>
        </section>}
        {hasMore && <div className="mt-7 flex justify-center">
          <button className="secondary-button" disabled={loadingMore} onClick={loadMore}>
            {loadingMore ? "Loading rides…" : "Show older rides"}
          </button>
        </div>}
      </div>
    </main>
  );
}

function RideTile({ ride, onOpen, featured = false }: {
  ride: ActivitySummaryOut; onOpen: (id: number) => void; featured?: boolean;
}) {
  return <button id={`ride-${ride.id}`} onClick={() => onOpen(ride.id)} className={`ride-tile surface p-5 ${featured ? "sm:p-7" : ""}`}>
    <span className="eyebrow">{rideDate(ride.start_time)} · {ride.is_indoor ? "Indoor" : "Outdoor"}</span>
    <span className={`block font-semibold text-[#243e2c] ${featured ? "mt-3 text-2xl sm:text-3xl" : "mt-2 text-xl"}`}>{rideTitle(ride)}</span>
    <span className="body-muted mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm">
      <span>{rideDistance(ride.distance_m)}</span><span>{rideDuration(ride.duration_s)}</span><span>{Math.round(ride.elev_gain_m)} m climbing</span>
    </span>
    <span className="mt-5 block text-sm font-semibold text-[#31563e]">View ride →</span>
  </button>;
}
