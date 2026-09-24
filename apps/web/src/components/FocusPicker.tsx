import type { FocusArea } from "../api/types";

// Fixed vocabulary — see docs/product-specs/new-user-onboarding.md. Kept
// in plain-language order (no jargon), matching SensorsStep/AnchorsStep's
// existing convention for onboarding copy.
const FOCUS_OPTIONS: { key: FocusArea; label: string }[] = [
  { key: "endurance", label: "Ride longer without fading" },
  { key: "climbing", label: "Climb better" },
  { key: "flat_speed", label: "Go faster on the flats" },
  { key: "sprint", label: "Sprint / short hard efforts" },
  { key: "technical_skill", label: "Bike handling & technical skill" },
  { key: "weight", label: "Lose weight" },
  { key: "first_event", label: "Finish a first event" },
  { key: "consistency", label: "Just ride more consistently" },
  { key: "enjoy", label: "Enjoy it more, less pressure" },
];

interface Props {
  value: string[];
  onChange: (value: string[]) => void;
}

export default function FocusPicker({ value, onChange }: Props) {
  const toggle = (key: FocusArea) =>
    onChange(value.includes(key) ? value.filter((v) => v !== key) : [...value, key]);

  return (
    <div className="flex flex-wrap gap-2">
      {FOCUS_OPTIONS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          onClick={() => toggle(key)}
          aria-pressed={value.includes(key)}
          className="choice-chip"
        >
          {label}
        </button>
      ))}
    </div>
  );
}
