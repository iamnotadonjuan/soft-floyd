import { useState } from "react";

import { api, ApiError } from "../../api/client";
import type { RepeatBlock, StepEnd, StepTarget, TrainingSessionOut, WorkoutStep } from "../../api/types";
import { useI18n } from "../../i18n/I18nProvider";
import { rideDuration } from "../activityFormat";

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

function targetText(target: StepTarget | null): string | null {
  if (!target) return null;
  const unit = target.kind === "power" ? "W" : target.kind === "hr" ? "bpm" : "rpm";
  return `${Math.round(target.low)}–${Math.round(target.high)} ${unit}`;
}

function StepRow({ step }: { step: WorkoutStep }) {
  const { m } = useI18n();
  const target = targetText(step.target);
  return (
    <li className="surface-soft flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
      <span>
        <strong>{m.training.stepKind[step.kind]}</strong> — {step.name} · {endText(step.end)}
      </span>
      <span className="body-muted">{target ?? step.cue}</span>
    </li>
  );

  function endText(end: StepEnd): string {
    if (end.kind === "time" && end.seconds != null) return rideDuration(end.seconds);
    if (end.kind === "distance" && end.meters != null) return `${(end.meters / 1000).toFixed(1)} km`;
    return m.training.untilLapButton;
  }
}

function RepeatRow({ block }: { block: RepeatBlock }) {
  const { m } = useI18n();
  return (
    <li className="surface-soft space-y-2 p-3">
      <p className="text-sm font-semibold">{m.training.repeatLabel(block.count)}</p>
      <ol className="space-y-2 border-l-2 border-neutral-200 pl-3">
        {block.steps.map((s, i) => (
          <StepRow key={i} step={s} />
        ))}
      </ol>
    </li>
  );
}

function statusTone(status: TrainingSessionOut["status"]): string {
  if (status === "done") return "good";
  if (status === "skipped") return "neutral";
  return "warning";
}

interface Props {
  session: TrainingSessionOut;
  garminConnected: boolean;
  onChange: (updated: TrainingSessionOut) => void;
  onDeleted: () => void;
}

// One planned/done/skipped session: the workout, the coach's rationale,
// and the actions to get it onto a device or mark it as ridden. Used
// both for the just-generated result and for reopening a past session —
// same TrainingSessionOut shape either way.
export default function WorkoutCard({ session, garminConnected, onChange, onDeleted }: Props) {
  const { m, intlLocale } = useI18n();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(key: string, action: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="surface space-y-5 p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow mb-1">{m.training.emphasisLabel[session.intent.emphasis]}</p>
          <h3 className="text-xl font-semibold">{session.workout.name}</h3>
          <p className="body-muted mt-1 text-sm">
            {m.training.estMinutes(session.workout.est_minutes)} ·{" "}
            {new Date(session.planned_date).toLocaleDateString(intlLocale, {
              weekday: "long", month: "short", day: "numeric",
            })}
          </p>
        </div>
        <span className="status-pill" data-tone={statusTone(session.status)}>
          {m.training.status[session.status]}
        </span>
      </div>

      {session.intent.off_schedule && (
        <p className="notice-error" role="status">{m.training.offSchedule}</p>
      )}

      <div>
        <p className="text-sm font-medium">{m.training.rationaleLabel}</p>
        <p className="body-muted mt-1 text-sm">{session.rationale}</p>
        {session.adjustments && (
          <p className="mt-2 text-sm">
            <strong>{m.training.adjustmentsLabel}:</strong> {session.adjustments}
          </p>
        )}
      </div>

      {session.sources.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label={m.training.sourcesAria}>
          {session.sources.map((s) => (
            <li key={`${s.book_id}-${s.page_start}`} className="status-pill" data-tone="neutral">
              {s.title}, p.{s.page_start}
            </li>
          ))}
        </ul>
      )}

      <ol className="space-y-2">
        {session.workout.steps.map((item, i) =>
          "count" in item ? <RepeatRow key={i} block={item} /> : <StepRow key={i} step={item} />
        )}
      </ol>

      {error && <p className="notice-error" role="alert">{error}</p>}

      <div className="flex flex-wrap items-center gap-2 pt-2">
        {garminConnected && (
          <button
            className="primary-button"
            disabled={busy !== null}
            onClick={() => run("garmin", async () => onChange(await api.sendTrainingSessionToGarmin(session.id)))}
          >
            {busy === "garmin" ? m.training.actions.sending : m.training.actions.sendToGarmin}
          </button>
        )}
        {session.available_export_formats.map((fmt) => (
          <a key={fmt} className="secondary-button" href={api.trainingSessionExportUrl(session.id, fmt)}>
            {m.training.actions.download} {m.training.formats[fmt]}
          </a>
        ))}
        <button
          className="secondary-button"
          disabled={busy !== null}
          onClick={() => run("regenerate", async () => onChange(await api.regenerateTrainingSession(session.id)))}
        >
          {busy === "regenerate" ? m.training.actions.regenerating : m.training.actions.regenerate}
        </button>
        {session.status !== "done" && (
          <button
            className="text-button"
            disabled={busy !== null}
            onClick={() => run("done", async () => onChange(await api.updateTrainingSessionStatus(session.id, "done")))}
          >
            {m.training.actions.markDone}
          </button>
        )}
        {session.status !== "skipped" && (
          <button
            className="text-button"
            disabled={busy !== null}
            onClick={() => run("skip", async () => onChange(await api.updateTrainingSessionStatus(session.id, "skipped")))}
          >
            {m.training.actions.markSkipped}
          </button>
        )}
        <button
          className="text-button text-red-700"
          disabled={busy !== null}
          onClick={() => run("delete", async () => { await api.deleteTrainingSession(session.id); onDeleted(); })}
        >
          {m.training.actions.delete}
        </button>
      </div>

      {session.sent_to_garmin_at && (
        <p className="body-muted text-xs">
          {m.training.actions.sentAt(new Date(session.sent_to_garmin_at).toLocaleString(intlLocale))}
        </p>
      )}
    </div>
  );
}
