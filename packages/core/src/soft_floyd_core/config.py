"""Settings for Soft Floyd.

Reads, in increasing priority: defaults -> ~/.soft-floyd/config.toml -> env
vars prefixed SOFT_FLOYD_ -> a local .env file. See .env.example.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

CONFIG_DIR = Path.home() / ".soft-floyd"
CONFIG_PATH = CONFIG_DIR / "config.toml"


class _TomlConfigSource(PydanticBaseSettingsSource):
    """Reads ~/.soft-floyd/config.toml if it exists. Missing file -> no-op."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        raise NotImplementedError  # unused; we override __call__ instead

    def __call__(self) -> dict[str, Any]:
        if not CONFIG_PATH.exists():
            return {}
        return tomllib.loads(CONFIG_PATH.read_text())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOFT_FLOYD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = None
    db_path: Path = Path("data/soft-floyd.db")
    log_level: str = "INFO"
    lthr: int = 165  # default lactate threshold HR (bpm) when the rider hasn't set one

    # Garmin sync (exec-plan 0002). No garmin_password field — the password
    # is prompted (hidden) once by `soft-floyd garmin-login` and never
    # persisted; only the resulting token cache is. See docs/SECURITY.md.
    garmin_email: str | None = None  # prefills the login prompt only
    garmin_token_dir: Path = CONFIG_DIR / "garmin"
    fit_dir: Path = Path("data/fit")
    garmin_poll_enabled: bool = True
    poll_interval_minutes: int = 10
    poll_max_backoff_minutes: int = 60
    garmin_page_size: int = 20

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority, highest first: init > env > .env > config.toml
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _TomlConfigSource(settings_cls),
            file_secret_settings,
        )


def get_settings() -> Settings:
    return Settings()
