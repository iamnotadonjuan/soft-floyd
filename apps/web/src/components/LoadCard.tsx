import { type KeyboardEvent, type PointerEvent, type ReactNode, useEffect, useRef, useState } from "react";

import type { DayLoadOut, TrainingLoadOut } from "../api/types";
import { useI18n } from "../i18n/I18nProvider";
import HelpDisclosure from "./HelpDisclosure";

// Chart geometry. Width follows the container so text stays at its real
// pixel size on every screen; only the height is fixed.
const H = 230;
const DEFAULT_W = 640;
const MIN_W = 260;
const NARROW_W = 440; // below this, no end labels and a slimmer right margin
const M = { top: 12, bottom: 28, left: 34 };
const PLOT_H = H - M.top - M.bottom;
// End labels closer together than this would collide; skip them and let the
// legend and tooltip carry identity instead of nudging them off their lines.
const MIN_LABEL_GAP = 16;

const FORM_GLYPH: Record<TrainingLoadOut["form"], string> = {
  fresh: "▲",
  neutral: "●",
  tired: "▼",
  "very tired": "⚠",
};
const FORM_TONE: Record<TrainingLoadOut["form"], string> = {
  fresh: "good",
  neutral: "neutral",
  tired: "warning",
  "very tired": "error",
};

