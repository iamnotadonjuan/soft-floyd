import { useEffect, useState } from "react";

import { api } from "./api/client";
import { hasCompletedOnboarding, type ProfileOut } from "./api/types";
import Dashboard from "./pages/Dashboard";
import Onboarding from "./pages/Onboarding";
import Settings from "./pages/Settings";

// Two destinations don't justify react-router yet — see docs/FRONTEND.md
// ("reach for a library only when the scaffold's approach visibly
// strains"). A third route is the point to revisit this.
type View = "dashboard" | "settings";

export default function App() {
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("dashboard");

  useEffect(() => {
    api.getProfile().then(setProfile).catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-md px-4 py-12 text-red-600">
        Couldn't reach the server: {error}
      </div>
    );
  }

  if (!profile) {
    return <div className="mx-auto max-w-md px-4 py-12 text-neutral-400">Loading…</div>;
  }

  if (!hasCompletedOnboarding(profile)) {
    return <Onboarding initialProfile={profile} onComplete={setProfile} />;
  }

  if (view === "settings") {
    return (
      <Settings profile={profile} onProfileChange={setProfile} onBack={() => setView("dashboard")} />
    );
  }

  return <Dashboard profile={profile} onOpenSettings={() => setView("settings")} />;
}
