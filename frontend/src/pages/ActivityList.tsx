import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { listActivities } from "../api/client";
import type { ActivitySummary } from "../api/types";

const BIKE_TYPES = ["all", "road", "mtb", "indoor", "other"] as const;
type BikeFilter = (typeof BIKE_TYPES)[number];

const CHIP_COLORS: Record<string, string> = {
  road: "bg-blue-100 text-blue-700",
  mtb: "bg-green-100 text-green-700",
  indoor: "bg-amber-100 text-amber-700",
  other: "bg-gray-100 text-gray-600",
};

function BikeChip({ type }: { type: string }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CHIP_COLORS[type] ?? CHIP_COLORS.other}`}>
      {type}
    </span>
  );
}

export default function ActivityList() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const filter = (params.get("bike_type") as BikeFilter) ?? "all";
  const page = parseInt(params.get("page") ?? "0");

  const [activities, setActivities] = useState<ActivitySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const PAGE_SIZE = 20;

  useEffect(() => {
    setLoading(true);
    listActivities({
      bike_type: filter === "all" ? undefined : filter,
      page,
      page_size: PAGE_SIZE,
    })
      .then((res) => {
        setActivities(res.activities);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [filter, page]);

  function setFilter(f: BikeFilter) {
    setParams({ bike_type: f === "all" ? "" : f, page: "0" });
  }

  function fmt(min: number) {
    const h = Math.floor(min / 60);
    const m = Math.round(min % 60);
    return h ? `${h}h${String(m).padStart(2, "0")}` : `${m}min`;
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div>
      {/* Filter chips */}
      <div className="flex gap-2 mb-4">
        {BIKE_TYPES.map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
              filter === t
                ? "bg-indigo-600 text-white"
                : "bg-white text-gray-600 border border-gray-200 hover:border-indigo-300"
            }`}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
        <span className="ml-auto text-sm text-gray-400 self-center">{total} rides</span>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading…</div>
        ) : activities.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No activities found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-500">Date</th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">Type</th>
                <th className="text-right px-4 py-3 font-medium text-gray-500">Dist</th>
                <th className="text-right px-4 py-3 font-medium text-gray-500">Time</th>
                <th className="text-right px-4 py-3 font-medium text-gray-500">↑ m</th>
                <th className="text-right px-4 py-3 font-medium text-gray-500">Avg HR</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {activities.map((a) => (
                <tr
                  key={a.id}
                  onClick={() => navigate(`/activities/${a.id}`)}
                  className="hover:bg-indigo-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 text-gray-700">{a.date}</td>
                  <td className="px-4 py-3">
                    <BikeChip type={a.bike_type} />
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700">{a.distance_km} km</td>
                  <td className="px-4 py-3 text-right text-gray-700">{fmt(a.duration_min)}</td>
                  <td className="px-4 py-3 text-right text-gray-700">{a.elev_gain_m}</td>
                  <td className="px-4 py-3 text-right text-gray-700">{a.avg_hr ?? "—"}</td>
                  <td className="px-4 py-3 text-right">
                    {a.analyzed && (
                      <span className="text-xs text-indigo-500 font-medium">✓ analyzed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-4">
          <button
            disabled={page === 0}
            onClick={() => setParams({ bike_type: filter === "all" ? "" : filter, page: String(page - 1) })}
            className="px-3 py-1 rounded border text-sm disabled:opacity-40"
          >
            ← Prev
          </button>
          <span className="px-3 py-1 text-sm text-gray-500">
            {page + 1} / {totalPages}
          </span>
          <button
            disabled={page + 1 >= totalPages}
            onClick={() => setParams({ bike_type: filter === "all" ? "" : filter, page: String(page + 1) })}
            className="px-3 py-1 rounded border text-sm disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
