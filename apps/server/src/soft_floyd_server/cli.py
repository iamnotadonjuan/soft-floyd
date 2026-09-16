"""`soft-floyd serve` — the only entrypoint. Binds to 127.0.0.1 by default;
see docs/SECURITY.md before ever changing that default.
"""

from __future__ import annotations

import typer
import uvicorn
from soft_floyd_core.config import get_settings
from soft_floyd_core.log import configure_logging

app = typer.Typer(name="soft-floyd", add_completion=False)


@app.callback()
def _callback() -> None:
    """Soft Floyd — a sensor-aware AI cycling coach."""
    # A no-op callback keeps `serve` an explicit subcommand. Without it,
    # Typer collapses a single-command app so `soft-floyd serve` fails
    # with "unexpected extra argument(s)" — see fastapi/typer#119.


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address. Keep this loopback-only."),
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(False, help="Autoreload on source changes (dev only)."),
) -> None:
    """Start the FastMCP + FastAPI server."""
    settings = get_settings()
    configure_logging(settings.log_level)
    uvicorn.run("soft_floyd_server.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
