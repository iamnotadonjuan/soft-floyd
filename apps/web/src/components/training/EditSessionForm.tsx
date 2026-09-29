import { useEffect, useState } from "react";

import { api, ApiError } from "../../api/client";
import type { BikeOut, SessionChangesIn, TrainingSessionOut } from "../../api/types";
import { useI18n } from "../../i18n/I18nProvider";
import SessionFields, { type SessionFieldsValue } from "./SessionFields";

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

function initialValue(session: TrainingSessionOut): SessionFieldsValue {
  const request = session.request;
  return {
    plannedDate: request.planned_date,
    minutes: request.available_minutes,
    setting: request.setting,
    discipline: request.discipline,
    bikeId: request.bike_id ?? "",
    routeIdea: request.route_idea,
    feel: request.feel,
  };
}

// Only what differs from the stored request: the server treats a date-only
// change as a move (no AI call) and anything else as a rebuild.
function changesFrom(session: TrainingSessionOut, value: SessionFieldsValue): SessionChangesIn {
  const request = session.request;
  const changes: SessionChangesIn = {};
  if (value.plannedDate !== request.planned_date) changes.planned_date = value.plannedDate;
  if (value.minutes !== request.available_minutes) changes.available_minutes = value.minutes;
  if (value.setting !== request.setting) changes.setting = value.setting;
  if (value.discipline !== request.discipline) changes.discipline = value.discipline;
  if (value.bikeId !== "" && value.bikeId !== request.bike_id) changes.bike_id = value.bikeId;
  if (value.routeIdea !== request.route_idea) changes.route_idea = value.routeIdea;
  if (value.feel !== request.feel) changes.feel = value.feel;
  return changes;
}

// Inline editor on a planned session's card (exec-plan 0013). Loads the
// garage itself so it works both on the Training page and inside the chat.
export default function EditSessionForm({ session, onSaved, onCancel }: {
  session: TrainingSessionOut;
  onSaved: (updated: TrainingSessionOut) => void;
  onCancel: () => void;
}) {
  const { m } = useI18n();
  const t = m.training.edit;
  const [value, setValue] = useState<SessionFieldsValue>(() => initialValue(session));
  const [bikes, setBikes] = useState<BikeOut[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.listBikes().then((items) => { if (active) setBikes(items); }).catch(() => { /* the bike picker just stays hidden */ });
    return () => { active = false; };
  }, []);

  const changes = changesFrom(session, value);
  const changed = Object.keys(changes);
  const dateOnly = changed.length === 1 && changed[0] === "planned_date";

  function update(patch: Partial<SessionFieldsValue>) {
    setValue((current) => {
      const next = { ...current, ...patch };
      // A bike picked for the old setting/discipline may no longer fit: let the
      // server pick again unless the rider chose one in this same change.
      if ((patch.setting !== undefined || patch.discipline !== undefined) && patch.bikeId === undefined) {
        next.bikeId = "";
      }
      return next;
    });
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      onSaved(await api.updateTrainingSession(session.id, changes));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="surface-soft space-y-4 p-4 sm:p-5">
      <h4 className="font-semibold">{t.title}</h4>
      <SessionFields value={value} onChange={update} bikes={bikes} />
      {changed.length > 0 && (
        <p className="body-muted text-sm">{dateOnly ? t.moveNote : t.rebuildNote}</p>
      )}
      {changed.length > 0 && session.sent_to_garmin_at && (
        <p className="notice-error" role="status">{t.garminWarning}</p>
      )}
      {error && <p className="notice-error" role="alert">{t.error(error)}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button className="primary-button" disabled={saving || changed.length === 0} onClick={save}>
          {saving ? t.saving : dateOnly ? t.moveSubmit : t.rebuildSubmit}
        </button>
        <button className="text-button" disabled={saving} onClick={onCancel}>{t.cancel}</button>
      </div>
    </div>
  );
}
