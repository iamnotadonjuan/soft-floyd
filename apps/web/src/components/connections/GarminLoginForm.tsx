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
      setPassword("");
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
      <div className="space-y-3 pt-4">
        <p className="text-sm font-medium">Enter the code Garmin just sent you</p>
        <input
          aria-label="Garmin verification code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="123456"
          className="form-field"
        />
        {error && <p className="notice-error" role="alert">{error}</p>}
        <button
          onClick={handleMfa}
          disabled={submitting || code.trim().length === 0}
          className="primary-button w-full"
        >
          {submitting ? "Verifying…" : "Verify"}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3 pt-4">
      <label className="block"><span className="form-label">Garmin email</span><input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Garmin email"
        className="form-field"
      /></label>
      <label className="block"><span className="form-label">Password</span><input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Garmin password"
        className="form-field"
      /></label>
      {error && <p className="notice-error" role="alert">{error}</p>}
      <button
        onClick={handleLogin}
        disabled={submitting || email.trim().length === 0 || password.length === 0}
        className="primary-button w-full"
      >
        {submitting ? "Connecting…" : "Connect Garmin"}
      </button>
      <p className="body-muted text-xs">
        Your password goes only to your local Soft Floyd server for this sign-in.
      </p>
    </div>
  );
}
