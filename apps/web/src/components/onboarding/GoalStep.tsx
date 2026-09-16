import { useState } from "react";

import type { Discipline } from "../../api/types";

interface Props {
  initialGoal: string;
  initialDiscipline: Discipline;
  onNext: (values: { goal_text: string; primary_discipline: Discipline }) => void;
}

export default function GoalStep({ initialGoal, initialDiscipline, onNext }: Props) {
  const [goal, setGoal] = useState(initialGoal);
  const [discipline, setDiscipline] = useState<Discipline>(initialDiscipline);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">What do you want to improve?</h2>
        <p className="text-neutral-500 text-sm">
          This shapes how we frame everything the coach tells you later.
        </p>
      </div>

      <label className="block space-y-1">
        <span className="text-sm font-medium">Your goal</span>
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="e.g. climb better for an upcoming gran fondo"
          rows={3}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>

      <div className="space-y-1">
        <span className="text-sm font-medium">Primary discipline</span>
        <div className="flex gap-3">
          {(["road", "mtb"] as const).map((option) => (
            <button
              key={option}
              onClick={() => setDiscipline(option)}
              className={`flex-1 rounded-md border py-2 capitalize ${
                discipline === option
                  ? "border-neutral-900 bg-neutral-900 text-white"
                  : "border-neutral-300"
              }`}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <button
        disabled={goal.trim().length === 0}
        onClick={() => onNext({ goal_text: goal, primary_discipline: discipline })}
        className="w-full rounded-md bg-neutral-900 py-2 text-white font-medium disabled:opacity-40"
      >
        Next
      </button>
    </div>
  );
}
