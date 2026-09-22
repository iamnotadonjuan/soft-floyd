import ConnectionsPanel from "../connections/ConnectionsPanel";

interface Props {
  onNext: () => void;
}

// Skippable — a rider can always connect Garmin later from Settings.
export default function ConnectStep({ onNext }: Props) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">Connect your apps</h2>
        <p className="text-neutral-500 text-sm">
          Link Garmin so rides sync automatically. You can always do this later from Settings.
        </p>
      </div>

      <ConnectionsPanel />

      <button
        onClick={onNext}
        className="w-full rounded-md bg-neutral-900 py-2 text-white font-medium"
      >
        Next
      </button>
    </div>
  );
}
