import type { FocusArea } from "../api/types";
import { useI18n } from "../i18n/I18nProvider";

// Fixed vocabulary — see docs/product-specs/new-user-onboarding.md. Kept
// in plain-language order (no jargon), matching SensorsStep/AnchorsStep's
// existing convention for onboarding copy. Labels live in i18n `focus`.
const FOCUS_OPTIONS: FocusArea[] = [
  "endurance", "climbing", "flat_speed", "sprint", "technical_skill",
  "weight", "first_event", "consistency", "enjoy",
];

interface Props {
  value: string[];
  onChange: (value: string[]) => void;
}

export default function FocusPicker({ value, onChange }: Props) {
  const { m } = useI18n();
  const toggle = (key: FocusArea) =>
    onChange(value.includes(key) ? value.filter((v) => v !== key) : [...value, key]);

  return (
    <div className="flex flex-wrap gap-2">
      {FOCUS_OPTIONS.map((key) => (
        <button
          key={key}
          type="button"
          onClick={() => toggle(key)}
          aria-pressed={value.includes(key)}
          className="choice-chip"
        >
          {m.focus[key]}
        </button>
      ))}
    </div>
  );
}
