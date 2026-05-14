import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMonthlyCost } from "../api/client";
import type { MonthlyCost } from "../api/types";

export default function Nav() {
  const [cost, setCost] = useState<MonthlyCost | null>(null);

  useEffect(() => {
    getMonthlyCost()
      .then(setCost)
      .catch(() => {});
  }, []);

  return (
    <nav className="bg-white border-b border-gray-200 px-4 py-3">
      <div className="mx-auto max-w-7xl flex items-center justify-between">
        <Link to="/activities" className="text-xl font-bold text-indigo-600 tracking-tight">
          🚴 Soft Floyd
        </Link>
        <div className="flex items-center gap-6">
          <Link
            to="/activities"
            className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            Activities
          </Link>
          {cost && (
            <span className="text-xs text-gray-400">
              ${cost.total_cost_usd.toFixed(2)} / $10 this month
            </span>
          )}
        </div>
      </div>
    </nav>
  );
}
