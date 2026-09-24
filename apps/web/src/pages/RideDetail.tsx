import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ActivityDetailOut } from "../api/types";
import { rideDate, rideDistance, rideDuration, rideTitle } from "../components/activityFormat";

export default function RideDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const [ride, setRide] = useState<ActivityDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.getActivity(id)
      .then((result) => { if (active) setRide(result); })
      .catch((reason) => { if (active) setError(String(reason)); });
    return () => { active = false; };
  }, [id]);

  return (
    <main className="app-shell">
      <div className="page-wrap max-w-4xl">
        <div className="mb-10 flex flex-wrap items-center justify-between gap-4">
          <span className="brand">Soft Floyd / Ride journal</span>
          <button className="text-button" onClick={onBack}>← Back to rides</button>
        </div>
        {error && <div className="notice-error" role="alert">Could not load this ride: {error}</div>}
        {!ride && !error && <p className="body-muted">Loading ride…</p>}
        {ride && (
          <>
            <header className="mb-8">
              <p className="eyebrow mb-3">{rideDate(ride.start_time)}</p>
              <h1 className="display-title">{rideTitle(ride)}</h1>
              <p className="body-muted mt-3">Recorded by Garmin · {ride.is_indoor ? "Indoor" : "Outdoor"}</p>
            </header>

            <section className="surface grid gap-5 p-5 sm:grid-cols-3 sm:p-7" aria-label="Ride summary">
              <Stat label="Distance" value={rideDistance(ride.distance_m)} />
              <Stat label="Duration" value={rideDuration(ride.duration_s)} />
              <Stat label="Elevation gain" value={`${Math.round(ride.elev_gain_m)} m`} />
              {ride.fit_status === "ok" && ride.sensors_present.includes("hr") && ride.avg_hr !== null &&
                <Stat label="Average heart rate" value={`${ride.avg_hr} bpm`} />}
              {ride.fit_status === "ok" && ride.sensors_present.includes("power") && ride.avg_power_w !== null &&
                <Stat label="Average power" value={`${ride.avg_power_w} W`} />}
              {ride.fit_status === "ok" && ride.sensors_present.includes("cadence") && ride.avg_cadence !== null &&
                <Stat label="Average cadence" value={`${ride.avg_cadence} rpm`} />}
            </section>

            <section className="surface-soft mt-5 p-5">
              <h2 className="font-semibold text-[#30553c]">What this ride recorded</h2>
              {ride.fit_status === "ok" ? (
                <p className="body-muted mt-1 text-sm">
                  {ride.sensors_present.length ? ride.sensors_present.join(" · ").toUpperCase() : "No sensor streams detected"}.
                  Only recorded signals appear above and in the laps below.
                </p>
              ) : (
                <p className="body-muted mt-1 text-sm">
                  The FIT file was unavailable or could not be read. Distance, time, and elevation come from the Garmin summary; sensor readings cannot be verified for this ride.
                </p>
              )}
            </section>

            {ride.fit_status === "ok" && ride.laps.length > 0 && (
              <section className="mt-10" aria-labelledby="laps-heading">
                <h2 id="laps-heading" className="section-title mb-4">Laps</h2>
                <div className="grid gap-3">
                  {ride.laps.map((lap) => (
                    <div className="surface flex flex-wrap items-center justify-between gap-3 p-4" key={lap.lap_index}>
                      <strong className="text-[#30553c]">Lap {lap.lap_index + 1}</strong>
                      <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm body-muted">
                        <span>{rideDistance(lap.distance_m)}</span>
                        <span>{rideDuration(lap.duration_s)}</span>
                        <span>{Math.round(lap.elev_gain_m)} m climbing</span>
                        {ride.sensors_present.includes("hr") && lap.avg_hr !== null && <span>{lap.avg_hr} bpm</span>}
                        {ride.sensors_present.includes("power") && lap.avg_power_w !== null && <span>{lap.avg_power_w} W</span>}
                        {ride.sensors_present.includes("cadence") && lap.avg_cadence !== null && <span>{lap.avg_cadence} rpm</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div><p className="eyebrow mb-1">{label}</p><p className="text-2xl font-semibold text-[#243e2c]">{value}</p></div>;
}
