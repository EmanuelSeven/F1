"""Barra lateral e aplicação dos filtros no dashboard (AppTest, sem rede)."""

import json
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from f1.config.settings import get_settings
from f1.domain.endpoints import Endpoint
from f1.ingestion.openf1_client import OpenF1Client
from tests.unit.dashboard.conftest import StubClient, as_season, season_page_script

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
    test = AppTest.from_function(season_page_script, default_timeout=TIMEOUT)
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
    assert "Fórmula 1 · Temporada 2024" in _html(app)
    assert app.selectbox(key="filter_season").value == 2024
    kinds = app.multiselect(key="filter_kinds_locked")
    assert kinds.disabled
    assert kinds.value == ["race", "sprint"]
    assert app.selectbox(key="filter_gp").value is None


def test_year_is_kept_in_query_params(monkeypatch, tmp_path, stub, openf1_data):
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path / "lake"))
    get_settings.cache_clear()
    test = AppTest.from_function(season_page_script, default_timeout=TIMEOUT)
    test.query_params["ano"] = "2023"
    test.run()

    assert test.selectbox(key="filter_season").value == 2023
    assert "Fórmula 1 · Temporada 2023" in _html(test)

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


def test_clear_filters_resets_all_but_the_season(app):
    app.multiselect(key="filter_teams").set_value(["Ferrari"]).run()
    app.selectbox(key="filter_gp").set_value(1219).run()

    app.sidebar.button[0].click().run()

    assert not app.exception
    assert app.multiselect(key="filter_teams").value == []
    assert app.selectbox(key="filter_gp").value is None
    assert app.selectbox(key="filter_season").value == 2024


def test_filters_live_in_session_state(app):
    app.multiselect(key="filter_teams").set_value(["Ferrari"]).run()
    app.run()  # novo rerun (como ao trocar de página): o filtro continua

    assert app.session_state["filter_teams"] == ["Ferrari"]
    filters = app.session_state["dashboard_filters"]
    assert (filters.year, filters.season.teams) == (2024, ("Ferrari",))
    assert _chart_labels(app) == ["SAI"]


# --- regras da página Temporada -----------------------------------------


def _season_app(monkeypatch, tmp_path, data) -> AppTest:
    client = StubClient(data)
    monkeypatch.setattr(OpenF1Client, "from_settings", lambda _s: client)
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("F1_REQUEST_INTERVAL_SECONDS", "0")
    st.cache_resource.clear()
    st.cache_data.clear()
    get_settings.cache_clear()
    test = AppTest.from_function(season_page_script, default_timeout=TIMEOUT)
    test.run()
    assert not test.exception
    return test


def _with_zero_point_driver(data):
    """Acrescenta HAM (Mercedes) na corrida, em 12º e sem pontos."""
    race_driver = next(d for d in data[Endpoint.DRIVERS] if d["session_key"] == 9165)
    data[Endpoint.DRIVERS].append(
        {
            **race_driver,
            "driver_number": 44,
            "name_acronym": "HAM",
            "first_name": "Lewis",
            "last_name": "Hamilton",
            "team_name": "Mercedes",
            "team_colour": "27F4D2",
        }
    )
    data[Endpoint.SESSION_RESULT].append(
        {
            "session_key": 9165,
            "meeting_key": 1219,
            "driver_number": 44,
            "position": 12,
            "points": 0.0,
            "number_of_laps": 62,
        }
    )
    return data


def _with_future_race(data):
    """Acrescenta um GP ainda não disputado ao calendário."""
    data[Endpoint.MEETINGS].append(
        {
            "meeting_key": 1300,
            "meeting_name": "Future Grand Prix",
            "year": 2024,
            "date_start": "2099-05-01T10:00:00+00:00",
            "date_end": "2099-05-03T15:00:00+00:00",
            "is_cancelled": False,
        }
    )
    data[Endpoint.SESSIONS].append(
        {
            "session_key": 9999,
            "meeting_key": 1300,
            "year": 2024,
            "session_name": "Race",
            "session_type": "Race",
            "date_start": "2099-05-03T13:00:00+00:00",
            "date_end": "2099-05-03T15:00:00+00:00",
            "is_cancelled": False,
        }
    )
    return data


