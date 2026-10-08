import { useEffect, useRef, useState } from "react";

import type { NavView } from "./AppNavigation";
import { useI18n } from "../i18n/I18nProvider";

const steps = [
  { view: "dashboard", target: "overview", copy: "overview" },
  { view: "dashboard", target: "connections", copy: "connections" },
  { view: "training", target: "training", copy: "training" },
  { view: "training", target: "nav-coach", copy: "coach" },
  { view: "settings", target: "settings", copy: "settings" },
  { view: "help", target: "help", copy: "help" },
] as const satisfies ReadonlyArray<{ view: NavView; target: string; copy: string }>;

type Spotlight = { top: number; left: number; width: number; height: number };
type Position = { top: number; left: number; width: number };

function visibleTarget(name: string): HTMLElement | null {
  return Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`))
    .find((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    }) ?? null;
}

export default function AppTour({ onNavigate, onClose }: {
  onNavigate: (view: Exclude<NavView, "ride">) => void;
  onClose: () => void;
}) {
  const { m } = useI18n();
  const [index, setIndex] = useState(0);
  const [spotlight, setSpotlight] = useState<Spotlight | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const step = steps[index];
  const copy = m.tour.steps[step.copy];

  useEffect(() => {
    const root = document.getElementById("root");
    if (!root) return;
    const siblings = Array.from(root.children).filter((element) => !element.hasAttribute("data-app-tour")) as HTMLElement[];
    const previous = siblings.map((element) => element.inert);
    siblings.forEach((element) => { element.inert = true; });
    return () => siblings.forEach((element, i) => { element.inert = previous[i]; });
  }, [index]);

  useEffect(() => {
    let frame = 0;
    const measure = () => {
      const target = visibleTarget(step.target);
      const width = Math.min(370, window.innerWidth - 32);
      const cardHeight = cardRef.current?.offsetHeight ?? 250;
      if (!target) {
        setSpotlight(null);
        setPosition({ width, left: (window.innerWidth - width) / 2,
          top: Math.max(16, (window.innerHeight - cardHeight) / 2) });
        return;
      }
      const rect = target.getBoundingClientRect();
      const padding = 6;
      setSpotlight({ top: rect.top - padding, left: rect.left - padding,
        width: rect.width + padding * 2, height: rect.height + padding * 2 });
      const below = rect.bottom + 18;
      const above = rect.top - cardHeight - 18;
      const top = below + cardHeight <= window.innerHeight - 16 ? below
        : above >= 16 ? above : Math.max(16, (window.innerHeight - cardHeight) / 2);
      const left = Math.min(Math.max(16, rect.left + rect.width / 2 - width / 2), window.innerWidth - width - 16);
      setPosition({ top, left, width });
    };
    const scheduleMeasure = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    const target = visibleTarget(step.target);
    target?.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
    scheduleMeasure();
    window.addEventListener("resize", scheduleMeasure);
    window.addEventListener("scroll", scheduleMeasure, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", scheduleMeasure);
      window.removeEventListener("scroll", scheduleMeasure, true);
    };
  }, [index]);

  useEffect(() => { cardRef.current?.focus(); }, [index]);

  function move(next: number) {
    if (next >= steps.length) { onClose(); return; }
    onNavigate(steps[next].view);
    setSpotlight(null);
    setPosition(null);
    setIndex(next);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
    if (event.key !== "Tab") return;
    const buttons = Array.from(cardRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
    if (!buttons.length) return;
    const first = buttons[0];
    const last = buttons[buttons.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === cardRef.current)) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first.focus();
    }
  }

  return <div className="app-tour-layer" data-app-tour data-target={Boolean(spotlight)}>
    {spotlight && <div className="app-tour-spotlight" aria-hidden="true" style={spotlight} />}
    <div className="app-tour-card surface" role="dialog" aria-modal="true" aria-labelledby="app-tour-title"
      aria-describedby="app-tour-description" tabIndex={-1} ref={cardRef} onKeyDown={onKeyDown}
      style={position ?? { visibility: "hidden" }}>
      <div className="flex items-start justify-between gap-4">
        <p className="eyebrow">{m.tour.progress(index + 1, steps.length)}</p>
        <button className="text-button text-sm" onClick={onClose}>{m.tour.skip}</button>
      </div>
      <h2 id="app-tour-title" className="section-title mt-4">{copy.title}</h2>
      <p id="app-tour-description" className="body-muted mt-3 leading-relaxed">{copy.body}</p>
      <div className="mt-6 flex justify-between gap-3">
        <button className="secondary-button" onClick={() => move(index - 1)} disabled={index === 0}>{m.tour.back}</button>
        <button className="primary-button" onClick={() => move(index + 1)}>{index === steps.length - 1 ? m.tour.finish : m.tour.next}</button>
      </div>
    </div>
  </div>;
}
