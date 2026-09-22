"""Connected apps: a provider-shaped read model over whatever sync state
already exists, so the UI has one generic "Connected apps" section
instead of Garmin-specific chrome. Garmin is the only provider today —
its state already lives in GarminSyncState (exec-plan 0002); this module
adds no new table, just a view over it plus GarminClient.has_token().

Adding a second provider later (Strava, Wahoo) means adding a sibling
function here and a row to list_connections's result — the web UI
renders the list generically and never hardcodes "garmin" outside the
one login form component. See docs/product-specs/connected-apps.md.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from soft_floyd_core.activities.service import get_sync_status
from soft_floyd_core.config import Settings

ConnectionStatus = Literal["connected", "disconnected", "reauth_required", "rate_limited", "error"]


class ConnectionOut(BaseModel):
    provider: str
    display_name: str
    status: ConnectionStatus
    last_sync_at: dt.datetime | None
    last_error: str | None  # human-readable only — never a token. See docs/SECURITY.md.
    supports_login_in_app: bool
    detail: str | None


def _garmin_connection(session: Session, settings: Settings) -> ConnectionOut:
    sync = get_sync_status(session, settings)

    if not sync.authenticated:
        status: ConnectionStatus = "disconnected"
    elif sync.last_status == "reauth_required":
        status = "reauth_required"
    elif sync.last_status == "rate_limited":
        status = "rate_limited"
    elif sync.last_status == "error":
        status = "error"
    else:
        # Covers "ok" and "never" (a fresh login that hasn't synced yet) —
        # both mean the token is good and sync will proceed on its own.
        status = "connected"

    detail = f"Polls every {settings.poll_interval_minutes} min" if status == "connected" else None

    return ConnectionOut(
        provider="garmin",
        display_name="Garmin Connect",
        status=status,
        last_sync_at=sync.last_sync_at,
        last_error=sync.last_error,
        supports_login_in_app=True,
        detail=detail,
    )


def list_connections(session: Session, settings: Settings) -> list[ConnectionOut]:
    return [_garmin_connection(session, settings)]
