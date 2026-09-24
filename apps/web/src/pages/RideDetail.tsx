import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ActivityDetailOut } from "../api/types";
import { rideDate, rideDistance, rideDuration, rideTitle } from "../components/activityFormat";
import LanguageToggle from "../components/LanguageToggle";
import { useI18n } from "../i18n/I18nProvider";

export default function RideDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const { m, intlLocale } = useI18n();
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
          <span className="brand">{m.dashboard.brand}</span>
          <div className="flex items-center gap-4">
            <button className="text-button" onClick={onBack}>{m.common.backToRides}</button>
            <LanguageToggle />
          </div>
        </div>
        {error && <div className="notice-error" role="alert">{m.rideDetail.loadError(error)}</div>}
        {!ride && !error && <p className="body-muted">{m.rideDetail.loading}</p>}
        {ride && (
          <>
            <header className="mb-8">
              <p className="eyebrow mb-3">{rideDate(ride.start_time, intlLocale)}</p>
              <h1 className="display-title">{rideTitle(ride, m)}</h1>
              <p className="body-muted mt-3">{m.rideDetail.recordedBy(ride.is_indoor ? m.rides.indoor : m.rides.outdoor)}</p>
            </header>

            <section className="surface grid gap-5 p-5 sm:grid-cols-3 sm:p-7" aria-label={m.rideDetail.summaryAria}>
              <Stat label={m.rideDetail.distance} value={rideDistance(ride.distance_m, intlLocale)} />
              <Stat label={m.rideDetail.duration} value={rideDuration(ride.duration_s)} />
              <Stat label={m.rideDetail.elevationGain} value={`${Math.round(ride.elev_gain_m)} m`} />
              {ride.fit_status === "ok" && ride.sensors_present.includes("hr") && ride.avg_hr !== null &&
                <Stat label={m.rideDetail.avgHr} value={`${ride.avg_hr} bpm`} />}
              {ride.fit_status === "ok" && ride.sensors_present.includes("power") && ride.avg_power_w !== null &&
                <Stat label={m.rideDetail.avgPower} value={`${ride.avg_power_w} W`} />}
              {ride.fit_status === "ok" && ride.sensors_present.includes("cadence") && ride.avg_cadence !== null &&
                <Stat label={m.rideDetail.avgCadence} value={`${ride.avg_cadence} rpm`} />}
            </section>

            <section className="surface-soft mt-5 p-5">
              <h2 className="font-semibold text-[#30553c]">{m.rideDetail.recordedHeading}</h2>
              {ride.fit_status === "ok" ? (
                <p className="body-muted mt-1 text-sm">
                  {ride.sensors_present.length ? ride.sensors_present.join(" · ").toUpperCase() : m.rideDetail.noSensors}.
                  {" "}{m.rideDetail.onlyRecorded}
                </p>
              ) : (
                <p className="body-muted mt-1 text-sm">
                  {m.rideDetail.fitUnavailable}
                </p>
              )}
            </section>

            {ride.fit_status === "ok" && ride.laps.length > 0 && (
              <section className="mt-10" aria-labelledby="laps-heading">
                <h2 id="laps-heading" className="section-title mb-4">{m.rideDetail.laps}</h2>
                <div className="grid gap-3">
                  {ride.laps.map((lap) => (
                    <div className="surface flex flex-wrap items-center justify-between gap-3 p-4" key={lap.lap_index}>
                      <strong className="text-[#30553c]">{m.rideDetail.lap(lap.lap_index + 1)}</strong>
                      <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm body-muted">
                        <span>{rideDistance(lap.distance_m, intlLocale)}</span>
                        <span>{rideDuration(lap.duration_s)}</span>
                        <span>{m.rides.climbing(Math.round(lap.elev_gain_m))}</span>
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
