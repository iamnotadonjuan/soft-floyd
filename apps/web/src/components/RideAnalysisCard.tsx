import { useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { RideAnalysisOut, RideMetricsOut } from "../api/types";
import { useI18n } from "../i18n/I18nProvider";

export default function RideAnalysisCard({ activityId }: { activityId: number }) {
  const { m, locale, intlLocale } = useI18n();
  const t = m.rideDetail.analysis;
  const [result, setResult] = useState<RideAnalysisOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    api.getRideAnalysis(activityId)
      .then((value) => { if (active) setResult(value); })
      .catch((reason) => { if (active) setLoadError(String(reason)); });
    return () => { active = false; };
  }, [activityId]);

  async function analyze(regenerate: boolean) {
    setBusy(true);
    setActionError(null);
    try {
      setResult(await api.analyzeRide(activityId, locale, regenerate));
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 402) setActionError(t.budget);
      else if (reason instanceof ApiError && reason.status === 400) setActionError(t.noKey);
      else setActionError(t.failed);
    } finally {
      setBusy(false);
    }
  }

  const analysis = result?.analysis ?? null;

  return (
    <section className="surface mt-5 p-5 sm:p-7" aria-labelledby="ride-analysis-heading">
      <p className="eyebrow mb-1">{t.eyebrow}</p>
      <h2 id="ride-analysis-heading" className="section-title">{t.title}</h2>

      {loadError && <div className="notice-error mt-4" role="alert">{t.loadError(loadError)}</div>}
      {!result && !loadError && <p className="body-muted mt-3">{t.loading}</p>}

      {result && !analysis && (
        <div className="mt-3">
          <p className="body-muted">{t.intro}</p>
          <button className="primary-button mt-4" disabled={busy} onClick={() => analyze(false)}>
            {busy ? t.analyzing : t.analyze}
          </button>
        </div>
      )}

      {analysis && result && (
        <div className="mt-4">
          <p className="text-lg font-semibold text-[#243e2c]">{analysis.headline}</p>
          <Bullets heading={t.wentWell} items={analysis.went_well} />
          <Bullets heading={t.toImprove} items={analysis.to_improve} />
          <div className="mt-5">
            <h3 className="eyebrow mb-1">{t.nextTime}</h3>
            <p>{analysis.next_time}</p>
          </div>
          {analysis.data_caveat && <p className="body-muted mt-4 text-sm">{analysis.data_caveat}</p>}
        </div>
      )}

      {result && <MetricTiles metrics={result.metrics} />}

      {actionError && <div className="notice-error mt-4" role="alert">{actionError}</div>}

      {analysis && result?.generated_at && (
        <div className="mt-5 flex flex-wrap items-center gap-4 text-sm">
          <span className="body-muted">
            {t.generatedAt(new Date(result.generated_at).toLocaleDateString(intlLocale))}
          </span>
          <button className="text-button" disabled={busy} onClick={() => analyze(true)}>
            {busy ? t.analyzing : t.regenerate}
          </button>
        </div>
      )}
    </section>
  );
}

function Bullets({ heading, items }: { heading: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-5">
      <h3 className="eyebrow mb-1">{heading}</h3>
      <ul className="list-disc space-y-1 pl-5">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function MetricTiles({ metrics }: { metrics: RideMetricsOut }) {
  const { m } = useI18n();
  const t = m.rideDetail.analysis;
  const tiles: { label: string; value: string; hint?: string }[] = [];
  if (metrics.normalized_power_w !== null) tiles.push({ label: t.np, value: `${metrics.normalized_power_w} W` });
  if (metrics.intensity_factor !== null) tiles.push({ label: t.intensityFactor, value: String(metrics.intensity_factor) });
  if (metrics.tss !== null) tiles.push({ label: t.tss, value: String(Math.round(metrics.tss)) });
  if (metrics.variability_index !== null) tiles.push({ label: t.variability, value: String(metrics.variability_index) });
  if (metrics.hr_drift_pct !== null) {
    tiles.push({
      label: t.hrDrift,
      value: `${metrics.hr_drift_pct > 0 ? "+" : ""}${metrics.hr_drift_pct}%`,
      hint: t.hrDriftHint,
    });
  }
  if (metrics.load !== null && metrics.load_basis) {
    tiles.push({
      label: t.load,
      value: String(Math.round(metrics.load)),
      hint: t.loadBasis[metrics.load_basis] ?? metrics.load_basis,
    });
  }
  if (metrics.climb_m_per_km !== null) tiles.push({ label: t.climbing, value: t.perKm(metrics.climb_m_per_km) });
  if (metrics.lap_variation_pct !== null && metrics.lap_variation_basis) {
    tiles.push({
      label: t.lapVariation,
      value: `${metrics.lap_variation_pct}%`,
      hint: t.lapVariationBasis[metrics.lap_variation_basis] ?? metrics.lap_variation_basis,
    });
  }

  const zones = metrics.hr_zone_minutes ? Object.entries(metrics.hr_zone_minutes) : [];
  const zoneTotal = zones.reduce((sum, [, minutes]) => sum + minutes, 0);
  if (!tiles.length && !zoneTotal) return null;

  return (
    <div className="mt-6 border-t border-[#d9dfcf] pt-5">
      <h3 className="eyebrow mb-3">{t.metricsHeading}</h3>
      {tiles.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-3">
          {tiles.map((tile) => (
            <div key={tile.label}>
              <p className="eyebrow mb-1">{tile.label}</p>
              <p className="text-xl font-semibold text-[#243e2c]">{tile.value}</p>
              {tile.hint && <p className="body-muted text-xs">{tile.hint}</p>}
            </div>
          ))}
        </div>
      )}
      {zoneTotal > 0 && (
        <div className="mt-5">
          <p className="eyebrow mb-2">{t.zones}</p>
          <div className="flex h-3 overflow-hidden rounded-full bg-[#e6eadc]" role="img"
            aria-label={zones.map(([z, min]) => `${t.zone(z)} ${t.minutes(min)}`).join(", ")}>
            {zones.map(([z, minutes]) => (
              <div key={z} style={{ width: `${(minutes / zoneTotal) * 100}%`, opacity: 0.35 + Number(z) * 0.13 }}
                className="bg-[#30553c]" />
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs body-muted">
            {zones.map(([z, minutes]) => <span key={z}>{t.zone(z)} · {t.minutes(minutes)}</span>)}
          </div>
        </div>
      )}
    </div>
  );
}
