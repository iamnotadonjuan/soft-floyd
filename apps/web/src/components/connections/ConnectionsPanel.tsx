import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { ConnectionOut } from "../../api/types";
import ConnectionCard from "./ConnectionCard";

// Fetches and renders every connected app generically — today that's
// just Garmin, but adding a provider means adding a row to
// connections/service.py's list_connections, not touching this component.
export default function ConnectionsPanel() {
  const [connections, setConnections] = useState<ConnectionOut[] | null>(null);

  useEffect(() => {
    api.listConnections().then(setConnections);
  }, []);

  function handleChanged(updated: ConnectionOut) {
    setConnections((prev) =>
      (prev ?? []).map((c) => (c.provider === updated.provider ? updated : c)),
    );
  }

  if (connections === null) {
    return <p className="text-sm text-neutral-400">Loading connected apps…</p>;
  }

  return (
    <div className="space-y-3">
      {connections.map((connection) => (
        <ConnectionCard key={connection.provider} connection={connection} onChanged={handleChanged} />
      ))}
    </div>
  );
}
