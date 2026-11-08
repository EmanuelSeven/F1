"""Barra lateral e aplicação dos filtros no dashboard (AppTest, sem rede)."""

import json
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from f1.config.settings import get_settings
from f1.domain.endpoints import Endpoint
from f1.ingestion.openf1_client import OpenF1Client
from tests.unit.dashboard.conftest import StubClient, as_season

APP = Path(__file__).parents[3] / "src" / "f1" / "dashboard.py"
TIMEOUT = 60


@pytest.fixture
def stub(monkeypatch, openf1_data):
    client = StubClient(as_season(openf1_data, 2024))
    monkeypatch.setattr(OpenF1Client, "from_settings", lambda _s: client)
    st.cache_resource.clear()
    st.cache_data.clear()
    yield client
    st.cache_resource.clear()
    st.cache_data.clear()


@pytest.fixture
def app(monkeypatch, tmp_path, stub):
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("F1_REQUEST_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()
    test = AppTest.from_file(str(APP), default_timeout=TIMEOUT)
    test.run()
    assert not test.exception
    yield test
    get_settings.cache_clear()


def _html(app: AppTest) -> str:
    return "\n".join(m.value for m in app.markdown)


def _chart_labels(app: AppTest) -> list[str]:
    spec = json.loads(app.get("plotly_chart")[0].proto.spec)
    return list(spec["data"][0]["y"])


def test_sidebar_has_brand_filters_and_footer(app):
    sidebar = "\n".join(m.value for m in app.sidebar.markdown)
    assert '<span class="f1-brand-mark">FORMULA 1</span>' in sidebar
    assert " · Analytics" in sidebar
    assert [s.label for s in app.sidebar.selectbox] == ["Temporada", "Grande Prêmio"]
    assert [m.label for m in app.sidebar.multiselect] == [
        "Tipo de sessão",
        "Equipes",
        "Pilotos",
    ]
    assert app.sidebar.button[0].label == "Limpar filtros"
    assert app.sidebar.expander[0].label == "Equipe e piloto"
    footer = app.sidebar.caption[-1].value
    assert footer.startswith("Dados: OpenF1 · última atualização ")
    assert not footer.endswith("—")  # a carga inicial já registrou a ingestão


def test_season_selector_moved_out_of_the_page(app):
    assert len(app.main.selectbox) == 0
    assert "Fórmula 1 · temporada 2024" in _html(app)
    assert app.selectbox(key="filter_season").value == 2024
    assert app.multiselect(key="filter_kinds").value == ["race", "sprint"]
    assert app.selectbox(key="filter_gp").value is None


def test_year_is_kept_in_query_params(monkeypatch, tmp_path, stub, openf1_data):
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path / "lake"))
    get_settings.cache_clear()
    test = AppTest.from_file(str(APP), default_timeout=TIMEOUT)
    test.query_params["ano"] = "2023"
    test.run()

    assert test.selectbox(key="filter_season").value == 2023
    assert "Fórmula 1 · temporada 2023" in _html(test)

    test.selectbox(key="filter_season").set_value(2024).run()
    assert test.query_params["ano"] == "2024"
    get_settings.cache_clear()


def test_options_depend_on_the_year(app):
    assert app.multiselect(key="filter_teams").options == ["Ferrari", "Red Bull Racing"]
    assert app.multiselect(key="filter_drivers").options == [
        "SAI · Carlos Sainz",
        "VER · Max Verstappen",
    ]
    assert app.selectbox(key="filter_gp").options == ["Todos", "1 · Singapore"]


def test_team_filter_restricts_chart_table_and_summary(app):
    assert _chart_labels(app) == ["SAI", "VER"]

    app.multiselect(key="filter_teams").set_value(["Red Bull Racing"]).run()

    assert not app.exception
    assert _chart_labels(app) == ["VER"]
    assert app.multiselect(key="filter_drivers").options == ["VER · Max Verstappen"]
    html = _html(app)
    assert "<strong>Max Verstappen</strong> lidera a seleção" in html
    assert "nenhum piloto da seleção venceu" in html
    assert "Nenhuma vitória dos pilotos filtrados." in [i.value for i in app.info]
    assert "pilotos filtrados" in html  # legenda do KPI


def test_driver_filter(app):
    app.multiselect(key="filter_drivers").set_value([55]).run()

    assert _chart_labels(app) == ["SAI"]
    assert app.dataframe[0].value["Vencedor"].tolist() == ["SAI"]


def test_grand_prix_filter_opens_details(app):
    assert "Rodada 1 · Singapore" not in _html(app)

    app.selectbox(key="filter_gp").set_value(1219).run()

    assert not app.exception
    assert "Rodada 1 · Singapore" in _html(app)  # sem precisar clicar
    assert app.dataframe[0].value["Vencedor"].tolist() == ["SAI"]  # linha mantida
    assert app.dataframe[1].value["Piloto"].tolist() == ["SAI", "VER"]


def test_qualifying_is_loaded_on_demand(app, stub):
    stub.calls.clear()

    app.multiselect(key="filter_kinds").set_value(["qualifying"]).run()

    assert not app.exception
    result_calls = [c for c in stub.calls if c[0] is Endpoint.SESSION_RESULT]
    assert [c[1][0].value for c in result_calls] == [(9161, 9165)]  # mantém a corrida
    assert "#### Vencedores por sessão" in [m.value for m in app.markdown]
    table = app.dataframe[0].value
    assert table["Sessão"].tolist() == ["Classificação"]
    assert table["Vencedor"].tolist() == ["SAI"]
    assert any("não valem pontos" in i.value for i in app.info)
    assert "**1** piloto terminou em 1º" not in _html(app)  # renderizado em HTML
    assert "terminou em 1º" in _html(app)


def test_empty_kinds_asks_for_a_type(app):
    app.multiselect(key="filter_kinds").set_value([]).run()

    assert not app.exception
    assert "Escolha ao menos um tipo de sessão" in app.info[0].value


def test_clear_filters_resets_all_but_the_season(app):
    app.multiselect(key="filter_teams").set_value(["Ferrari"]).run()
    app.multiselect(key="filter_kinds").set_value(["race"]).run()
    app.selectbox(key="filter_gp").set_value(1219).run()

    app.sidebar.button[0].click().run()

    assert not app.exception
    assert app.multiselect(key="filter_teams").value == []
    assert app.multiselect(key="filter_kinds").value == ["race", "sprint"]
    assert app.selectbox(key="filter_gp").value is None
    assert app.selectbox(key="filter_season").value == 2024


def test_filters_live_in_session_state(app):
    app.multiselect(key="filter_teams").set_value(["Ferrari"]).run()
    app.run()  # novo rerun (como ao trocar de página): o filtro continua

    assert app.session_state["filter_teams"] == ["Ferrari"]
    filters = app.session_state["dashboard_filters"]
    assert (filters.year, filters.season.teams) == (2024, ("Ferrari",))
    assert _chart_labels(app) == ["SAI"]
