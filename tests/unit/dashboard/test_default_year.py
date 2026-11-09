"""Ano padrão do filtro "Temporada": consulta ao lake e à API (sem rede)."""

from datetime import UTC, datetime

import pytest
import streamlit as st

from f1.config.settings import Settings, get_settings
from f1.dashboard.bootstrap import run_season_bootstrap
from f1.dashboard.views.data import default_year, season_has_completed_race
from f1.domain.endpoints import Endpoint
from f1.ingestion.openf1_client import OpenF1Client
from tests.unit.dashboard.conftest import DeniedClient, StubClient, as_season

TODAY = datetime(2027, 3, 10, tzinfo=UTC)  # antes da 1ª corrida de 2027
YEARS = (2027, 2026, 2025, 2024, 2023)


@pytest.fixture
def lake(monkeypatch, tmp_path):
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path / "lake"))
    get_settings.cache_clear()
    st.cache_data.clear()
    yield tmp_path / "lake"
    get_settings.cache_clear()
    st.cache_data.clear()


def test_uses_the_lake_calendar_without_the_api(lake, openf1_data):
    settings = Settings(_env_file=None, data_dir=lake, request_interval_seconds=0)
    run_season_bootstrap(
        settings,
        2026,
        source_factory=lambda _: StubClient(as_season(openf1_data, 2026)),
    )
    denied = DeniedClient({})  # a API não pode ser usada

    assert season_has_completed_race(lake, 2026, TODAY, lambda _s: denied)
    assert denied.calls == []


def test_queries_only_the_race_sessions_when_not_in_the_lake(lake, openf1_data):
    stub = StubClient(as_season(openf1_data, 2026))

    assert season_has_completed_race(lake, 2026, TODAY, lambda _s: stub)
    assert not season_has_completed_race(lake, 2027, TODAY, lambda _s: stub)
    filters = [(f.field, f.value) for _e, fs in stub.calls for f in fs]
    assert filters == [
        ("year", 2026),
        ("session_name", "Race"),
        ("year", 2027),
        ("session_name", "Race"),
    ]
    assert {e for e, _f in stub.calls} == {Endpoint.SESSIONS}


def test_default_year_picks_latest_season_with_a_race(monkeypatch, lake, openf1_data):
    """Hoje é 10/03/2027 sem corrida concluída em 2027 → padrão 2026."""
    stub = StubClient(as_season(openf1_data, 2026))
    monkeypatch.setattr(OpenF1Client, "from_settings", lambda _s: stub)

    assert default_year(lake, YEARS, bucket=1) == 2026


def test_default_year_when_api_is_unavailable(monkeypatch, lake):
    monkeypatch.setattr(OpenF1Client, "from_settings", lambda _s: DeniedClient({}))
    assert default_year(lake, YEARS, bucket=2) == 2027  # ano atual da lista
