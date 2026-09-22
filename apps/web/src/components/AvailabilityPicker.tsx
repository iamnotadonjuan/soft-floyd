import type { Weekday } from "../api/types";

export interface AvailabilityValue {
  available_days: Weekday[];
  weekday_max_minutes: number | null;
  weekend_max_minutes: number | null;
}

const DAYS: { key: Weekday; label: string }[] = [
  { key: "mon", label: "Mon" },
  { key: "tue", label: "Tue" },
  { key: "wed", label: "Wed" },
  { key: "thu", label: "Thu" },
  { key: "fri", label: "Fri" },
  { key: "sat", label: "Sat" },
  { key: "sun", label: "Sun" },
];

interface Props {
  value: AvailabilityValue;
  onChange: (value: AvailabilityValue) => void;
}

export default function AvailabilityPicker({ value, onChange }: Props) {
  const toggleDay = (day: Weekday) => {
    const days = value.available_days.includes(day)
      ? value.available_days.filter((d) => d !== day)
      : [...value.available_days, day];
    onChange({ ...value, available_days: days });
  };

  return (
    <div className="space-y-3">
      <div>
        <span className="text-sm font-medium">Which days can you usually ride?</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {DAYS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => toggleDay(key)}
              className={`rounded-full border px-3 py-1.5 text-sm ${
                value.available_days.includes(key)
                  ? "border-neutral-900 bg-neutral-900 text-white"
                  : "border-neutral-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Weekday max (minutes)</span>
          <input
            type="number"
            min={0}
            value={value.weekday_max_minutes ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                weekday_max_minutes: e.target.value === "" ? null : Number(e.target.value),
              })
            }
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Weekend max (minutes)</span>
          <input
            type="number"
            min={0}
            value={value.weekend_max_minutes ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                weekend_max_minutes: e.target.value === "" ? null : Number(e.target.value),
              })
            }
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>
    </div>
  );
}
