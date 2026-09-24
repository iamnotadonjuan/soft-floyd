"""`soft-floyd serve` — the only entrypoint. Binds to 127.0.0.1 by default;
see docs/SECURITY.md before ever changing that default.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer
import uvicorn
from openai import OpenAIError
from soft_floyd_core.config import get_settings
from soft_floyd_core.db import make_engine, make_session_factory, session_scope
from soft_floyd_core.garmin.client import GarminClient
from soft_floyd_core.garmin.errors import GarminApiError, GarminRateLimited
from soft_floyd_core.garmin.login import clear_login_block, perform_login
from soft_floyd_core.garmin.sync import run_sync_cycle
from soft_floyd_core.log import configure_logging
from soft_floyd_core.rag import service as rag_service

app = typer.Typer(name="soft-floyd", add_completion=False)
books_app = typer.Typer(help="Import local training books.")
app.add_typer(books_app, name="books")


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


def _exit_with_garmin_error(exc: GarminApiError) -> None:
    typer.secho(str(exc), fg=typer.colors.RED, err=True)
    if isinstance(exc, GarminRateLimited) and exc.retry_after_s:
        typer.secho(f"Retry after {exc.retry_after_s}s.", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


@app.command(name="garmin-login")
def garmin_login(
    email: str = typer.Option(None, help="Defaults to SOFT_FLOYD_GARMIN_EMAIL if set."),
    force: bool = typer.Option(False, help="Replace an existing cached token."),
    verbose: bool = typer.Option(
        False, help="Log garminconnect's login strategy chain at DEBUG level."
    ),
) -> None:
    """Authenticate with Garmin Connect (MFA-aware). The password is
    prompted and never persisted — only the resulting token cache is
    (at settings.garmin_token_dir). See docs/SECURITY.md.

    Refuses locally (no network call) if a prior 429 put login on
    cooldown — see docs/RELIABILITY.md.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    if verbose:
        logging.getLogger("garminconnect").setLevel(logging.DEBUG)
    engine = make_engine(settings.db_path)
    session_factory = make_session_factory(engine)
    client = GarminClient(settings.garmin_token_dir)

    if client.has_token() and not force:
        try:
            client.load()
        except GarminApiError:
            typer.echo("Cached token is no longer valid. Requesting a fresh login.")
        else:
            typer.echo("Already logged in. Use --force to replace the cached token.")
            raise typer.Exit(0)

    email = email or settings.garmin_email or typer.prompt("Garmin email")
    password = typer.prompt("Garmin password", hide_input=True)

    def prompt_mfa() -> str:
        return typer.prompt("Garmin MFA code")

    with session_scope(session_factory) as session:
        try:
            perform_login(session, settings, client, email, password, prompt_mfa)
        except GarminApiError as exc:
            _exit_with_garmin_error(exc)

    typer.echo(f"Logged in. Token cached at {settings.garmin_token_dir}.")


@app.command(name="garmin-logout")
def garmin_logout() -> None:
    """Remove the cached Garmin token. The next sync will need garmin-login again."""
    settings = get_settings()
    GarminClient(settings.garmin_token_dir).logout()
    engine = make_engine(settings.db_path)
    session_factory = make_session_factory(engine)
    with session_scope(session_factory) as session:
        clear_login_block(session)
    typer.echo("Logged out.")


@app.command(name="garmin-sync")
def garmin_sync() -> None:
    """Run one Garmin sync cycle now, without starting the server."""
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings.db_path)
    session_factory = make_session_factory(engine)
    client = GarminClient(settings.garmin_token_dir)

    with session_scope(session_factory) as session:
        result = run_sync_cycle(session, settings, client)

    if result.status == "ok":
        if result.new_activity_ids:
            typer.echo(f"Synced: {result.new_activity_ids}")
        else:
            typer.echo("No new activities.")
        if result.skipped:
            typer.echo(f"Skipped (not found): {result.skipped}")
    else:
        typer.secho(f"{result.status}: {result.message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)


@books_app.command(name="import")
def import_book(
    path: Path,
    title: str = typer.Option(..., help="Book title for citations."),
    author: str | None = typer.Option(None, help="Author for citations."),
) -> None:
    """Import a selectable-text PDF into the local training corpus."""
    settings = get_settings()
    engine = make_engine(settings.db_path)
    session_factory = make_session_factory(engine)
    embedder = rag_service.make_embedder(settings.openai_api_key)
    if embedder is None:
        typer.secho("SOFT_FLOYD_OPENAI_API_KEY is required to import books.", err=True)
        raise typer.Exit(1)

    def show_progress(done: int, total: int) -> None:
        if done == 0 or done == total or done % 25 == 0:
            typer.echo(f"Embedded {done}/{total} passages.")

    try:
        with session_scope(session_factory) as session:
            result = asyncio.run(
                rag_service.import_pdf(session, path, title, author, embedder, show_progress)
            )
    except (ValueError, OpenAIError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        typer.echo("Rerun the same command to resume this book.", err=True)
        raise typer.Exit(1) from exc
    status = "Already imported" if result.already_imported else "Imported"
    typer.echo(
        f"{status} book {result.book_id}: {result.passages} passages"
        f" (resumed from {result.resumed_from})."
    )


if __name__ == "__main__":
    app()
