import { useState } from "react";

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
  const [ftp, setFtp] = useState<string>(initialFtp?.toString() ?? "");
  const [lthr, setLthr] = useState<string>((initialLthr ?? 165).toString());

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">A couple of anchor numbers</h2>
        <p className="text-neutral-500 text-sm">Skip either if you don't know it yet.</p>
      </div>

      {hasPowerMeter && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">FTP (watts)</span>
          <input
            type="number"
            min={0}
            value={ftp}
            onChange={(e) => setFtp(e.target.value)}
            placeholder="e.g. 240"
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </label>
      )}

      {hasHrMonitor && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">Lactate threshold HR (bpm)</span>
          <input
            type="number"
            min={0}
            value={lthr}
            onChange={(e) => setLthr(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
          <span className="text-xs text-neutral-400">Default 165 if you're not sure.</span>
        </label>
      )}

      <button
        onClick={() =>
          onNext({
            ftp_watts: ftp.trim() === "" ? null : Number(ftp),
            lthr: lthr.trim() === "" ? null : Number(lthr),
          })
        }
        className="w-full rounded-md bg-neutral-900 py-2 text-white font-medium"
      >
        Next
      </button>
    </div>
  );
}