def test_points_chart_hides_drivers_without_points(monkeypatch, tmp_path, openf1_data):
    data = _with_zero_point_driver(as_season(openf1_data, 2024))
    app = _season_app(monkeypatch, tmp_path, data)

    toggle = app.toggle(key="show_zero_2024")
    assert toggle.label == "Mostrar pilotos sem pontos"
    assert toggle.value is False
    assert _chart_labels(app) == ["SAI", "VER"]

    toggle.set_value(True).run()
    assert _chart_labels(app) == ["SAI", "VER", "HAM"]


def test_season_in_progress_shows_done_of_total(monkeypatch, tmp_path, openf1_data):
    data = _with_future_race(as_season(openf1_data, 2024))
    app = _season_app(monkeypatch, tmp_path, data)

    html = _html(app)
    assert (
        "<strong>Carlos Sainz</strong> lidera com <strong>25</strong> pontos após "
        "<strong>1</strong> de <strong>2</strong> corridas; <strong>1</strong> "
        "piloto venceu."
    ) in html
    assert 'class="kpi-value">1/2<' in html
    assert "Realizadas / previstas" in html


def test_finished_season_keeps_plain_races_card(app):
    html = _html(app)
    assert 'class="kpi-value">1<' in html
    assert "Grandes Prêmios da temporada" in html
    assert "lidera com" not in html


def test_season_page_ignores_saved_session_kinds(monkeypatch, tmp_path, openf1_data):
    data = as_season(openf1_data, 2024)
    client = StubClient(data)
    monkeypatch.setattr(OpenF1Client, "from_settings", lambda _s: client)
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path / "lake"))
    st.cache_resource.clear()
    st.cache_data.clear()
    get_settings.cache_clear()
    test = AppTest.from_function(season_page_script, default_timeout=TIMEOUT)
    test.session_state["filter_kinds_saved"] = ["qualifying"]
    test.run()

    assert not test.exception
    assert "#### Vencedores por corrida" in [m.value for m in test.markdown]
    assert _chart_labels(test) == ["SAI", "VER"]
    assert "Não se aplica a esta página" in " ".join(
        c.value for c in test.sidebar.caption
    )
    calls = [c for c in client.calls if c[0] is Endpoint.SESSION_RESULT]
    assert [c[1][0].value for c in calls] == [(9165,)]  # só a corrida, sem quali
    assert test.session_state["filter_kinds_saved"] == ["qualifying"]  # preservado


# --- "Tipo de sessão" em páginas que o usam ------------------------------


def _policy_script() -> None:
    import streamlit as st  # noqa: PLC0415 - AppTest executa só o corpo da função

    from f1.config.settings import get_settings  # noqa: PLC0415
    from f1.dashboard.views.sidebar import (  # noqa: PLC0415
        EDITABLE_PAGE,
        LAKE_PAGE,
        SEASON_PAGE,
        render_sidebar_filters,
    )

    pages = {"editable": EDITABLE_PAGE, "hidden": LAKE_PAGE, "locked": SEASON_PAGE}
    page = pages[st.session_state.get("_test_page", "editable")]
    filters = render_sidebar_filters(get_settings().data_dir, page)
    st.write("kinds=" + ",".join(filters.season.kinds))


