import { useEffect, useState } from "react";
import { generateDailySummary, getDailySummary } from "../api/client";
import type { DailySummaryResponse } from "../api/types";

export default function DailyReadiness() {
  const [data, setData] = useState<DailySummaryResponse | null>(null);
  const [regen, setRegen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setData(await getDailySummary());
    } catch {
      setData(null);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const regenerate = async () => {
    setRegen(true);
    setError(null);
    try {
      await generateDailySummary();
      await load();
    } catch (err) {
      setError("Failed to regenerate: " + String(err));
    } finally {
      setRegen(false);
    }
  };

  if (!data) return null;

  return (
    <div className="mb-5 rounded-xl border border-blue-100 bg-blue-50 p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-blue-700">
          ☀️ Today's readiness · {data.date}
        </span>
        <button
          onClick={regenerate}
          disabled={regen}
          className="text-xs text-blue-400 hover:text-blue-700 disabled:opacity-40 transition-colors"
        >
          {regen ? "Regenerating…" : "Regenerate"}
        </button>
      </div>
      <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{data.text}</p>
      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
    </div>
  );
}
