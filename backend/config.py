from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    results_dir: Path = Field(
        default=Path.home() / "Desktop" / "Stock",
        description="Where analysis results + sqlite history live.",
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed origins for the future React dev server.",
    )

    model_config = SettingsConfigDict(
        env_prefix="TRADINGAGENTS_",
        env_file=".env",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()
