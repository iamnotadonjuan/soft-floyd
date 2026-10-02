import { useId } from "react";

import type { BikeOut, Discipline, Feel, SessionSetting, Terrain } from "../../api/types";
import HelpDisclosure from "../HelpDisclosure";
import { useI18n } from "../../i18n/I18nProvider";

export const DISCIPLINES: Discipline[] = ["road", "mtb", "gravel"];
const FEELS: Feel[] = ["fresh", "normal", "tired"];
const TERRAINS: Terrain[] = ["flat", "rolling", "hilly"];

export interface SessionFieldsValue {
  plannedDate: string;
  minutes: number;
  setting: SessionSetting;
  discipline: Discipline;
  bikeId: number | "";
  routeIdea: string;
  feel: Feel;
  trainingArea: string;
  terrain: Terrain | null;
  startingAltitudeM: number | "";
}

// The inputs of a training session, shared by the Plan a session form and the
// edit form on a planned session's card, so the two can't drift apart.
export default function SessionFields({ value, onChange, bikes, showIdea = true }: {
  value: SessionFieldsValue;
  onChange: (patch: Partial<SessionFieldsValue>) => void;
  bikes: BikeOut[];
  showIdea?: boolean;
}) {
  const { m } = useI18n();
  const id = useId();
  const matchingBikes = bikes.filter((b) =>
    value.setting === "indoor" ? b.kind === "indoor" : b.kind === value.discipline
  );

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="block space-y-1">
          <div className="flex items-center gap-2 text-sm font-medium"><label htmlFor={`${id}-date`}>{m.training.form.dateLabel}</label><HelpDisclosure title={m.training.form.dateLabel}>{m.training.help.date}</HelpDisclosure></div>
          <input
            id={`${id}-date`}
            type="date"
            value={value.plannedDate}
            onChange={(e) => onChange({ plannedDate: e.target.value })}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </div>
        <div className="block space-y-1">
          <div className="flex items-center gap-2 text-sm font-medium"><label htmlFor={`${id}-minutes`}>{m.training.form.minutesLabel}</label><HelpDisclosure title={m.training.form.minutesLabel}>{m.training.help.minutes}</HelpDisclosure></div>
          <input
            id={`${id}-minutes`}
            type="number"
            min={10}
            max={600}
            value={value.minutes}
            onChange={(e) => onChange({ minutes: Number(e.target.value) })}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </div>
      </div>

      <div>
        <span className="flex items-center gap-2 text-sm font-medium">{m.training.form.settingLabel}<HelpDisclosure title={m.training.form.settingLabel}>{m.training.help.setting}</HelpDisclosure></span>
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
        <span className="flex items-center gap-2 text-sm font-medium">{m.training.form.disciplineLabel}<HelpDisclosure title={m.training.form.disciplineLabel}>{m.training.help.discipline}</HelpDisclosure></span>
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

      {value.setting === "outdoor" && <div className="space-y-4">
        <div className="block space-y-1">
          <div className="flex items-center gap-2 text-sm font-medium"><label htmlFor={`${id}-area`}>{m.training.form.areaLabel}</label><HelpDisclosure title={m.training.form.areaLabel}>{m.training.help.area}</HelpDisclosure></div>
          <input id={`${id}-area`} value={value.trainingArea} maxLength={120} onChange={(e) => onChange({ trainingArea: e.target.value })}
            placeholder={m.training.form.areaPlaceholder} className="w-full rounded-md border border-neutral-300 px-3 py-2" />
        </div>
        <div>
          <span className="flex items-center gap-2 text-sm font-medium">{m.training.form.terrainLabel}<HelpDisclosure title={m.training.form.terrainLabel}>{m.training.help.terrain}</HelpDisclosure></span>
          <div className="mt-2 flex flex-wrap gap-2">
            {TERRAINS.map((key) => <button key={key} type="button" className="choice-chip"
              aria-pressed={value.terrain === key} onClick={() => onChange({ terrain: value.terrain === key ? null : key })}>
              {m.training.form.terrain[key]}
            </button>)}
          </div>
        </div>
        <div className="block space-y-1">
          <div className="flex items-center gap-2 text-sm font-medium"><label htmlFor={`${id}-altitude`}>{m.training.form.altitudeLabel}</label><HelpDisclosure title={m.training.form.altitudeLabel}>{m.training.help.altitude}</HelpDisclosure></div>
          <input id={`${id}-altitude`} type="number" min={-500} max={9000} value={value.startingAltitudeM}
            onChange={(e) => onChange({ startingAltitudeM: e.target.value === "" ? "" : Number(e.target.value) })}
            placeholder={m.training.form.altitudePlaceholder} className="w-full rounded-md border border-neutral-300 px-3 py-2" />
        </div>
      </div>}

      {showIdea && <div className="block space-y-1">
        <div className="flex items-center gap-2 text-sm font-medium"><label htmlFor={`${id}-idea`}>{m.training.form.ideaLabel}</label><HelpDisclosure title={m.training.form.ideaLabel}>{m.training.help.idea}</HelpDisclosure></div>
        <textarea id={`${id}-idea`} value={value.routeIdea} onChange={(e) => onChange({ routeIdea: e.target.value })}
          rows={2} placeholder={m.training.form.ideaPlaceholder}
          className="w-full rounded-md border border-neutral-300 px-3 py-2" />
      </div>}

      <div>
        <span className="flex items-center gap-2 text-sm font-medium">{m.training.form.feelLabel}<HelpDisclosure title={m.training.form.feelLabel}>{m.training.help.feel}</HelpDisclosure></span>
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
