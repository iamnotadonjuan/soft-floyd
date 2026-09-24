import { useState } from "react";

import { ApiError, api } from "../../api/client";
import { useI18n } from "../../i18n/I18nProvider";

type Stage = "credentials" | "mfa";

interface Props {
  onConnected: () => void;
}

// The one provider-specific login form — see ConnectionCard's comment on
// why it's the single seam that knows the provider's name. Password
// lives only in this component's state and the POST body; it is never
// written to browser storage. See docs/SECURITY.md.
export default function GarminLoginForm({ onConnected }: Props) {
  const { m } = useI18n();
  const g = m.connections.garmin;
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
        <p className="text-sm font-medium">{g.codePrompt}</p>
        <input
          aria-label={g.codeAria}
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
          {submitting ? g.verifying : g.verify}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3 pt-4">
      <label className="block"><span className="form-label">{g.email}</span><input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder={g.email}
        className="form-field"
      /></label>
      <label className="block"><span className="form-label">{g.password}</span><input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder={g.passwordPlaceholder}
        className="form-field"
      /></label>
      {error && <p className="notice-error" role="alert">{error}</p>}
      <button
        onClick={handleLogin}
        disabled={submitting || email.trim().length === 0 || password.length === 0}
        className="primary-button w-full"
      >
        {submitting ? g.connecting : g.connect}
      </button>
      <p className="body-muted text-xs">
        {g.privacy}
      </p>
    </div>
  );
}
