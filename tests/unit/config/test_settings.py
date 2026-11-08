from pathlib import Path

import pytest
from pydantic import ValidationError

from f1.config.settings import Settings, get_settings


def test_settings_defaults(monkeypatch):
    for var in ("F1_ENV", "F1_DATA_DIR", "F1_MAX_REJECTION_RATE"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)

    assert settings.env == "dev"
    assert settings.api_base_url == "https://api.openf1.org/v1"
    assert settings.data_dir == Path("data")
    assert settings.max_rejection_rate == 0.05


def test_settings_reads_prefixed_env(monkeypatch, tmp_path):
    monkeypatch.setenv("F1_HTTP_MAX_RETRIES", "2")
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path))

    settings = Settings(_env_file=None)

    assert settings.http_max_retries == 2
    assert settings.data_dir == tmp_path


def test_settings_rejects_invalid_rate(monkeypatch):
    monkeypatch.setenv("F1_MAX_REJECTION_RATE", "2")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_cached():
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()
