import { useState } from "react";

import { useI18n } from "../../i18n/I18nProvider";

interface Props {
  hasPowerMeter: boolean;
  hasHrMonitor: boolean;
  initialFtp: number | null;
  initialLthr: number | null;
  onNext: (values: { ftp_watts: number | null; lthr: number | null }) => void;
}

// Onboarding.tsx skips this step entirely when neither sensor is present —
// never ask for a number the rider has no way to produce. hasPowerMeter
// reflects "any bike in the garage has a power meter" (a derived field
// on ProfileOut, refreshed after GarageStep) — see
// docs/product-specs/new-user-onboarding.md.
export default function AnchorsStep({
  hasPowerMeter,
  hasHrMonitor,
  initialFtp,
  initialLthr,
  onNext,
}: Props) {
  const { m } = useI18n();
  const [ftp, setFtp] = useState<string>(initialFtp?.toString() ?? "");
  const [lthr, setLthr] = useState<string>((initialLthr ?? 165).toString());

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{m.onboarding.anchors.title}</h2>
        <p className="text-neutral-500 text-sm">{m.onboarding.anchors.body}</p>
      </div>

      {hasPowerMeter && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.fields.ftp}</span>
          <input
            type="number"
            min={0}
            value={ftp}
            onChange={(e) => setFtp(e.target.value)}
            placeholder={m.onboarding.anchors.ftpPlaceholder}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      )}

      {hasHrMonitor && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">{m.fields.lthr}</span>
          <input
            type="number"
            min={0}
            value={lthr}
            onChange={(e) => setLthr(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
          <span className="text-xs text-neutral-400">{m.onboarding.anchors.lthrDefault}</span>
        </label>
      )}

      <button
        onClick={() =>
          onNext({
            ftp_watts: ftp.trim() === "" ? null : Number(ftp),
            lthr: lthr.trim() === "" ? null : Number(lthr),
          })
        }
        className="primary-button w-full"
      >
        {m.common.next}
      </button>
    </div>
  );
}
