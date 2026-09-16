import { useState } from "react";

export interface SensorAnswers {
  has_power_meter: boolean;
  has_hr_monitor: boolean;
  has_cadence_sensor: boolean;
  has_speed_sensor: boolean;
}

interface Props {
  initial: SensorAnswers;
  onNext: (values: SensorAnswers) => void;
}

const SENSOR_OPTIONS: { key: keyof SensorAnswers; label: string; hint: string }[] = [
  { key: "has_power_meter", label: "Power meter", hint: "pedals, crank, or hub-based" },
  { key: "has_hr_monitor", label: "Heart rate monitor", hint: "chest strap or wrist-based" },
  { key: "has_cadence_sensor", label: "Cadence sensor", hint: "pedaling rate" },
  { key: "has_speed_sensor", label: "Speed sensor", hint: "wheel-mounted, separate from GPS" },
];

// The common Edge + strap setup, used when the rider isn't sure what they have.
const HR_ONLY_DEFAULT: SensorAnswers = {
  has_power_meter: false,
  has_hr_monitor: true,
  has_cadence_sensor: false,
  has_speed_sensor: false,
};

export default function SensorsStep({ initial, onNext }: Props) {
  const [sensors, setSensors] = useState<SensorAnswers>(initial);

  const toggle = (key: keyof SensorAnswers) =>
    setSensors((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">What do you ride with?</h2>
        <p className="text-neutral-500 text-sm">
          This decides which numbers we're honest enough to show you — see below.
        </p>
      </div>

      <div className="space-y-3">
        {SENSOR_OPTIONS.map(({ key, label, hint }) => (
          <label
            key={key}
            className="flex items-center gap-3 rounded-md border border-neutral-300 px-3 py-2"
          >
            <input
              type="checkbox"
              checked={sensors[key]}
              onChange={() => toggle(key)}
              className="h-4 w-4"
            />
            <span>
              <span className="font-medium">{label}</span>{" "}
              <span className="text-neutral-500 text-sm">— {hint}</span>
            </span>
          </label>
        ))}
      </div>

      <button
        onClick={() => onNext(HR_ONLY_DEFAULT)}
        className="w-full text-sm text-neutral-500 underline"
      >
        I'm not sure — assume heart rate monitor only
      </button>

      <button
        onClick={() => onNext(sensors)}
        className="w-full rounded-md bg-neutral-900 py-2 text-white font-medium"
      >
        Next
      </button>
    </div>
  );
}
