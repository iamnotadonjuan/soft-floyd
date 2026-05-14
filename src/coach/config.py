from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

COACH_DIR = Path.home() / ".coach"
DATA_DIR = Path("data")


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        toml_file=str(COACH_DIR / "config.toml"),
        env_prefix="COACH_",
        extra="ignore",
    )

    # Training
    lthr: int = Field(default=165, description="Lactate threshold heart rate (bpm)")

    # Storage
    db_path: Path = Field(default=DATA_DIR / "trainer.db")
    fit_dir: Path = Field(default=DATA_DIR / "fit")

    # Garmin token
    garth_token_path: Path = Field(default=COACH_DIR / "garth.json")

    # Keychain
    keychain_service: str = "coach-soft-floyd"
    keychain_account: str = "garth-token-key"

    # Poller
    poll_interval_minutes: int = 10

    # Phase 2
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Phase 3
    serve_frontend: bool = False  # set COACH_SERVE_FRONTEND=1 to serve built React app

    # Logging
    log_level: str = "INFO"

    def ensure_dirs(self) -> None:
        COACH_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.fit_dir.mkdir(parents=True, exist_ok=True)


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
