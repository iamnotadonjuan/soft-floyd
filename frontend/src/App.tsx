import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Nav from "./components/Nav";
import { useProfile } from "./lib/useProfile";
import ActivityDetail from "./pages/ActivityDetail";
import ActivityList from "./pages/ActivityList";
import Onboarding from "./pages/Onboarding";
import Settings from "./pages/Settings";

function AppInner() {
  const { profile } = useProfile();

  // Loading — wait before deciding where to send the user
  if (profile === undefined) {
    return (
      <div className="flex items-center justify-center min-h-screen text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Nav />
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Routes>
          <Route
            path="/"
            element={
              profile === null ? (
                <Navigate to="/onboarding" replace />
              ) : (
                <Navigate to="/activities" replace />
              )
            }
          />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/activities" element={<ActivityList />} />
          <Route path="/activities/:id" element={<ActivityDetail />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppInner />
    </BrowserRouter>
  );
}
