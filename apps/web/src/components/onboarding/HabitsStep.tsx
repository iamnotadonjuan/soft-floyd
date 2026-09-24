import { useState } from "react";

import { useI18n } from "../../i18n/I18nProvider";
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
  const { m } = useI18n();
  const [hours, setHours] = useState(initialHours ? String(initialHours) : "");
  const [availability, setAvailability] = useState<AvailabilityValue>(initialAvailability);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{m.onboarding.habits.title}</h2>
        <p className="text-neutral-500 text-sm">
          {m.onboarding.habits.body}
        </p>
      </div>

      <div className="max-w-xs">
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.fields.hoursPerWeek}</span>
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
        {m.common.next}
      </button>
    </div>
  );
}
