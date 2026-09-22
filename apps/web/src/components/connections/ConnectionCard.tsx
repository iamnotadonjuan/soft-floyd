import { useState } from "react";

import { api } from "../../api/client";
import type { ConnectionOut } from "../../api/types";
import GarminLoginForm from "./GarminLoginForm";

const STATUS_COPY: Record<ConnectionOut["status"], string> = {
  connected: "Connected",
  disconnected: "Not connected",
  reauth_required: "Needs sign-in again",
  rate_limited: "Rate limited — try again soon",
  error: "Error",
};

const STATUS_DOT: Record<ConnectionOut["status"], string> = {
  connected: "bg-green-500",
  disconnected: "bg-neutral-300",
  reauth_required: "bg-amber-500",
  rate_limited: "bg-amber-500",
  error: "bg-red-500",
};

interface Props {
  connection: ConnectionOut;
  onChanged: (connection: ConnectionOut) => void;
}

export default function ConnectionCard({ connection, onChanged }: Props) {
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
    <div className="rounded-md border border-neutral-200 p-4">
      <div className="flex items-center justify-between">
        <span className="font-medium">{connection.display_name}</span>
        <span className="flex items-center gap-1.5 text-sm text-neutral-500">
          <span className={`h-2 w-2 rounded-full ${STATUS_DOT[connection.status]}`} />
          {STATUS_COPY[connection.status]}
        </span>
      </div>

      {connection.detail && <p className="mt-1 text-xs text-neutral-400">{connection.detail}</p>}
      {connection.last_error && connection.status !== "connected" && (
        <p className="mt-1 text-xs text-red-600">{connection.last_error}</p>
      )}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}

      {connection.status === "connected" && (
        <button
          onClick={handleDisconnect}
          disabled={disconnecting}
          className="mt-3 text-sm text-neutral-500 underline disabled:opacity-40"
        >
          Disconnect
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
