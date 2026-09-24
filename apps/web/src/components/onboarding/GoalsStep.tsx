import { useState } from "react";

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
  const [goal, setGoal] = useState(initialGoal);
  const [focusAreas, setFocusAreas] = useState<string[]>(initialFocusAreas);
  const [eventName, setEventName] = useState(initialTargetEventName ?? "");
  const [eventDate, setEventDate] = useState(initialTargetEventDate ?? "");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">What do you want to get better at?</h2>
        <p className="text-neutral-500 text-sm">
          Pick everything that applies — this shapes how the coach frames everything else.
        </p>
      </div>

      <FocusPicker value={focusAreas} onChange={setFocusAreas} />

      <label className="block space-y-1">
        <span className="text-sm font-medium">In your own words</span>
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="e.g. climb better for an upcoming gran fondo"
          rows={3}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>

      <div className="space-y-1">
        <span className="text-sm font-medium">Got an event in mind? (optional)</span>
        <div className="grid grid-cols-2 gap-3">
          <input
            value={eventName}
            onChange={(e) => setEventName(e.target.value)}
            placeholder="Event name"
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
        Next
      </button>
    </div>
  );
}
