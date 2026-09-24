import { useState } from "react";

import AvailabilityPicker, { type AvailabilityValue } from "../AvailabilityPicker";

interface Props {
  initialHours: number;
  initialAvailability: AvailabilityValue;
  onNext: (
    values: {
      weekly_hours: number;
    } & AvailabilityValue,
  ) => void;
}

export default function HabitsStep({
  initialHours,
  initialAvailability,
  onNext,
}: Props) {
  const [hours, setHours] = useState(initialHours ? String(initialHours) : "");
  const [availability, setAvailability] = useState<AvailabilityValue>(initialAvailability);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">How do you ride now?</h2>
        <p className="text-neutral-500 text-sm">
          Rough numbers are fine — we'll refine this from your actual rides later.
        </p>
      </div>

      <div className="max-w-xs">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Hours per week</span>
          <input
            type="number"
            min={0}
            step={0.5}
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>

      <AvailabilityPicker value={availability} onChange={setAvailability} />

      <button
        onClick={() => onNext({ weekly_hours: Number(hours), ...availability })}
        className="primary-button w-full"
      >
        Next
      </button>
    </div>
  );
}
