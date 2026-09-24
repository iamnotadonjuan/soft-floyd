import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { BikeIn, BikeKind, BikeOut } from "../api/types";
import { useI18n } from "../i18n/I18nProvider";
import { bikeKindLabel } from "./activityFormat";

const BIKE_KINDS: BikeKind[] = ["road", "gravel", "mtb", "tt", "indoor"];

interface Props {
  // Fires once after the initial load, and again after every mutation —
  // GarageStep uses this to know when there's at least one bike.
  onBikesChange?: (bikes: BikeOut[]) => void;
}

export default function BikeEditor({ onBikesChange }: Props) {
  const { m } = useI18n();
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
      ? <p className="notice-error" role="alert">{m.bikes.loadError(error)}</p>
      : <p className="body-muted text-sm">{m.bikes.loading}</p>;
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
        {BIKE_KINDS.map((key) => (
          <button
            key={key}
            type="button"
            disabled={adding}
            onClick={() => handleAdd(key)}
            className="secondary-button text-sm disabled:opacity-40"
          >
            + {m.bikes.kinds[key]}
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
  const { m } = useI18n();
  const label = bikeKindLabel(bike.kind, m);
  return (
    <div className="surface-soft p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <input
          aria-label={m.bikes.nicknameAria(label)}
          defaultValue={bike.nickname}
          onBlur={(e) => {
            if (e.target.value !== bike.nickname) onUpdate({ nickname: e.target.value });
          }}
          placeholder={label}
          className="min-w-0 flex-1 font-semibold"
        />
        <span className="status-pill" data-tone="neutral">
          {label}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-3 text-sm">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={bike.has_power_meter}
            onChange={(e) => onUpdate({ has_power_meter: e.target.checked })}
          />
          {m.bikes.powerMeter}
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={bike.has_cadence_sensor}
            onChange={(e) => onUpdate({ has_cadence_sensor: e.target.checked })}
          />
          {m.bikes.cadence}
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={bike.has_speed_sensor}
            onChange={(e) => onUpdate({ has_speed_sensor: e.target.checked })}
          />
          {m.bikes.speed}
        </label>
      </div>

      <div className="body-muted mt-4 flex flex-wrap items-center justify-between gap-2 text-sm">
        {bike.is_primary ? (
          <span className="font-semibold text-[#30553c]">{m.bikes.primary}</span>
        ) : (
          <button type="button" onClick={() => onUpdate({ is_primary: true })} className="text-button">
            {m.bikes.makePrimary}
          </button>
        )}
        {canDelete && (
          <button type="button" onClick={onDelete} className="font-semibold text-red-700 underline">
            {m.bikes.remove}
          </button>
        )}
      </div>
    </div>
  );
}
