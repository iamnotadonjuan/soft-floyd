import { useState } from "react";

import { api } from "../../api/client";
import type { ConnectionOut } from "../../api/types";
import { useI18n } from "../../i18n/I18nProvider";
import GarminLoginForm from "./GarminLoginForm";

const STATUS_TONE: Record<ConnectionOut["status"], string> = {
  connected: "good", disconnected: "neutral", reauth_required: "warning",
  rate_limited: "warning", error: "error",
};

interface Props {
  connection: ConnectionOut;
  onChanged: (connection: ConnectionOut) => void;
}

export default function ConnectionCard({ connection, onChanged }: Props) {
  const { m, intlLocale } = useI18n();
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refreshThisProvider() {
    const connections = await api.listConnections();
    const refreshed = connections.find((c) => c.provider === connection.provider);
    if (refreshed) onChanged(refreshed);
  }

  async function handleDisconnect() {
    setDisconnecting(true);
    setError(null);
    try {
      await api.garminDisconnect();
      await refreshThisProvider();
    } catch (e) {
      setError(String(e));
    } finally {
      setDisconnecting(false);
    }
  }

  const needsLogin = connection.status === "disconnected" || connection.status === "reauth_required";

  return (
    <div className="surface-soft p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-[#243e2c]">{connection.display_name}</span>
        <span className="status-pill" data-tone={STATUS_TONE[connection.status]}>
          {m.connections.status[connection.status]}
        </span>
      </div>

      {connection.detail && <p className="body-muted mt-2 text-sm">{connection.detail}</p>}
      {connection.last_sync_at && <p className="body-muted mt-1 text-sm">{m.connections.lastChecked(new Date(connection.last_sync_at).toLocaleString(intlLocale))}</p>}
      {connection.last_error && connection.status !== "connected" && (
        <p className="notice-error mt-3" role="alert">{connection.last_error}</p>
      )}
      {error && <p className="notice-error mt-3" role="alert">{error}</p>}

      {connection.status === "connected" && (
        <button
          onClick={handleDisconnect}
          disabled={disconnecting}
          className="text-button mt-4 text-sm disabled:opacity-40"
        >
          {m.connections.disconnect}
        </button>
      )}

      {/* Garmin is the only provider with a browser login flow today.
          Adding a second provider means a sibling *LoginForm component
          and another branch here — this is the one place that knows
          provider names, everything else in this panel is generic. See
          docs/product-specs/connected-apps.md. */}
      {needsLogin && connection.provider === "garmin" && connection.supports_login_in_app && (
        <div className="mt-3">
          <GarminLoginForm onConnected={refreshThisProvider} />
        </div>
      )}
    </div>
  );
}
