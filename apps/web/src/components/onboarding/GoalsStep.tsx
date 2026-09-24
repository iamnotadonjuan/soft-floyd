import { useState } from "react";

import { useI18n } from "../../i18n/I18nProvider";
import FocusPicker from "../FocusPicker";

interface Props {
  initialGoal: string;
  initialFocusAreas: string[];
  initialTargetEventName: string | null;
  initialTargetEventDate: string | null;
  onNext: (values: {
    goal_text: string;
    focus_areas: string[];
    target_event_name: string | null;
    target_event_date: string | null;
  }) => void;
}

export default function GoalsStep({
  initialGoal,
  initialFocusAreas,
  initialTargetEventName,
  initialTargetEventDate,
  onNext,
}: Props) {
  const { m } = useI18n();
  const [goal, setGoal] = useState(initialGoal);
  const [focusAreas, setFocusAreas] = useState<string[]>(initialFocusAreas);
  const [eventName, setEventName] = useState(initialTargetEventName ?? "");
  const [eventDate, setEventDate] = useState(initialTargetEventDate ?? "");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{m.onboarding.goals.title}</h2>
        <p className="text-neutral-500 text-sm">
          {m.onboarding.goals.body}
        </p>
      </div>

      <FocusPicker value={focusAreas} onChange={setFocusAreas} />

      <label className="block space-y-1">
        <span className="text-sm font-medium">{m.fields.ownWords}</span>
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder={m.onboarding.goals.goalPlaceholder}
          rows={3}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>

      <div className="space-y-1">
        <span className="text-sm font-medium">{m.onboarding.goals.eventQuestion}</span>
        <div className="grid grid-cols-2 gap-3">
          <input
            value={eventName}
            onChange={(e) => setEventName(e.target.value)}
            placeholder={m.fields.eventName}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
          <input
            type="date"
            value={eventDate}
            onChange={(e) => setEventDate(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </div>
      </div>

      <button
        disabled={goal.trim().length === 0}
        onClick={() =>
          onNext({
            goal_text: goal,
            focus_areas: focusAreas,
            target_event_name: eventName.trim() === "" ? null : eventName,
            target_event_date: eventDate.trim() === "" ? null : eventDate,
          })
        }
        className="primary-button w-full"
      >
        {m.common.next}
      </button>
    </div>
  );
}
