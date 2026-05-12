import asyncio
from pathlib import Path

import typer

from coach.config import get_config
from coach.log import configure_logging

app = typer.Typer(name="coach", help="Soft Floyd — Personal AI Cycling Coach", no_args_is_help=True)


@app.callback()
def main(ctx: typer.Context, verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    cfg = get_config()
    configure_logging("DEBUG" if verbose else cfg.log_level)
    cfg.ensure_dirs()


@app.command()
def login(
    email: str = typer.Option(..., prompt="Garmin email"),
    password: str = typer.Option(..., prompt="Garmin password", hide_input=True),
) -> None:
    """Authenticate with Garmin Connect (MFA-aware). Persists an encrypted token."""
    from coach.ingest.garmin_client import GarminClient

    def mfa_prompt() -> str:
        return typer.prompt("Garmin MFA code")

    client = GarminClient(get_config())
    client.login(email, password, mfa_prompt)
    typer.echo("Login successful. Token saved.")


@app.command()
def backfill(
    days: int = typer.Option(365, "--days", help="How many days of history to import"),
) -> None:
    """Seed the database with historical rides from Garmin Connect."""
    from coach.ingest.backfill import run_backfill

    asyncio.run(run_backfill(get_config(), days=days))


@app.command()
def run() -> None:
    """Start the background poller (and HTTP server in Phase 2)."""
    from coach.ingest.poller import run_poller

    asyncio.run(run_poller(get_config()))


@app.command(name="ingest-fit")
def ingest_fit(path: Path) -> None:
    """Manually ingest a single FIT file (offline fallback)."""
    from coach.ingest.backfill import ingest_single_fit

    asyncio.run(ingest_single_fit(get_config(), path))
    typer.echo(f"Ingested {path}")


if __name__ == "__main__":
    app()
