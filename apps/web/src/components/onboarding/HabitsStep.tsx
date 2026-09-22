import { useState } from "react";

import AvailabilityPicker, { type AvailabilityValue } from "../AvailabilityPicker";

interface Props {
  initialRides: number;
  initialHours: number;
  initialAvailability: AvailabilityValue;
  onNext: (
    values: {
      weekly_rides: number;
      weekly_hours: number;
    } & AvailabilityValue,
  ) => void;
}

export default function HabitsStep({
  initialRides,
  initialHours,
  initialAvailability,
  onNext,
}: Props) {
  const [rides, setRides] = useState(initialRides || 3);
  const [hours, setHours] = useState(initialHours || 5);
  const [availability, setAvailability] = useState<AvailabilityValue>(initialAvailability);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">How do you ride now?</h2>
        <p className="text-neutral-500 text-sm">
          Rough numbers are fine — we'll refine this from your actual rides later.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Rides per week</span>
          <input
            type="number"
            min={0}
            value={rides}
            onChange={(e) => setRides(Number(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-sm font-medium">Hours per week</span>
          <input
            type="number"
            min={0}
            step={0.5}
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>

      <AvailabilityPicker value={availability} onChange={setAvailability} />

      <button
        onClick={() => onNext({ weekly_rides: rides, weekly_hours: hours, ...availability })}
        className="w-full rounded-md bg-neutral-900 py-2 text-white font-medium"
      >
        Next
      </button>
    </div>
  );
}
