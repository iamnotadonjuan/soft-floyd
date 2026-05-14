import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Brush,
  ResponsiveContainer,
} from "recharts";
import type { TimeseriesPoint } from "../api/types";

interface Props {
  data: TimeseriesPoint[];
}

function fmtTime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h${String(m).padStart(2, "0")}` : `${m}min`;
}

export default function Chart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
        No time-series data for this activity.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="t"
          tickFormatter={fmtTime}
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          yAxisId="hr"
          domain={["auto", "auto"]}
          tick={{ fontSize: 11, fill: "#ef4444" }}
          axisLine={false}
          tickLine={false}
          width={36}
        />
        <YAxis
          yAxisId="alt"
          orientation="right"
          domain={["auto", "auto"]}
          tick={{ fontSize: 11, fill: "#6366f1" }}
          axisLine={false}
          tickLine={false}
          width={40}
        />
        <Tooltip
          formatter={(v: number, name: string) =>
            name === "HR" ? [`${v} bpm`, name] : [`${v} m`, name]
          }
          labelFormatter={fmtTime}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
        <Line
          yAxisId="hr"
          type="monotone"
          dataKey="hr"
          name="HR"
          stroke="#ef4444"
          dot={false}
          strokeWidth={1.5}
          connectNulls
        />
        <Line
          yAxisId="alt"
          type="monotone"
          dataKey="alt"
          name="Elevation"
          stroke="#6366f1"
          dot={false}
          strokeWidth={1.5}
          connectNulls
        />
        <Brush dataKey="t" height={20} stroke="#e5e7eb" tickFormatter={fmtTime} />
      </LineChart>
    </ResponsiveContainer>
  );
}
