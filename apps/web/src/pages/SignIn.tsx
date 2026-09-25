import LanguageToggle from "../components/LanguageToggle";
import { useI18n } from "../i18n/I18nProvider";

export default function SignIn() {
  const { m } = useI18n();
  const benefits = [
    ["01", m.auth.benefit1Title, m.auth.benefit1Text],
    ["02", m.auth.benefit2Title, m.auth.benefit2Text],
    ["03", m.auth.benefit3Title, m.auth.benefit3Text],
  ];
  return (
    <main className="signin-page min-h-screen overflow-hidden">
      <div className="page-wrap relative z-10">
        <header className="flex items-center justify-between gap-4 py-3">
          <span className="brand text-sm">{m.auth.brand}</span>
          <LanguageToggle />
        </header>
        <div className="grid gap-12 pb-20 pt-12 lg:grid-cols-[1.1fr_.9fr] lg:items-center lg:gap-20 lg:pt-24">
          <div>
            <p className="eyebrow mb-6">{m.auth.eyebrow}</p>
            <h1 className="display-title max-w-3xl text-[clamp(3.4rem,7vw,6.4rem)] leading-[.99]">
              {m.auth.headline}
            </h1>
            <p className="body-muted mt-8 max-w-xl text-lg leading-relaxed">{m.auth.intro}</p>
            <div className="mt-10 max-w-sm">
              <a href="/api/auth/google/start" className="google-button">
                <span className="google-mark" aria-hidden="true">G</span>
                {m.auth.google}
                <span aria-hidden="true" className="ml-auto text-lg">↗</span>
              </a>
              <p className="body-muted mt-3 text-sm">{m.auth.register}</p>
              <p className="mt-6 flex items-center gap-2 text-xs font-semibold text-[#4b6952]">
                <span aria-hidden="true">✦</span>{m.auth.secure}
              </p>
            </div>
          </div>
          <div className="signin-visual" aria-hidden="true">
            <div className="signin-orbit orbit-one" />
            <div className="signin-orbit orbit-two" />
            <div className="signin-ride-card">
              <div className="flex items-center justify-between">
                <span className="eyebrow">SOFT FLOYD</span>
                <span className="text-2xl text-[#b66c44]">✳</span>
              </div>
              <div className="signin-route mt-8">
                <svg viewBox="0 0 440 220" fill="none" role="presentation">
                  <path d="M9 177C68 183 79 111 135 136C191 161 199 34 262 70C311 98 326 179 431 28" stroke="#dbe5d5" strokeWidth="22" strokeLinecap="round" />
                  <path d="M9 177C68 183 79 111 135 136C191 161 199 34 262 70C311 98 326 179 431 28" stroke="#476c50" strokeWidth="5" strokeLinecap="round" strokeDasharray="1 11" />
                  <circle cx="9" cy="177" r="9" fill="#b66c44" />
                  <circle cx="431" cy="28" r="9" fill="#b66c44" />
                </svg>
              </div>
              <p className="eyebrow mt-6">{m.auth.previewLabel}</p>
              <h2 className="section-title mt-3">{m.auth.previewHeadline}</h2>
              <p className="body-muted mt-4 leading-relaxed">{m.auth.previewBody}</p>
            </div>
          </div>
        </div>
        <section className="grid gap-4 border-t border-[#d6e0d3] py-8 md:grid-cols-3 md:gap-8">
          {benefits.map(([number, title, body]) => (
            <article key={number} className="py-3">
              <span className="eyebrow text-[#ae6845]">{number} /</span>
              <h2 className="mt-3 font-serif text-2xl text-[#243e2c]">{title}</h2>
              <p className="body-muted mt-2 text-sm leading-relaxed">{body}</p>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
