import type { Lap } from "../api/types";

interface Props {
  laps: Lap[];
}

function fmt(min: number) {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  const s = Math.round((min * 60) % 60);
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function LapTable({ laps }: Props) {
  if (laps.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-100">
          <tr>
            <th className="text-left px-3 py-2 font-medium text-gray-500">Lap</th>
            <th className="text-right px-3 py-2 font-medium text-gray-500">Dist</th>
            <th className="text-right px-3 py-2 font-medium text-gray-500">Time</th>
            <th className="text-right px-3 py-2 font-medium text-gray-500">Avg HR</th>
            <th className="text-right px-3 py-2 font-medium text-gray-500">Speed</th>
            <th className="text-right px-3 py-2 font-medium text-gray-500">↑ m</th>
            <th className="text-right px-3 py-2 font-medium text-gray-500">GAP</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {laps.map((lap) => (
            <tr key={lap.lap_index} className="hover:bg-gray-50">
              <td className="px-3 py-2 text-gray-500">{lap.lap_index + 1}</td>
              <td className="px-3 py-2 text-right">{lap.distance_km} km</td>
              <td className="px-3 py-2 text-right">{fmt(lap.duration_min)}</td>
              <td className="px-3 py-2 text-right">{lap.avg_hr ?? "—"}</td>
              <td className="px-3 py-2 text-right">
                {lap.avg_speed_kmh != null ? `${lap.avg_speed_kmh} km/h` : "—"}
              </td>
              <td className="px-3 py-2 text-right">{lap.elev_gain_m}</td>
              <td className="px-3 py-2 text-right">
                {lap.gap_speed_kmh != null ? `${lap.gap_speed_kmh} km/h` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
