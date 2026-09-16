import { useState } from "react";

interface Props {
  initialRides: number;
  initialHours: number;
  onNext: (values: { weekly_rides: number; weekly_hours: number }) => void;
}

export default function VolumeStep({ initialRides, initialHours, onNext }: Props) {
  const [rides, setRides] = useState(initialRides || 3);
  const [hours, setHours] = useState(initialHours || 5);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">How much do you ride now?</h2>
        <p className="text-neutral-500 text-sm">
          Rough numbers are fine — we'll refine this from your actual rides later.
        </p>
      </div>

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

      <button
        onClick={() => onNext({ weekly_rides: rides, weekly_hours: hours })}
        className="w-full rounded-md bg-neutral-900 py-2 text-white font-medium"
      >
        Next
      </button>
    </div>
  );
}
