import type { Weekday } from "../api/types";
import { useI18n } from "../i18n/I18nProvider";

export interface AvailabilityValue {
  available_days: Weekday[];
  weekday_max_minutes: number | null;
  weekend_max_minutes: number | null;
}

const DAYS: Weekday[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

interface Props {
  value: AvailabilityValue;
  onChange: (value: AvailabilityValue) => void;
}

export default function AvailabilityPicker({ value, onChange }: Props) {
  const { m } = useI18n();
  const toggleDay = (day: Weekday) => {
    const days = value.available_days.includes(day)
      ? value.available_days.filter((d) => d !== day)
      : [...value.available_days, day];
    onChange({ ...value, available_days: days });
  };

  return (
    <div className="space-y-3">
      <div>
        <span className="text-sm font-medium">{m.availability.whichDays}</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {DAYS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => toggleDay(key)}
              aria-pressed={value.available_days.includes(key)}
              className="choice-chip"
            >
              {m.availability.days[key]}
            </button>
          ))}
        </div>
        <p className="body-muted mt-2 text-sm">
          {value.available_days.length === 0
            ? m.availability.selectDays
            : m.availability.daysPerWeek(value.available_days.length)}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.availability.weekdayMax}</span>
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
          <span className="body-muted block text-xs">{m.availability.weekdayHint}</span>
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.availability.weekendMax}</span>
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
