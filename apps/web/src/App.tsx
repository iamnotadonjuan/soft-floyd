import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "./api/client";
import { hasCompletedOnboarding, type AccountOut, type ProfileOut } from "./api/types";
import LanguageToggle from "./components/LanguageToggle";
import { useI18n } from "./i18n/I18nProvider";
import Coach from "./pages/Coach";
import Dashboard from "./pages/Dashboard";
import Onboarding from "./pages/Onboarding";
import Settings from "./pages/Settings";
import RideDetail from "./pages/RideDetail";
import Profile from "./pages/Profile";
import SignIn from "./pages/SignIn";

// These are local views; a ride detail keeps the dashboard mounted so
// returning to history preserves loaded pages and keyboard focus.
type View = "dashboard" | "settings" | "ride" | "coach" | "profile";

export default function App() {
  const { m } = useI18n();
  const [account, setAccount] = useState<AccountOut | null | undefined>(undefined);
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("dashboard");
  const [selectedRideId, setSelectedRideId] = useState<number | null>(null);
  const rideListScroll = useRef(0);

  useEffect(() => {
    let active = true;
    api.getMe().then((identity) => {
      if (!active) return;
      setAccount(identity);
      return api.getProfile().then((rider) => { if (active) setProfile(rider); });
    }).catch((reason) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) setAccount(null);
      else setError(String(reason));
    });
    const unauthorized = () => { setAccount(null); setProfile(null); };
    window.addEventListener("soft-floyd-unauthorized", unauthorized);
    return () => { active = false; window.removeEventListener("soft-floyd-unauthorized", unauthorized); };
  }, []);

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

  if (view === "profile") {
    return <Profile account={account} onBack={() => setView("dashboard")}
      onSignOut={() => { setAccount(null); setProfile(null); setView("dashboard"); }} />;
  }

  if (!hasCompletedOnboarding(profile)) {
    return <Onboarding initialProfile={profile} onComplete={setProfile}
      onOpenProfile={() => setView("profile")} />;
  }

  if (view === "settings") {
    return (
      <Settings profile={profile} onProfileChange={setProfile} onBack={() => setView("dashboard")}
        onOpenProfile={() => setView("profile")} />
    );
  }

  if (view === "coach") {
    return <Coach onBack={() => setView("dashboard")} />;
  }

  return <>
    <div hidden={view === "ride"}>
      <Dashboard
        profile={profile}
        onOpenSettings={() => setView("settings")}
        onOpenProfile={() => setView("profile")}
        onOpenCoach={() => { setView("coach"); window.scrollTo(0, 0); }}
        onOpenRide={(id) => {
          rideListScroll.current = window.scrollY;
          setSelectedRideId(id);
          setView("ride");
          window.scrollTo(0, 0);
        }}
      />
    </div>
    {view === "ride" && selectedRideId !== null &&
      <RideDetail id={selectedRideId} onBack={() => {
        setView("dashboard");
        requestAnimationFrame(() => {
          window.scrollTo(0, rideListScroll.current);
          document.getElementById(`ride-${selectedRideId}`)?.focus({ preventScroll: true });
        });
      }} />}
  </>;
}