@pytest.fixture
def policy_app(monkeypatch, tmp_path, stub):
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("F1_REQUEST_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()
    test = AppTest.from_function(_policy_script, default_timeout=TIMEOUT)
    test.run()
    assert not test.exception
    yield test
    get_settings.cache_clear()


def _kinds_text(app: AppTest) -> str:
    return next(m.value for m in app.markdown if m.value.startswith("kinds="))


def test_editable_page_loads_qualifying_on_demand(policy_app, stub):
    assert policy_app.multiselect(key="filter_kinds").value == ["race", "sprint"]
    stub.calls.clear()

    policy_app.multiselect(key="filter_kinds").set_value(["qualifying"]).run()

    assert not policy_app.exception
    assert _kinds_text(policy_app) == "kinds=qualifying"
    result_calls = [c for c in stub.calls if c[0] is Endpoint.SESSION_RESULT]
    assert [c[1][0].value for c in result_calls] == [(9161, 9165)]  # mantém a corrida


def test_hidden_page_has_no_kinds_filter_and_keeps_choice(policy_app):
    policy_app.multiselect(key="filter_kinds").set_value(["qualifying"]).run()

    policy_app.session_state["_test_page"] = "hidden"
    policy_app.run()
    labels = [m.label for m in policy_app.sidebar.multiselect]
    assert "Tipo de sessão" not in labels
    assert _kinds_text(policy_app) == "kinds=race,sprint"

    policy_app.session_state["_test_page"] = "editable"
    policy_app.run()
    assert policy_app.multiselect(key="filter_kinds").value == ["qualifying"]


def test_locked_page_shows_disabled_filter_with_note(policy_app):
    policy_app.session_state["_test_page"] = "locked"
    policy_app.run()

    locked = policy_app.multiselect(key="filter_kinds_locked")
    assert locked.disabled
    assert "Não se aplica a esta página" in policy_app.sidebar.caption[0].value
    assert _kinds_text(policy_app) == "kinds=race,sprint"


def test_empty_kinds_on_editable_page(policy_app, stub):
    stub.calls.clear()
    policy_app.multiselect(key="filter_kinds").set_value([]).run()

    assert not policy_app.exception
    assert _kinds_text(policy_app) == "kinds="
    assert stub.calls == [] or all(
        c[0] is not Endpoint.SESSION_RESULT for c in stub.calls
    )


def test_clear_filters_restores_session_kinds(policy_app):
    policy_app.multiselect(key="filter_kinds").set_value(["practice"]).run()
    policy_app.sidebar.button[0].click().run()

    assert policy_app.multiselect(key="filter_kinds").value == ["race", "sprint"]


# --- bandeira e banner na página Temporada --------------------------------


def _nationality_text(cell: str) -> str:
    import base64  # noqa: PLC0415

    return base64.b64decode(cell.split(",", 1)[1]).decode("utf-8")


def test_winners_table_shows_nationality_after_winner(app):
    table = app.dataframe[0].value
    columns = list(table.columns)
    assert columns.index("Nacionalidade") == columns.index("Vencedor") + 1
    assert "Nac." not in columns
    cell = table["Nacionalidade"].iloc[0]
    assert cell.startswith("data:image/svg+xml;base64,")
    svg = _nationality_text(cell)
    assert ">Espanha</text>" in svg  # country_code ESP → es → Babel
    assert "<image" not in svg  # sem internet nos testes: só o nome
    assert table["GP"].tolist() == ["Singapore"]  # coluna GP inalterada


def test_nationality_falls_back_to_acronym_or_stays_empty(
    monkeypatch, tmp_path, openf1_data
):
    data = as_season(openf1_data, 2024)
    for driver in data[Endpoint.DRIVERS]:  # como em 2026: country_code vazio
        driver["country_code"] = None
        if driver["name_acronym"] == "VER":
            driver["name_acronym"] = "CAM"  # sigla sem nacionalidade conhecida
    app = _season_app(monkeypatch, tmp_path, data)

    cell = app.dataframe[0].value["Nacionalidade"].iloc[0]
    assert ">Espanha</text>" in _nationality_text(cell)  # SAI → es pela sigla
    assert "CAM" in _chart_labels(app)  # sem nacionalidade, mas sem quebrar


def test_season_header_is_a_hero_banner(monkeypatch, tmp_path, openf1_data):
    monkeypatch.setattr(
        "f1.dashboard.views.season.hero_background",
        lambda: "data:image/svg+xml;base64,PHN2Zy8+",
    )
    app = _season_app(monkeypatch, tmp_path, as_season(openf1_data, 2024))
    hero = next(m.value for m in app.markdown if 'class="f1-hero"' in m.value)
    assert "background-image:" in hero and "data:image/svg+xml;base64," in hero
    assert "Fórmula 1 · Temporada 2024" in hero
    assert "<strong>Carlos Sainz</strong> soma" in hero  # frase-resumo no banner


def test_season_header_without_hero_file(monkeypatch, tmp_path, openf1_data):
    monkeypatch.setattr("f1.dashboard.views.season.hero_background", lambda: None)
    app = _season_app(monkeypatch, tmp_path, as_season(openf1_data, 2024))

    html = _html(app)
    assert 'class="f1-hero"' not in html
    assert '<div class="f1-title">Fórmula 1 · Temporada 2024</div>' in html
    assert "<strong>Carlos Sainz</strong> soma" in html
