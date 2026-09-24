import { useState } from "react";

import { useI18n } from "../../i18n/I18nProvider";
import BikeEditor from "../BikeEditor";

interface Props {
  onNext: () => void;
}

// Not skippable — the rider needs at least one bike for a garage-level
// capability_tier to mean anything. BikeEditor mutates through the bikes
// API directly (there's no profile-diff to collect and submit here), so
// this step just tracks whether the garage is non-empty.
export default function GarageStep({ onNext }: Props) {
  const { m } = useI18n();
  const [bikeCount, setBikeCount] = useState<number | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{m.onboarding.garage.title}</h2>
        <p className="text-neutral-500 text-sm">
          {m.onboarding.garage.body}
        </p>
      </div>

      <BikeEditor onBikesChange={(bikes) => setBikeCount(bikes.length)} />

      <button
        disabled={!bikeCount}
        onClick={onNext}
        className="primary-button w-full"
      >
        {m.common.next}
      </button>
    </div>
  );
}
