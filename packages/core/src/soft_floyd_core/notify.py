"""Best-effort macOS desktop notifications.

Deliberately no `pync` dependency (v0's choice) — one `osascript`
subprocess call beats a dependency for a cosmetic feature. This is
garnish, never the contract: `GarminSyncState`/`GET /api/sync/garmin/status`
is what actually answers "is sync healthy," this just nudges the rider.
"""

from __future__ import annotations

import subprocess
import sys

from soft_floyd_core.log import get_logger

log = get_logger(__name__)


def _applescript_string(value: str) -> str:
    """AppleScript string literals are double-quoted, not Python's
    single-quoted repr() — using repr() here produced a syntax error on
    every real notification (caught live: `21:23: syntax error: Expected
    ... but found "'s"`, from `` `soft-floyd garmin-login` `` rendered as
    a Python-repr'd single-quoted string, which osascript can't parse).
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def notify(message: str, *, title: str = "Soft Floyd") -> None:
    if sys.platform != "darwin":
        return
    try:
        script = (
            f"display notification {_applescript_string(message)} "
            f"with title {_applescript_string(title)}"
        )
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
    except Exception as exc:
        log.warning("notify.failed", error=str(exc))
