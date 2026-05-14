import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getActivity } from "../api/client";
import type { ActivityDetail as Detail, Metrics } from "../api/types";
import Chart from "../components/Chart";
import LapTable from "../components/LapTable";
import ChatPanel from "../components/ChatPanel";

const ZONE_COLORS = [
  "bg-sky-200",
  "bg-green-300",
  "bg-yellow-300",
  "bg-orange-400",
  "bg-red-500",
];

function ZoneBar({ metrics }: { metrics: Metrics | null }) {
  if (!metrics) return null;
  const zones = [
    metrics.time_in_z1_min ?? 0,
    metrics.time_in_z2_min ?? 0,
    metrics.time_in_z3_min ?? 0,
    metrics.time_in_z4_min ?? 0,
    metrics.time_in_z5_min ?? 0,
  ];
  const total = zones.reduce((a, b) => a + b, 0);
  if (total === 0) return null;
  return (
    <div className="mt-2">
      <div className="flex rounded-full overflow-hidden h-3">
        {zones.map((z, i) => (
          <div
            key={i}
            className={ZONE_COLORS[i]}
            style={{ width: `${(z / total) * 100}%` }}
            title={`Z${i + 1}: ${z.toFixed(0)} min`}
          />
        ))}
      </div>
      <div className="flex gap-2 mt-1">
        {zones.map((z, i) => (
          <span key={i} className="text-xs text-gray-400">
            Z{i + 1} {Math.round((z / total) * 100)}%
          </span>
        ))}
      </div>
    </div>
  );
}

function stat(label: string, value: string | number | null | undefined) {
  return (
    <div>
      <span className="text-xs text-gray-400 block">{label}</span>
      <span className="text-sm font-semibold text-gray-700">{value ?? "—"}</span>
    </div>
  );
}

export default function ActivityDetail() {
  const { id } = useParams<{ id: string }>();
  const activityId = parseInt(id!);
  const [activity, setActivity] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getActivity(activityId)
      .then(setActivity)
      .finally(() => setLoading(false));
  }, [activityId]);

  if (loading) {
    return <div className="text-center py-16 text-gray-400">Loading…</div>;
  }
  if (!activity) {
    return <div className="text-center py-16 text-red-400">Activity not found.</div>;
  }

  const m = activity.metrics;

  function fmt(min: number) {
    const h = Math.floor(min / 60);
    const mm = Math.round(min % 60);
    return h ? `${h}h${String(mm).padStart(2, "0")}` : `${mm}min`;
  }

  return (
    <div>
      {/* Breadcrumb */}
      <Link to="/activities" className="text-sm text-indigo-500 hover:underline">
        ← All activities
      </Link>

      {/* Header card */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 mt-3">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-800">
              {activity.date} &mdash;{" "}
              <span className="capitalize text-indigo-600">{activity.bike_type}</span>
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">
              {activity.sport} {activity.sub_sport ? `/ ${activity.sub_sport}` : ""}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-4 mt-4">
          {stat("Distance", `${activity.distance_km} km`)}
          {stat("Duration", fmt(activity.duration_min))}
          {stat("Elevation", `${activity.elev_gain_m} m`)}
          {stat("Avg HR", activity.avg_hr ? `${activity.avg_hr} bpm` : null)}
          {stat("Max HR", activity.max_hr ? `${activity.max_hr} bpm` : null)}
          {stat("TSS proxy", activity.tss_proxy)}
        </div>
        {m && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4 pt-4 border-t border-gray-50">
            {stat("Decoupling", m.decoupling_pct != null ? `${m.decoupling_pct.toFixed(1)}%` : null)}
            {stat("HR drift", m.hr_drift_pct != null ? `${m.hr_drift_pct.toFixed(1)}%` : null)}
            {stat("VAM", m.vam_best_20min != null ? `${Math.round(m.vam_best_20min)} m/h` : null)}
            {stat(
              "GAP",
              m.gap_normalized_mps != null
                ? `${(m.gap_normalized_mps * 3.6).toFixed(1)} km/h`
                : null,
            )}
          </div>
        )}
        <ZoneBar metrics={m} />
      </div>

      {/* Main layout: chart + laps (left) / chat (right) */}
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left column */}
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">HR &amp; Elevation</h2>
            <Chart data={activity.timeseries} />
          </div>
          {activity.laps.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <h2 className="text-sm font-semibold text-gray-700 mb-3">Laps</h2>
              <LapTable laps={activity.laps} />
            </div>
          )}
        </div>

        {/* Right column — chat */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex flex-col min-h-[500px]">
          <ChatPanel activityId={activityId} />
        </div>
      </div>
    </div>
  );
}
