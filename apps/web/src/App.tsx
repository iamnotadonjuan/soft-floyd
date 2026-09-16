import { useEffect, useState } from "react";

import { api } from "./api/client";
import { hasCompletedOnboarding, type ProfileOut } from "./api/types";
import Dashboard from "./pages/Dashboard";
import Onboarding from "./pages/Onboarding";

export default function App() {
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return <Dashboard profile={profile} />;
}
