import type { BikeOut, Discipline, Feel, SessionSetting } from "../../api/types";
import { useI18n } from "../../i18n/I18nProvider";

export const DISCIPLINES: Discipline[] = ["road", "mtb", "gravel"];
const FEELS: Feel[] = ["fresh", "normal", "tired"];

export interface SessionFieldsValue {
  plannedDate: string;
  minutes: number;
  setting: SessionSetting;
  discipline: Discipline;
  bikeId: number | "";
  routeIdea: string;
  feel: Feel;
}

// The inputs of a training session, shared by the Plan a session form and the
// edit form on a planned session's card, so the two can't drift apart.
export default function SessionFields({ value, onChange, bikes }: {
  value: SessionFieldsValue;
  onChange: (patch: Partial<SessionFieldsValue>) => void;
  bikes: BikeOut[];
}) {
  const { m } = useI18n();
  const matchingBikes = bikes.filter((b) =>
    value.setting === "indoor" ? b.kind === "indoor" : b.kind === value.discipline
  );

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.training.form.dateLabel}</span>
          <input
            type="date"
            value={value.plannedDate}
            onChange={(e) => onChange({ plannedDate: e.target.value })}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.training.form.minutesLabel}</span>
          <input
            type="number"
            min={10}
            max={600}
            value={value.minutes}
            onChange={(e) => onChange({ minutes: Number(e.target.value) })}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      </div>

      <div>
        <span className="text-sm font-medium">{m.training.form.settingLabel}</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {(["outdoor", "indoor"] as SessionSetting[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => onChange({ setting: key })}
              aria-pressed={value.setting === key}
              className="choice-chip"
            >
              {m.training.form[key]}
            </button>
          ))}
        </div>
      </div>

      <div>
        <span className="text-sm font-medium">{m.training.form.disciplineLabel}</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {DISCIPLINES.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => onChange({ discipline: key })}
              aria-pressed={value.discipline === key}
              className="choice-chip"
            >
              {m.bikes.kinds[key]}
            </button>
          ))}
        </div>
      </div>

      {matchingBikes.length > 1 && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.training.form.bikeLabel}</span>
          <select
            value={value.bikeId}
            onChange={(e) => onChange({ bikeId: e.target.value === "" ? "" : Number(e.target.value) })}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          >
            <option value="" />
            {matchingBikes.map((b) => (
              <option key={b.id} value={b.id}>{b.nickname || m.bikes.kinds[b.kind as Discipline]}</option>
            ))}
          </select>
        </label>
      )}

      <label className="block space-y-1">
        <span className="text-sm font-medium">{m.training.form.ideaLabel}</span>
        <textarea
          value={value.routeIdea}
          onChange={(e) => onChange({ routeIdea: e.target.value })}
          rows={2}
          placeholder={m.training.form.ideaPlaceholder}
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
      </label>

      <div>
        <span className="text-sm font-medium">{m.training.form.feelLabel}</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {FEELS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => onChange({ feel: key })}
              aria-pressed={value.feel === key}
              className="choice-chip"
            >
              {m.training.form[key]}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
