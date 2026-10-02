import LanguageToggle from "./LanguageToggle";
import { useI18n } from "../i18n/I18nProvider";

export type NavView = "dashboard" | "training" | "coach" | "settings" | "profile" | "help" | "ride";

export default function AppNavigation({ view, coachReady, onNavigate }: {
  view: NavView;
  coachReady: boolean;
  onNavigate: (view: Exclude<NavView, "ride">) => void;
}) {
  const { m } = useI18n();
  const primary = [
    { view: "dashboard" as const, label: m.navigation.home, icon: "⌁" },
    { view: "training" as const, label: m.navigation.training, icon: "◉" },
    { view: "coach" as const, label: m.navigation.coach, icon: "✳" },
  ];
  return <>
    <header className="app-navigation">
      <div className="app-navigation-inner">
        <button className="nav-brand" onClick={() => onNavigate("dashboard")} aria-label={m.navigation.home}>
          <span className="brand-symbol" aria-hidden="true">✳</span>
          <span>SOFT FLOYD</span>
        </button>
        <nav className="desktop-nav" aria-label={m.navigation.primaryAria}>
          {primary.map((item) => <button key={item.view} className="nav-link"
            data-active={(view === "ride" ? "dashboard" : view) === item.view}
            aria-current={(view === "ride" ? "dashboard" : view) === item.view ? "page" : undefined}
            disabled={item.view === "coach" && !coachReady}
            aria-label={item.view === "coach" && !coachReady ? `${item.label}. ${m.dashboard.coachHint}` : undefined}
            title={item.view === "coach" && !coachReady ? m.dashboard.coachHint : undefined}
            onClick={() => onNavigate(item.view)}>{item.label}</button>)}
        </nav>
        <div className="nav-utilities">
          <button className="nav-utility" data-active={view === "settings"} onClick={() => onNavigate("settings")}>{m.navigation.settings}</button>
          <button className="nav-utility" data-active={view === "help"} onClick={() => onNavigate("help")}>{m.navigation.help}</button>
          <button className="nav-utility" data-active={view === "profile"} onClick={() => onNavigate("profile")}>{m.auth.profile}</button>
          <LanguageToggle />
        </div>
      </div>
    </header>
    <nav className="mobile-nav" aria-label={m.navigation.primaryAria}>
      {primary.map((item) => <button key={item.view} className="mobile-nav-link"
        data-active={(view === "ride" ? "dashboard" : view) === item.view}
        aria-current={(view === "ride" ? "dashboard" : view) === item.view ? "page" : undefined}
        disabled={item.view === "coach" && !coachReady}
        aria-label={item.view === "coach" && !coachReady ? `${item.label}. ${m.dashboard.coachHint}` : undefined}
        title={item.view === "coach" && !coachReady ? m.dashboard.coachHint : undefined}
        onClick={() => onNavigate(item.view)}>
        <span className="mobile-nav-icon" aria-hidden="true">{item.icon}</span>{item.label}
      </button>)}
    </nav>
  </>;
}
