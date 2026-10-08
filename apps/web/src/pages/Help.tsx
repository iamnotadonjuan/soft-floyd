import type { NavView } from "../components/AppNavigation";
import { useI18n } from "../i18n/I18nProvider";

export default function Help({ onBack, onNavigate, onOpenConnections, onReopenGuide, onReplayTour }: {
  onBack: () => void;
  onNavigate?: (view: Exclude<NavView, "ride" | "help">) => void;
  onOpenConnections?: () => void;
  onReopenGuide?: () => void;
  onReplayTour?: () => void;
}) {
  const { m } = useI18n();
  const t = m.help;
  const screens = [t.screens.overview, t.screens.training, t.screens.coach, t.screens.settings];

  return (
    <main className="app-shell">
      <div className="page-wrap">
        {!onNavigate && <button className="text-button mb-7" onClick={onBack}>{m.common.back}</button>}
        <div className="page-intro mb-10 max-w-2xl" data-tour="help">
          <p className="eyebrow mb-3">{t.eyebrow}</p>
          <h1 className="display-title">{t.title}</h1>
          <p className="body-muted mt-4">{t.intro}</p>
        </div>

        <section className="surface mb-10 p-5 sm:p-8" aria-labelledby="guide-heading">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 id="guide-heading" className="section-title">{t.guideTitle}</h2>
              <p className="body-muted mt-2 max-w-2xl">{t.guideIntro}</p>
            </div>
            <div className="flex flex-wrap gap-3">
              {onReplayTour && <button className="secondary-button" onClick={onReplayTour}>{m.tour.replay}</button>}
              {onReopenGuide && <button className="secondary-button" onClick={onReopenGuide}>{t.reopenGuide}</button>}
            </div>
          </div>
          <ol className="mt-6 grid gap-3 md:grid-cols-3">
            {([t.connect, t.ride, t.session] as const).map((step, index) => (
              <li key={step.title} className="surface-soft p-5">
                <span className="eyebrow">0{index + 1}</span>
                <h3 className="mt-3 text-lg font-semibold">{step.title}</h3>
                <p className="body-muted mt-2 text-sm leading-relaxed">{step.body}</p>
                {onNavigate && <button className="text-button mt-4 text-sm" onClick={() => {
                  if (index === 0) onOpenConnections?.();
                  else onNavigate(index === 1 ? "dashboard" : "training");
                }}>{step.action} →</button>}
              </li>
            ))}
          </ol>
        </section>

        <section className="mb-10" aria-labelledby="screens-heading">
          <h2 id="screens-heading" className="section-title mb-5">{t.screensTitle}</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {screens.map((screen) => <div key={screen.title} className="surface p-5 sm:p-6">
              <h3 className="text-lg font-semibold">{screen.title}</h3>
              <p className="body-muted mt-2 text-sm leading-relaxed">{screen.body}</p>
            </div>)}
          </div>
        </section>

        <section aria-labelledby="faq-heading">
          <h2 id="faq-heading" className="section-title mb-5">{t.faqTitle}</h2>
          <div className="space-y-3">
            {t.faq.map((item) => <details key={item.question} className="faq-item surface p-5">
              <summary className="font-semibold">{item.question}</summary>
              <p className="body-muted mt-3 max-w-3xl leading-relaxed">{item.answer}</p>
            </details>)}
          </div>
        </section>
      </div>
    </main>
  );
}
