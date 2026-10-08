import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "./api/client";
import { hasCompletedOnboarding, type AccountOut, type ProfileOut } from "./api/types";
import LanguageToggle from "./components/LanguageToggle";
import AppNavigation, { type NavView } from "./components/AppNavigation";
import AppTour from "./components/AppTour";
import { isGuidePending, setGuidePending } from "./components/firstUseStorage";
import { useI18n } from "./i18n/I18nProvider";
import Coach from "./pages/Coach";
import Dashboard from "./pages/Dashboard";
import Onboarding from "./pages/Onboarding";
import Settings from "./pages/Settings";
import RideDetail from "./pages/RideDetail";
import Profile from "./pages/Profile";
import SignIn from "./pages/SignIn";
import Training from "./pages/Training";
import Help from "./pages/Help";

// These are local views; a ride detail keeps the dashboard mounted so
// returning to history preserves loaded pages and keyboard focus.
type View = NavView;

export default function App() {
  const { m } = useI18n();
  const [account, setAccount] = useState<AccountOut | null | undefined>(undefined);
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("dashboard");
  const [coachReady, setCoachReady] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  const [selectedRideId, setSelectedRideId] = useState<number | null>(null);
  const rideListScroll = useRef(0);
  const previousView = useRef<Exclude<View, "help">>("dashboard");
  const tourOrigin = useRef<Exclude<View, "ride">>("dashboard");

  useEffect(() => {
    let active = true;
    api.getMe().then((identity) => {
      if (!active) return;
      setAccount(identity);
      setShowGuide(isGuidePending(identity.id));
      return api.getProfile().then((rider) => { if (active) setProfile(rider); });
    }).catch((reason) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) setAccount(null);
      else setError(String(reason));
    });
    const unauthorized = () => { setAccount(null); setProfile(null); setShowGuide(false); setTourOpen(false); };
    window.addEventListener("soft-floyd-unauthorized", unauthorized);
    return () => { active = false; window.removeEventListener("soft-floyd-unauthorized", unauthorized); };
  }, []);

  useEffect(() => {
    if (!account || !profile || !hasCompletedOnboarding(profile)) return;
    let active = true;
    api.listConnections()
      .then((items) => { if (active) setCoachReady(items.some((item) => item.status === "connected")); })
      .catch(() => { if (active) setCoachReady(false); });
    return () => { active = false; };
  }, [account, profile, view]);

  function navigate(next: Exclude<View, "ride">) {
    if (next === "help" && view !== "help") previousView.current = view;
    if (view === "ride" && next === "dashboard") {
      setView("dashboard");
      requestAnimationFrame(() => {
        window.scrollTo(0, rideListScroll.current);
        document.getElementById(`ride-${selectedRideId}`)?.focus({ preventScroll: true });
      });
      return;
    }
    setView(next);
    window.scrollTo(0, 0);
  }

  function openConnections() {
    navigate("settings");
    requestAnimationFrame(() => document.getElementById("settings-connections")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function refreshCoachReady() {
    api.listConnections()
      .then((items) => setCoachReady(items.some((item) => item.status === "connected")))
      .catch(() => setCoachReady(false));
  }

  function finishOnboarding(updated: ProfileOut) {
    setGuidePending(account!.id, true);
    setShowGuide(true);
    setProfile(updated);
    setView("dashboard");
    tourOrigin.current = "dashboard";
    setTourOpen(true);
  }

  function dismissGuide() {
    setGuidePending(account!.id, false);
    setShowGuide(false);
  }

  function reopenGuide() {
    setGuidePending(account!.id, true);
    setShowGuide(true);
    navigate("dashboard");
  }

  function replayTour() {
    tourOrigin.current = view === "ride" ? "dashboard" : view;
    setView("dashboard");
    setTourOpen(true);
  }

  function closeTour() {
    setTourOpen(false);
    navigate(tourOrigin.current);
    requestAnimationFrame(() => document.querySelector<HTMLElement>(
      tourOrigin.current === "help" ? "[data-tour-replay]" : ".nav-brand",
    )?.focus());
  }

  if (account === undefined && !error) {
    return <div className="app-shell page-wrap body-muted">{m.auth.loading}</div>;
  }

  if (account === null) return <SignIn />;

  if (error) {
    return (
      <div className="app-shell page-wrap">
        <div className="mb-6 flex justify-end"><LanguageToggle /></div>
        <p className="text-red-700">{m.app.serverError(error)}</p>
      </div>
    );
  }

  if (account === undefined) {
    return <div className="app-shell page-wrap body-muted">{m.auth.loading}</div>;
  }

  if (!profile) {
    return <div className="app-shell page-wrap body-muted">{m.app.loading}</div>;
  }

  if (!hasCompletedOnboarding(profile) && view === "profile") {
    return <Profile account={account} onBack={() => setView("dashboard")}
      showLanguageToggle
      onSignOut={() => { setAccount(null); setProfile(null); setShowGuide(false); setTourOpen(false); setView("dashboard"); }} />;
  }

  if (!hasCompletedOnboarding(profile)) {
    return <Onboarding initialProfile={profile} onComplete={finishOnboarding}
      onOpenProfile={() => setView("profile")} />;
  }

  return <>
    <AppNavigation view={view} coachReady={coachReady} onNavigate={navigate} />
    {view === "profile" && <Profile account={account} onBack={() => navigate("dashboard")}
      onSignOut={() => { setAccount(null); setProfile(null); setShowGuide(false); setTourOpen(false); setView("dashboard"); }} />}
    {view === "settings" && <Settings profile={profile} onProfileChange={setProfile}
      onConnectionsChange={refreshCoachReady} />}
    {view === "help" && <Help onBack={() => navigate(previousView.current === "ride" ? "dashboard" : previousView.current)}
      onNavigate={navigate} onOpenConnections={openConnections} onReopenGuide={reopenGuide} onReplayTour={replayTour} />}
    {view === "coach" && <Coach />}
    {view === "training" && <Training profile={profile} onProfileChange={setProfile} />}
    {(view === "dashboard" || view === "ride") && <div hidden={view === "ride"}>
      <Dashboard
        profile={profile}
        onOpenSettings={openConnections}
        onOpenCoach={() => navigate("coach")}
        onOpenTraining={() => navigate("training")}
        showGuide={showGuide}
        onDismissGuide={dismissGuide}
        onOpenHelp={() => navigate("help")}
        onOpenRide={(id) => {
          rideListScroll.current = window.scrollY;
          setSelectedRideId(id);
          setView("ride");
          window.scrollTo(0, 0);
        }}
      />
    </div>}
    {view === "ride" && selectedRideId !== null &&
      <RideDetail id={selectedRideId} onBack={() => {
        setView("dashboard");
        requestAnimationFrame(() => {
          window.scrollTo(0, rideListScroll.current);
          document.getElementById(`ride-${selectedRideId}`)?.focus({ preventScroll: true });
        });
      }} />}
    {tourOpen && <AppTour onNavigate={(next) => { setView(next); window.scrollTo(0, 0); }} onClose={closeTour} />}
  </>;
}
