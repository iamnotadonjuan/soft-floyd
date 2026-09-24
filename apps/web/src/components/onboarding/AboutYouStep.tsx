import { useState } from "react";

import type { SelfRatedLevel } from "../../api/types";

export interface AboutYouValue {
  has_hr_monitor: boolean;
  birth_year: number | null;
  weight_kg: number | null;
  max_hr: number | null;
  years_riding: number | null;
  longest_recent_ride_km: number | null;
  self_rated_level: string | null;
  followed_plan_before: boolean | null;
  health_notes: string | null;
}

interface Props {
  initial: AboutYouValue;
  onNext: (values: AboutYouValue) => void;
}

const LEVEL_OPTIONS: { key: SelfRatedLevel; label: string }[] = [
  { key: "beginner", label: "Just starting out" },
  { key: "recreational", label: "Recreational" },
  { key: "enthusiast", label: "Enthusiast" },
  { key: "competitive", label: "Competitive / racing" },
];

function numberField(raw: string): number | null {
  return raw.trim() === "" ? null : Number(raw);
}

// Every field here is skippable — see docs/product-specs/new-user-onboarding.md.
export default function AboutYouStep({ initial, onNext }: Props) {
  const [values, setValues] = useState<AboutYouValue>(initial);

  function set<K extends keyof AboutYouValue>(key: K, value: AboutYouValue[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">A bit about you</h2>
        <p className="text-neutral-500 text-sm">
          All optional — skip anything you'd rather not answer.
        </p>
      </div>

      <label className="flex items-center gap-3 rounded-xl border border-[#d9ded1] bg-[#eef1e8] p-4 text-sm font-medium">
        <input
          type="checkbox"
          checked={values.has_hr_monitor}
          onChange={(e) => set("has_hr_monitor", e.target.checked)}
        />
        I wear a heart rate monitor when I ride
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Birth year</span>
          <input
            type="number"
            value={values.birth_year ?? ""}
            onChange={(e) => set("birth_year", numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Weight (kg)</span>
          <input
            type="number"
            step={0.1}
            value={values.weight_kg ?? ""}
            onChange={(e) => set("weight_kg", numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Max heart rate (bpm)</span>
          <input
            type="number"
            value={values.max_hr ?? ""}
            onChange={(e) => set("max_hr", numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Years riding</span>
          <input
            type="number"
            step={0.5}
            value={values.years_riding ?? ""}
            onChange={(e) => set("years_riding", numberField(e.target.value))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>

      <label className="block space-y-1">
        <span className="text-sm font-medium">Longest ride in the last few months (km)</span>
        <input
          type="number"
          value={values.longest_recent_ride_km ?? ""}
          onChange={(e) => set("longest_recent_ride_km", numberField(e.target.value))}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>

      <div className="space-y-1">
        <span className="text-sm font-medium">How would you describe yourself?</span>
        <div className="flex flex-wrap gap-2">
          {LEVEL_OPTIONS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => set("self_rated_level", values.self_rated_level === key ? null : key)}
              aria-pressed={values.self_rated_level === key}
              className="choice-chip"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={values.followed_plan_before === true}
          onChange={(e) => set("followed_plan_before", e.target.checked)}
        />
        I've followed a structured training plan before
      </label>

      <label className="block space-y-1">
        <span className="text-sm font-medium">Anything to know — injuries, limits, etc.</span>
        <textarea
          value={values.health_notes ?? ""}
          onChange={(e) => set("health_notes", e.target.value === "" ? null : e.target.value)}
          rows={2}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>

      <button
        onClick={() => onNext(values)}
        className="primary-button w-full"
      >
        Next
      </button>
    </div>
  );
}
