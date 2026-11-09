"""Página "Voltas": 5 voltas mais rápidas por circuito (AppTest, sem rede)."""

import json

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from f1.config.settings import get_settings
from f1.dashboard.views import charts
from f1.dashboard.views.laps import (
    kinds_text,
    laps_display,
    laps_subtitle,
    laps_title,
)
from f1.dashboard.views.sidebar import EDITABLE_PAGE, LAPS_PAGE
from f1.domain.endpoints import Endpoint
from f1.domain.models import SessionKind
from f1.ingestion.openf1_client import OpenF1Client
from f1.processing.fastest_laps import fastest_laps
from f1.processing.normalize import normalize
from tests.conftest import load_fixture
from tests.unit.dashboard.conftest import StubClient, as_season

TIMEOUT = 60


def _laps_script() -> None:
    from f1.config.settings import get_settings  # noqa: PLC0415 - AppTest executa o corpo
    from f1.dashboard.views.laps import render_laps  # noqa: PLC0415
    from f1.dashboard.views.sidebar import (  # noqa: PLC0415
        LAPS_PAGE,
        render_sidebar_filters,
    )

    render_sidebar_filters(get_settings().data_dir, LAPS_PAGE)
    render_laps()


@pytest.fixture
def stub(monkeypatch, openf1_data):
    client = StubClient(as_season(openf1_data, 2026))
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
    test = AppTest.from_function(_laps_script, default_timeout=TIMEOUT)
    test.run()
    assert not test.exception
    yield test
    get_settings.cache_clear()


def _html(app: AppTest) -> str:
    return "\n".join(m.value for m in app.markdown)


def _table(app: AppTest):
    return app.dataframe[-1].value


def test_laps_page_uses_editable_session_filter():
    assert LAPS_PAGE == EDITABLE_PAGE


def test_default_shows_latest_grand_prix(app, stub):
    html = _html(app)
    assert "Fórmula 1 · Top 5 Voltas Mais Rápidas 2026" in html
    assert "Circuito Singapore · Singapore" in html
    assert "Rodada 1 · Exibindo as 5 voltas mais rápidas em corrida e sprint" in html
    assert "Mostrando o Grande Prêmio mais recente" in " ".join(
        c.value for c in app.caption
    )
    table = _table(app)
    assert table["Piloto"].tolist() == ["SAI", "SAI", "VER", "VER"]
    assert table["Tempo"].tolist()[0] == "1:40.512"
    assert table["Diferença"].tolist()[:2] == ["—", "+0,390 s"]
    assert table["Equipe"].tolist()[0] == "■ Ferrari"
    assert "Volta mais rápida: **1:40.512**, de **Carlos Sainz**" in html
    assert len(app.get("plotly_chart")) == 1
    lap_calls = [c for c in stub.calls if c[0] is Endpoint.LAPS]
    assert [c[1][0].value for c in lap_calls] == [9165]  # só a corrida


def test_qualifying_laps_are_loaded_on_demand(app, stub):
    stub.calls.clear()

    app.multiselect(key="filter_kinds").set_value(["race", "qualifying"]).run()

    assert not app.exception
    table = _table(app)
    assert table[["Piloto", "Tempo", "Sessão"]].values.tolist()[0] == [
        "SAI",
        "1:32.708",
        "Classificação",
    ]
    lap_calls = [c for c in stub.calls if c[0] is Endpoint.LAPS]
    assert {c[1][0].value for c in lap_calls} == {9161, 9165}  # mantém a corrida
    assert (
        "Rodada 1 · Exibindo as 5 voltas mais rápidas em corrida e classificação"
    ) in _html(app)


def test_one_lap_per_driver(app):
    app.toggle(key="laps_one_per_driver").set_value(True).run()
    assert _table(app)["Piloto"].tolist() == ["SAI", "VER"]


def test_team_filter_restricts_laps(app):
    app.multiselect(key="filter_teams").set_value(["Red Bull Racing"]).run()
    assert _table(app)["Piloto"].unique().tolist() == ["VER"]


def test_selected_grand_prix_without_sessions_yet(app):
    app.multiselect(key="filter_kinds").set_value(["sprint"]).run()
    assert "ainda não aconteceram" in app.info[0].value


def test_empty_kinds(app):
    app.multiselect(key="filter_kinds").set_value([]).run()
    assert "Escolha ao menos um tipo de sessão" in app.info[0].value


# --- funções puras ----------------------------------------------------------


@pytest.fixture
def top():
    frames = {e: normalize(e, load_fixture(e)) for e in Endpoint}
    return fastest_laps(
        frames[Endpoint.LAPS],
        frames[Endpoint.DRIVERS],
        frames[Endpoint.SESSIONS],
        session_keys=[9165],
    )


def test_laps_display_and_kinds_text(top):
    display = laps_display(top)
    assert list(display.columns) == [
        "Pos.",
        "Piloto",
        "Nome",
        "Nacionalidade",
        "Equipe",
        "Tempo",
        "Diferença",
        "Sessão",
        "Volta",
    ]
    assert display["Sessão"].unique().tolist() == ["Corrida"]
    assert kinds_text((SessionKind.RACE,)) == "corrida"
    assert kinds_text(tuple(SessionKind)) == (
        "corrida, sprint, classificação e treino livre"
    )


def test_fastest_laps_chart_is_a_dot_plot(top):
    fig = charts.fastest_laps_chart(top)
    trace = fig.data[0]
    assert trace.type == "scatter"
    assert list(trace.y) == ["1º SAI", "2º SAI", "3º VER", "4º VER"]
    assert list(trace.text)[:2] == ["1:40.512", "1:40.902  +0,390"]
    assert trace.marker.color[0] == "#F91536"
    low, high = fig.layout.xaxis.range
    assert low < 100.512 and high > 101.456  # eixo não parte do zero
    assert json.loads(fig.to_json())["layout"]["yaxis"]["autorange"] == "reversed"


# --- textos dinâmicos do ranking Top 5 ------------------------------------


@pytest.mark.parametrize("year", [2023, 2026, 2027])
def test_title_uses_the_selected_year(year):
    assert laps_title(year) == f"Fórmula 1 · Top 5 Voltas Mais Rápidas {year}"


@pytest.mark.parametrize("round_number", [1, 20, 24])
def test_subtitle_uses_the_round_of_the_event(round_number):
    assert laps_subtitle(round_number, (SessionKind.RACE, SessionKind.SPRINT)) == (
        f"Rodada {round_number} · Exibindo as 5 voltas mais rápidas em corrida e sprint"
    )


def test_subtitle_follows_the_session_filter():
    assert laps_subtitle(20, (SessionKind.QUALIFYING,)) == (
        "Rodada 20 · Exibindo as 5 voltas mais rápidas em classificação"
    )


def test_title_follows_the_season_filter(app):
    app.selectbox(key="filter_season").set_value(2025).run()

    assert not app.exception
    html = _html(app)
    assert "Fórmula 1 · Top 5 Voltas Mais Rápidas 2025" in html
    assert "Ainda não há Grandes Prêmios disputados em 2025" in app.info[0].value
