import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { BikeIn, BikeKind, BikeOut } from "../api/types";

const BIKE_KIND_OPTIONS: { key: BikeKind; label: string }[] = [
  { key: "road", label: "Road" },
  { key: "gravel", label: "Gravel" },
  { key: "mtb", label: "Mountain" },
  { key: "tt", label: "TT / triathlon" },
  { key: "indoor", label: "Indoor trainer" },
];

const BIKE_KIND_LABEL: Record<string, string> = Object.fromEntries(
  BIKE_KIND_OPTIONS.map(({ key, label }) => [key, label]),
);

interface Props {
  // Fires once after the initial load, and again after every mutation —
  // GarageStep uses this to know when there's at least one bike.
  onBikesChange?: (bikes: BikeOut[]) => void;
}

export default function BikeEditor({ onBikesChange }: Props) {
  const [bikes, setBikes] = useState<BikeOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.listBikes()
      .then((loaded) => {
        if (cancelled) return;
        setBikes(loaded);
        onBikesChange?.(loaded);
      })
      .catch((reason) => { if (!cancelled) setError(String(reason)); });
    return () => {
      cancelled = true;
    };
    // onBikesChange fires from this effect once, then again from the
    // mutation handlers below — intentionally not a dependency, or every
    // parent render (e.g. an inline arrow function prop) would refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    const loaded = await api.listBikes();
    setBikes(loaded);
    onBikesChange?.(loaded);
  }

  async function handleAdd(kind: BikeKind) {
    setError(null);
    setAdding(true);
    try {
      await api.addBike({ kind, nickname: "" });
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setAdding(false);
    }
  }

  async function handleUpdate(id: number, patch: BikeIn) {
    setError(null);
    try {
      // Setting is_primary demotes every other bike server-side, and
      // deleting may promote a new primary — refetch rather than
      // patching local state, so the UI never shows a stale invariant.
      await api.updateBike(id, patch);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDelete(id: number) {
    setError(null);
    try {
      await api.deleteBike(id);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  if (bikes === null) {
    return error
      ? <p className="notice-error" role="alert">Could not load bikes: {error}</p>
      : <p className="body-muted text-sm">Loading your garage…</p>;
  }

  return (
    <div className="space-y-4">
      {error && <p className="notice-error" role="alert">{error}</p>}

      {bikes.length > 0 && (
        <div className="space-y-3">
          {bikes.map((bike) => (
            <BikeRow
              key={bike.id}
              bike={bike}
              canDelete={bikes.length > 1}
              onUpdate={(patch) => handleUpdate(bike.id, patch)}
              onDelete={() => handleDelete(bike.id)}
            />
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {BIKE_KIND_OPTIONS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            disabled={adding}
            onClick={() => handleAdd(key)}
            className="secondary-button text-sm disabled:opacity-40"
          >
            + {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function BikeRow({
  bike,
  canDelete,
  onUpdate,
  onDelete,
}: {
  bike: BikeOut;
  canDelete: boolean;
  onUpdate: (patch: BikeIn) => void;
  onDelete: () => void;
}) {
  return (
    <div className="surface-soft p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <input
          aria-label={`${BIKE_KIND_LABEL[bike.kind] ?? bike.kind} bike nickname`}
          defaultValue={bike.nickname}
          onBlur={(e) => {
            if (e.target.value !== bike.nickname) onUpdate({ nickname: e.target.value });
          }}
          placeholder={BIKE_KIND_LABEL[bike.kind] ?? bike.kind}
          className="min-w-0 flex-1 font-semibold"
        />
        <span className="status-pill" data-tone="neutral">
          {bike.kind}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-3 text-sm">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={bike.has_power_meter}
            onChange={(e) => onUpdate({ has_power_meter: e.target.checked })}
          />
          Power meter
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={bike.has_cadence_sensor}
            onChange={(e) => onUpdate({ has_cadence_sensor: e.target.checked })}
          />
          Cadence
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={bike.has_speed_sensor}
            onChange={(e) => onUpdate({ has_speed_sensor: e.target.checked })}
          />
          Speed
        </label>
      </div>

      <div className="body-muted mt-4 flex flex-wrap items-center justify-between gap-2 text-sm">
        {bike.is_primary ? (
          <span className="font-semibold text-[#30553c]">Primary bike</span>
        ) : (
          <button type="button" onClick={() => onUpdate({ is_primary: true })} className="text-button">
            Make primary
          </button>
        )}
        {canDelete && (
          <button type="button" onClick={onDelete} className="font-semibold text-red-700 underline">
            Remove
          </button>
        )}
      </div>
    </div>
  );
}