function niceScale(max: number): { top: number; ticks: number[] } {
  const step = [5, 10, 20, 25, 50, 100].find((s) => s >= Math.max(max, 8) / 4) ?? 100;
  const top = Math.ceil(Math.max(max, 1) / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  return { top, ticks };
}

function LineKey({ color }: { color: string }) {
  return (
    <svg width="18" height="8" aria-hidden="true">
      <line x1="1" y1="4" x2="17" y2="4" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function Tile({ label, value, hint, help, swatch, extra }: {
  label: string; value: string; hint: string; help: string; swatch?: string; extra?: ReactNode;
}) {
  return (
    <div className="surface-soft p-4">
      <div className="eyebrow flex items-center gap-2">
        {swatch && <LineKey color={swatch} />}
        {label}
        <HelpDisclosure title={label}>{help}</HelpDisclosure>
      </div>
      <p className="mt-2 text-3xl font-semibold leading-none">{value}</p>
      <p className="body-muted mt-2 text-sm">{hint}</p>
      {extra}
    </div>
  );
}

function LoadChart({ series }: { series: DayLoadOut[] }) {
  const { m, intlLocale } = useI18n();
  const t = m.load;
  const [active, setActive] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(DEFAULT_W);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(MIN_W, Math.round(el.clientWidth)));
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const n = series.length;
  if (n < 2) return null;

  const W = width;
  const narrow = W < NARROW_W;
  const right = narrow ? 16 : 84;
  const plotW = W - M.left - right;

  const { top, ticks } = niceScale(Math.max(...series.map((d) => Math.max(d.ctl, d.atl))));
  const x = (i: number) => M.left + (i * plotW) / (n - 1);
  const y = (v: number) => M.top + PLOT_H - (v / top) * PLOT_H;
  const path = (pick: (d: DayLoadOut) => number) =>
    series.map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(pick(d)).toFixed(1)}`).join(" ");
  const shortDate = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(intlLocale, { month: "short", day: "numeric" });
  const longDate = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(intlLocale, { weekday: "short", month: "short", day: "numeric" });
  const fmt = new Intl.NumberFormat(intlLocale, { maximumFractionDigits: 0 });

  const last = series[n - 1];
  const xTicks = [0, Math.floor((n - 1) / 3), Math.floor(((n - 1) * 2) / 3), n - 1];
  const showEndLabels = !narrow && Math.abs(y(last.ctl) - y(last.atl)) >= MIN_LABEL_GAP;

  function indexAt(clientX: number): number {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return n - 1;
    const local = clientX - rect.left - M.left;
    return Math.max(0, Math.min(n - 1, Math.round(local / (plotW / (n - 1)))));
  }

  function onKeyDown(event: KeyboardEvent<SVGSVGElement>) {
    const step =
      event.key === "ArrowLeft" ? -1 :
      event.key === "ArrowRight" ? 1 : null;
    const jump = event.key === "Home" ? 0 : event.key === "End" ? n - 1 : null;
    if (step === null && jump === null) return;
    event.preventDefault();
    setActive((current) => Math.max(0, Math.min(n - 1, jump ?? (current ?? n - 1) + (step ?? 0))));
  }

  const day = active === null ? null : series[active];
  const dot = (i: number, value: number, color: string) => (
    <g key={`${color}-${i}`} pointerEvents="none">
      <circle cx={x(i)} cy={y(value)} r="6" style={{ fill: "var(--viz-surface)" }} />
      <circle cx={x(i)} cy={y(value)} r="4" style={{ fill: color }} />
    </g>
  );

  return (
    <div className="relative" ref={wrapRef}>
      <ul className="mb-2 flex flex-wrap gap-x-5 gap-y-1 text-sm" aria-label={t.legendAria}>
        <li className="flex items-center gap-2"><LineKey color="var(--viz-fitness)" />{t.fitness}</li>
        <li className="flex items-center gap-2"><LineKey color="var(--viz-fatigue)" />{t.fatigue}</li>
      </ul>
      <svg
        ref={svgRef}
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        className="block touch-pan-y"
        tabIndex={0}
        role="group"
        aria-label={t.chartAria(n)}
        onPointerMove={(e: PointerEvent<SVGSVGElement>) => setActive(indexAt(e.clientX))}
        onPointerDown={(e: PointerEvent<SVGSVGElement>) => setActive(indexAt(e.clientX))}
        onPointerLeave={() => setActive(null)}
        onFocus={() => setActive((a) => a ?? n - 1)}
        onBlur={() => setActive(null)}
        onKeyDown={onKeyDown}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={M.left} x2={W - right} y1={y(v)} y2={y(v)}
              style={{ stroke: v === 0 ? "var(--viz-axis)" : "var(--viz-grid)" }} strokeWidth="1" />
            <text x={M.left - 8} y={y(v) + 4} textAnchor="end" className="fill-[#647167] text-[11px]">{fmt.format(v)}</text>
          </g>
        ))}
        {xTicks.map((i, k) => (
          <text key={i} x={x(i)} y={H - 8} className="fill-[#647167] text-[11px]"
            textAnchor={k === 0 ? "start" : k === xTicks.length - 1 ? "end" : "middle"}>
            {shortDate(series[i].date)}
          </text>
        ))}

        <path d={path((d) => d.atl)} fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          style={{ stroke: "var(--viz-fatigue)" }} />
        <path d={path((d) => d.ctl)} fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          style={{ stroke: "var(--viz-fitness)" }} />

        {showEndLabels && (
          <>
            <text x={x(n - 1) + 12} y={y(last.ctl) + 4} className="fill-[#233029] text-[11px] font-semibold">{t.fitness}</text>
            <text x={x(n - 1) + 12} y={y(last.atl) + 4} className="fill-[#233029] text-[11px] font-semibold">{t.fatigue}</text>
          </>
        )}
        {day && active !== null && (
          <line x1={x(active)} x2={x(active)} y1={M.top} y2={M.top + PLOT_H} pointerEvents="none"
            style={{ stroke: "var(--viz-axis)" }} strokeWidth="1" />
        )}
        {dot(n - 1, last.atl, "var(--viz-fatigue)")}
        {dot(n - 1, last.ctl, "var(--viz-fitness)")}
        {day && active !== null && active !== n - 1 && (
          <>
            {dot(active, day.atl, "var(--viz-fatigue)")}
            {dot(active, day.ctl, "var(--viz-fitness)")}
          </>
        )}
      </svg>

      <div aria-live="polite">
        {day && active !== null && (
          <div className="load-tooltip" style={{
            left: x(active),
            transform: active > n * 0.6 ? "translateX(calc(-100% - 12px))" : "translateX(12px)",
          }}>
            <p className="body-muted text-xs">{longDate(day.date)}</p>
            {([
              ["var(--viz-fitness)", t.fitness, day.ctl],
              ["var(--viz-fatigue)", t.fatigue, day.atl],
            ] as const).map(([color, name, value]) => (
              <p key={name} className="mt-1 flex items-center gap-2 text-sm">
                <LineKey color={color} />
                <strong>{fmt.format(value)}</strong>
                <span className="body-muted">{name}</span>
              </p>
            ))}
            <p className="body-muted mt-1 text-xs">{t.dayLoad}: {fmt.format(day.load)}</p>
          </div>
        )}
      </div>

      <details className="mt-3">
        <summary className="text-button cursor-pointer text-sm">{t.tableSummary}</summary>
        <div className="mt-2 max-h-64 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="body-muted">
                <th className="py-1 pr-3 font-semibold">{t.columns.date}</th>
                <th className="py-1 pr-3 text-right font-semibold">{t.columns.load}</th>
                <th className="py-1 pr-3 text-right font-semibold">{t.columns.fitness}</th>
                <th className="py-1 pr-3 text-right font-semibold">{t.columns.fatigue}</th>
                <th className="py-1 text-right font-semibold">{t.columns.form}</th>
              </tr>
            </thead>
            <tbody>
              {[...series].reverse().map((d) => (
                <tr key={d.date} className="border-t border-[#e8ebe2] tabular-nums">
                  <td className="py-1 pr-3">{longDate(d.date)}</td>
                  <td className="py-1 pr-3 text-right">{d.load.toFixed(1)}</td>
                  <td className="py-1 pr-3 text-right">{d.ctl.toFixed(1)}</td>
                  <td className="py-1 pr-3 text-right">{d.atl.toFixed(1)}</td>
                  <td className="py-1 text-right">{d.tsb.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

// Fitness / fatigue / form (exec-plan 0012). Colors are the validated
// blue/orange pair in .load-viz (index.css), not the app's greens: green
// beside orange fails the colorblind-separation check.
export default function LoadCard({ load }: { load: TrainingLoadOut }) {
  const { m, intlLocale } = useI18n();
  const t = m.load;
  const whole = new Intl.NumberFormat(intlLocale, { maximumFractionDigits: 0 });
  const signed0 = new Intl.NumberFormat(intlLocale, { maximumFractionDigits: 0, signDisplay: "exceptZero" });
  const signed1 = new Intl.NumberFormat(intlLocale, {
    minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero",
  });
  // The server's short-history note is English; the localized notice below
  // replaces it. The other notes (missing FTP/LTHR, estimated load) are shown
  // as the server wrote them until they carry codes we can translate.
  const notes = load.notes.filter((note) => !/^Only \d+ day/.test(note));

  return (
    <section className="surface load-viz mb-12 p-5 sm:p-6" aria-labelledby="load-heading">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="eyebrow mb-2">{t.eyebrow}</p>
          <h2 id="load-heading" className="section-title">{t.title}</h2>
        </div>
      </div>

      {load.days_of_history === 0 ? (
        <p className="body-muted">{t.empty}</p>
      ) : (
        <>
          {load.confidence !== "ok" && (
            <p className="surface-soft mb-4 p-3 text-sm">{t.buildingBaseline(load.days_of_history)}</p>
          )}
          <div className="mb-5 grid gap-3 sm:grid-cols-3">
            <Tile label={t.fitness} help={t.fitnessHelp} swatch="var(--viz-fitness)" value={whole.format(load.ctl)}
              hint={t.fitnessHint}
              extra={<p className="body-muted mt-1 text-sm">{t.vsLastWeek(signed1.format(load.ramp_rate_7d))}</p>} />
            <Tile label={t.fatigue} help={t.fatigueHelp} swatch="var(--viz-fatigue)" value={whole.format(load.atl)}
              hint={t.fatigueHint} />
            <Tile label={t.form} help={t.formHelp} value={signed0.format(load.tsb)} hint={t.formHint}
              extra={
                <span className="status-pill mt-2" data-tone={FORM_TONE[load.form]}>
                  <span aria-hidden="true">{FORM_GLYPH[load.form]}</span>
                  {t.formLabel[load.form]}
                </span>
              } />
          </div>
          <LoadChart series={load.series} />
          {notes.length > 0 && (
            <ul className="body-muted mt-4 list-disc space-y-1 pl-5 text-sm">
              {notes.map((note) => <li key={note}>{note}</li>)}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
