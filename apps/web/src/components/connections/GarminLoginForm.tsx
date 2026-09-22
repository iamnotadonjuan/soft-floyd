import { useState } from "react";

import { ApiError, api } from "../../api/client";

type Stage = "credentials" | "mfa";

interface Props {
  onConnected: () => void;
}

// The one provider-specific login form — see ConnectionCard's comment on
// why it's the single seam that knows the provider's name. Password
// lives only in this component's state and the POST body; it is never
// written to browser storage. See docs/SECURITY.md.
export default function GarminLoginForm({ onConnected }: Props) {
  const [stage, setStage] = useState<Stage>("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin() {
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.garminLogin(email, password);
      if (result.state === "mfa_required") {
        setStage("mfa");
      } else {
        onConnected();
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleMfa() {
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.garminSubmitMfa(code);
      if (result.state === "connected") onConnected();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (stage === "mfa") {
    return (
      <div className="space-y-2 rounded-md border border-neutral-200 bg-neutral-50 p-3">
        <p className="text-sm font-medium">Enter the code Garmin just sent you</p>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="123456"
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
        />
        {error && <p className="text-xs text-red-600">{error}</p>}
        <button
          onClick={handleMfa}
          disabled={submitting || code.trim().length === 0}
          className="w-full rounded-md bg-neutral-900 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {submitting ? "Verifying…" : "Verify"}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-md border border-neutral-200 bg-neutral-50 p-3">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Garmin email"
        className="w-full rounded-md border border-neutral-300 px-3 py-2"
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Garmin password"
        className="w-full rounded-md border border-neutral-300 px-3 py-2"
      />
      {error && <p className="text-xs text-red-600">{error}</p>}
      <button
        onClick={handleLogin}
        disabled={submitting || email.trim().length === 0 || password.length === 0}
        className="w-full rounded-md bg-neutral-900 py-2 text-sm font-medium text-white disabled:opacity-40"
      >
        {submitting ? "Connecting…" : "Connect Garmin"}
      </button>
      <p className="text-xs text-neutral-400">
        Sent directly to your own local server and never stored — see docs/SECURITY.md.
      </p>
    </div>
  );
}
