"""Página "Última corrida" pelo roteador real (é a página inicial; sem rede)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from f1.config.settings import Settings, get_settings
from f1.dashboard.bootstrap import run_season_bootstrap
from f1.domain.endpoints import Endpoint
from f1.ingestion.openf1_client import OpenF1Client
from tests.unit.dashboard.conftest import DeniedClient, StubClient, as_season

APP = Path(__file__).parents[3] / "src" / "f1" / "dashboard.py"
TIMEOUT = 60
YEAR = datetime.now(UTC).year  # a página procura no ano atual


def _with_unpublished_race(data):
    """Acrescenta uma corrida já terminada, ainda sem resultados na API."""
    data[Endpoint.MEETINGS].append(
        {
            "meeting_key": 1300,
            "meeting_name": "Future Grand Prix",
            "year": YEAR,
            "circuit_short_name": "Futura",
            "country_name": "Brasil",
            "date_start": "2025-06-01T10:00:00+00:00",
            "is_cancelled": False,
        }
    )
    data[Endpoint.SESSIONS].append(
        {
            "session_key": 9300,
            "meeting_key": 1300,
            "year": YEAR,
            "session_name": "Race",
            "session_type": "Race",
            "date_start": "2025-06-01T13:00:00+00:00",
            "date_end": "2025-06-01T15:00:00+00:00",
            "is_cancelled": False,
        }
    )
    return data


@pytest.fixture
def lake(monkeypatch, tmp_path):
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("F1_REQUEST_INTERVAL_SECONDS", "0")
    st.cache_resource.clear()
    st.cache_data.clear()
    get_settings.cache_clear()
    yield tmp_path / "lake"
    st.cache_resource.clear()
    st.cache_data.clear()
    get_settings.cache_clear()


def _run(monkeypatch, client) -> AppTest:
    monkeypatch.setattr(OpenF1Client, "from_settings", lambda _s: client)
    app = AppTest.from_file(str(APP), default_timeout=TIMEOUT)
    app.run()
    assert not app.exception
    return app


def _html(app: AppTest) -> str:
    return "\n".join(m.value for m in app.markdown)


def _cards(app: AppTest) -> str:
    return "\n".join(m.value for m in app.markdown if "kpi-card" in m.value)


def test_latest_race_is_the_home_page(monkeypatch, lake, openf1_data):
    stub = StubClient(as_season(openf1_data, YEAR))
    app = _run(monkeypatch, stub)

    html = _html(app)
    assert "Singapore Grand Prix · Singapore, Singapore" in html
    assert '<div class="f1-date">17/09/2023</div>' in html
    assert f"Rodada 1 de 1 · temporada {YEAR}" in [c.value for c in app.main.caption]
    assert not app.warning
    # pódio: cor da equipe, tempo do vencedor e diferença dos demais
    assert (
        '<div class="podium-place">1º</div><div class="podium-driver">Carlos Sainz'
        in html
    )
    assert "--team: #F91536" in html
    assert '<div class="podium-time">1:44:38.123</div>' in html
    assert html.count('class="podium-card"') == 1  # VER chegou em 5º


def test_classification_with_grid_and_highlights(monkeypatch, lake, openf1_data):
    stub = StubClient(as_season(openf1_data, YEAR))
    app = _run(monkeypatch, stub)

    table = app.dataframe[0].value
    assert list(table.columns) == [
        "Pos.",
        "Piloto",
        "Nacionalidade",
        "Equipe",
        "Largada",
        "Posições",
        "Tempo / diferença",
        "Pontos",
        "Situação",
    ]
    assert table[["Piloto", "Largada", "Posições", "Pontos"]].values.tolist() == [
        ["Carlos Sainz", "1", "=", "25"],
        ["Max Verstappen", "11", "▲ 6", "10"],
    ]
    cards = _cards(app)
    assert 'kpi-value">1:40.512<' in cards and "Carlos Sainz · volta 3" in cards
    assert 'kpi-value">▲ 6<' in cards and "Max Verstappen" in cards
    assert 'kpi-label">Abandonos</div><div class="kpi-value">0<' in cards
    championship = app.dataframe[1].value
    assert championship[["Piloto", "Pontos", "Variação"]].values.tolist() == [
        ["Carlos Sainz", "25", "—"],
        ["Max Verstappen", "10", "—"],
    ]
    grid_calls = [c for c in stub.calls if c[0] is Endpoint.STARTING_GRID]
    assert [(f.field, f.value) for c in grid_calls for f in c[1]] == [
        ("meeting_key", 1219)
    ]


def test_sidebar_navigation_above_filters(monkeypatch, lake, openf1_data):
    app = _run(monkeypatch, StubClient(as_season(openf1_data, YEAR)))

    links = [p.label for p in app.sidebar.get("page_link")]
    assert links == ["Última corrida", "Temporada", "Voltas", "Data Lake"]
    season = app.selectbox(key="filter_season_locked")
    assert season.disabled
    assert season.value == YEAR  # ano da corrida exibida, não o do filtro
    assert "Não se aplica a esta página" in app.sidebar.caption[0].value
    assert [s.label for s in app.sidebar.selectbox] == ["Temporada"]  # sem GP
    assert any('setAttribute("translate", "no")' in h.value for h in app.html)


def test_unpublished_results_show_previous_race(monkeypatch, lake, openf1_data):
    stub = StubClient(_with_unpublished_race(as_season(openf1_data, YEAR)))
    app = _run(monkeypatch, stub)

    warning = app.warning[0].value
    assert "Resultados de Future Grand Prix ainda não disponíveis" in warning
    assert "Mostrando a corrida anterior" in warning
    assert "Singapore Grand Prix · Singapore, Singapore" in _html(app)
    refreshes = [c for c in stub.calls if c[0] is Endpoint.MEETINGS]
    assert len(refreshes) == 2  # carga inicial + uma atualização

    calls = len(stub.calls)
    app.run()  # mesma janela de 10 min: não consulta a API de novo
    assert len(stub.calls) == calls


def test_access_error_shows_previous_race(monkeypatch, lake, openf1_data):
    data = _with_unpublished_race(as_season(openf1_data, YEAR))
    settings = Settings(_env_file=None, data_dir=lake, request_interval_seconds=0)
    run_season_bootstrap(settings, YEAR, source_factory=lambda _: StubClient(data))

    app = _run(monkeypatch, DeniedClient({}))

    warning = app.warning[0].value
    assert "Resultados de Future Grand Prix ainda não disponíveis" in warning
    assert "temporariamente indisponível" in warning
    assert "Singapore Grand Prix · Singapore, Singapore" in _html(app)
    assert app.dataframe[0].value["Largada"].tolist() == ["—", "—"]  # sem grade


def test_no_completed_race(monkeypatch, lake):
    app = _run(monkeypatch, StubClient({}))
    assert "Ainda não há corridas concluídas" in app.info[0].value
