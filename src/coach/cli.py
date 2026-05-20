import asyncio
from pathlib import Path

import typer

from coach.config import get_config
from coach.ingest.garmin_client import GarminApiError, GarminRateLimited, ReauthRequired
from coach.log import configure_logging

app = typer.Typer(name="coach", help="Soft Floyd — Personal AI Cycling Coach", no_args_is_help=True)


@app.callback()
def main(ctx: typer.Context, verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    cfg = get_config()
    configure_logging("DEBUG" if verbose else cfg.log_level)
    cfg.ensure_dirs()


@app.command()
def login(
    email: str | None = typer.Option(None, "--email", "-e", help="Garmin account email"),
    password: str | None = typer.Option(
        None,
        "--password",
        help="Garmin account password. Omit this to use a hidden prompt.",
        hide_input=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Ignore any saved token and start a fresh Garmin SSO login.",
    ),
) -> None:
    """Authenticate with Garmin Connect (MFA-aware). Persists an encrypted token."""
    from coach.ingest.garmin_client import GarminClient

    def mfa_prompt() -> str:
        return typer.prompt("Garmin MFA code")

    cfg = get_config()
    client = GarminClient(cfg)

    if cfg.garth_token_path.exists() and not force:
        try:
            client.load_from_disk()
        except ReauthRequired:
            typer.echo("Saved Garmin token could not be loaded; starting a new login.", err=True)
        except GarminApiError as exc:
            _exit_with_garmin_error(exc)
        else:
            typer.echo(
                "Saved Garmin token found. Use `coach login --force` to replace it with a fresh login."
            )
            return

    email = email or typer.prompt("Garmin email")
    password = password or typer.prompt("Garmin password", hide_input=True)

    try:
        client.login(email, password, mfa_prompt)
    except GarminApiError as exc:
        _exit_with_garmin_error(exc)
    typer.echo("Login successful. Token saved.")


@app.command()
def backfill(
    days: int = typer.Option(365, "--days", help="How many days of history to import"),
) -> None:
    """Seed the database with historical rides from Garmin Connect."""
    from coach.ingest.backfill import run_backfill

    try:
        asyncio.run(run_backfill(get_config(), days=days))
    except GarminApiError as exc:
        _exit_with_garmin_error(exc)


@app.command()
def run() -> None:
    """Start the background poller and HTTP server (127.0.0.1:8000)."""
    from uvicorn import Config as UvicornConfig
    from uvicorn import Server

    from coach.ingest.poller import run_poller
    from coach.web.api import create_app

    async def _main() -> None:
        cfg = get_config()
        uv_cfg = UvicornConfig(
            app=create_app(cfg),
            host="127.0.0.1",
            port=8000,
            log_level="warning",
            loop="asyncio",
        )
        server = Server(uv_cfg)
        await asyncio.gather(run_poller(cfg), server.serve())

    asyncio.run(_main())


@app.command(name="ingest-fit")
def ingest_fit(path: Path) -> None:
    """Manually ingest a single FIT file (offline fallback)."""
    from coach.ingest.backfill import ingest_single_fit

    asyncio.run(ingest_single_fit(get_config(), path))
    typer.echo(f"Ingested {path}")


def _exit_with_garmin_error(exc: GarminApiError) -> None:
    typer.secho(str(exc), fg=typer.colors.RED, err=True)
    if isinstance(exc, GarminRateLimited):
        if exc.retry_after_s is not None:
            minutes = max(1, round(exc.retry_after_s / 60))
            typer.echo(f"Garmin sent Retry-After: about {minutes} minute(s).", err=True)
        else:
            typer.echo("Garmin did not send Retry-After; wait before trying again.", err=True)
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
