import { useI18n } from "../../i18n/I18nProvider";
import ConnectionsPanel from "../connections/ConnectionsPanel";

interface Props {
  onNext: () => void;
}

// Skippable — a rider can always connect Garmin later from Settings.
export default function ConnectStep({ onNext }: Props) {
  const { m } = useI18n();
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{m.onboarding.connect.title}</h2>
        <p className="text-neutral-500 text-sm">
          {m.onboarding.connect.body}
        </p>
      </div>

      <ConnectionsPanel />

      <button
        onClick={onNext}
        className="primary-button w-full"
      >
        {m.common.next}
      </button>
    </div>
  );
}
