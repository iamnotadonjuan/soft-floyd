import { useState } from "react";

import BikeEditor from "../BikeEditor";

interface Props {
  onNext: () => void;
}

// Not skippable — the rider needs at least one bike for a garage-level
// capability_tier to mean anything. BikeEditor mutates through the bikes
// API directly (there's no profile-diff to collect and submit here), so
// this step just tracks whether the garage is non-empty.
export default function GarageStep({ onNext }: Props) {
  const [bikeCount, setBikeCount] = useState<number | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">What do you ride?</h2>
        <p className="text-neutral-500 text-sm">
          Add every bike you actually ride — sensors vary bike to bike, so we ask per bike. An
          indoor trainer counts as a bike too.
        </p>
      </div>

      <BikeEditor onBikesChange={(bikes) => setBikeCount(bikes.length)} />

      <button
        disabled={!bikeCount}
        onClick={onNext}
        className="w-full rounded-md bg-neutral-900 py-2 text-white font-medium disabled:opacity-40"
      >
        Next
      </button>
    </div>
  );
}
