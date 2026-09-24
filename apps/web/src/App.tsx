import { useEffect, useRef, useState } from "react";

import { api } from "./api/client";
import { hasCompletedOnboarding, type ProfileOut } from "./api/types";
import Coach from "./pages/Coach";
import Dashboard from "./pages/Dashboard";
import Onboarding from "./pages/Onboarding";
import Settings from "./pages/Settings";
import RideDetail from "./pages/RideDetail";

// These are local views; a ride detail keeps the dashboard mounted so
// returning to history preserves loaded pages and keyboard focus.
type View = "dashboard" | "settings" | "ride" | "coach";

export default function App() {
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("dashboard");
  const [selectedRideId, setSelectedRideId] = useState<number | null>(null);
  const rideListScroll = useRef(0);

  useEffect(() => {
    api.getProfile().then(setProfile).catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return (
      <div className="app-shell page-wrap text-red-700">
        Couldn't reach the server: {error}
      </div>
    );
  }

  if (!profile) {
    return <div className="app-shell page-wrap body-muted">Loading your ride journal…</div>;
  }

  if (!hasCompletedOnboarding(profile)) {
    return <Onboarding initialProfile={profile} onComplete={setProfile} />;
  }

  if (view === "settings") {
    return (
      <Settings profile={profile} onProfileChange={setProfile} onBack={() => setView("dashboard")} />
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
