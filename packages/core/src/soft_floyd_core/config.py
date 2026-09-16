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
