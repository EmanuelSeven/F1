"""Configuração centralizada a partir de variáveis de ambiente (prefixo ``F1_``)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="F1_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "dev"
    log_level: str = "INFO"
    api_base_url: str = "https://api.openf1.org/v1"
    data_dir: Path = Path("data")
    http_timeout_seconds: float = Field(default=30.0, gt=0)
    http_max_retries: int = Field(default=5, ge=0)
    request_interval_seconds: float = Field(default=0.5, ge=0)
    max_rejection_rate: float = Field(default=0.05, ge=0, le=1)


@lru_cache
def get_settings() -> Settings:
    """Retorna as configurações carregadas uma única vez por processo."""
    return Settings()
