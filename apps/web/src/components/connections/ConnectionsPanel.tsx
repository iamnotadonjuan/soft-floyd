import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { ConnectionOut } from "../../api/types";
import { useI18n } from "../../i18n/I18nProvider";
import ConnectionCard from "./ConnectionCard";

// Fetches and renders every connected app generically — today that's
// just Garmin, but adding a provider means adding a row to
// connections/service.py's list_connections, not touching this component.
export default function ConnectionsPanel() {
  const { m } = useI18n();
  const [connections, setConnections] = useState<ConnectionOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.listConnections()
      .then((items) => { if (active) setConnections(items); })
      .catch((reason) => { if (active) setError(String(reason)); });
    return () => { active = false; };
  }, []);

  function handleChanged(updated: ConnectionOut) {
    setConnections((prev) =>
      (prev ?? []).map((c) => (c.provider === updated.provider ? updated : c)),
    );
  }

  if (error) return <p className="notice-error" role="alert">{m.connections.loadError(error)}</p>;
  if (connections === null) return <p className="body-muted text-sm">{m.connections.loading}</p>;

  return (
    <div className="space-y-3">
      {connections.length === 0 && <p className="body-muted text-sm">{m.common.noAppsYet}</p>}
      {connections.map((connection) => (
        <ConnectionCard key={connection.provider} connection={connection} onChanged={handleChanged} />
      ))}
    </div>
  );
}
