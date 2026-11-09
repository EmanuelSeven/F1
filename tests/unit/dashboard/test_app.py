"""Testes das páginas Streamlit com o AppTest (sem rede)."""

import base64
from datetime import UTC, datetime
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from f1.config.settings import get_settings
from f1.dashboard.loaders import load_season_data
from f1.dashboard.views.season import summary_html, winners_display
from f1.dashboard.views.sidebar import season_options
from f1.domain.endpoints import Endpoint
from f1.ingestion.openf1_client import OpenF1Client
from f1.processing.standings import SeasonKpis, race_winners
from tests.conftest import load_fixture
from tests.unit.dashboard.conftest import (
    DeniedClient,
    FailingClient,
    StubClient,
    as_season,
    season_page_script,
)

APP = Path(__file__).parents[3] / "src" / "f1" / "dashboard.py"
TIMEOUT = 60


@pytest.fixture(autouse=True)
def client(monkeypatch):
    """Sem rede: por padrão a API responde 401. Cada teste pode trocar o cliente."""
    holder = {"client": DeniedClient({})}
    monkeypatch.setattr(OpenF1Client, "from_settings", lambda _s: holder["client"])
    st.cache_resource.clear()
    st.cache_data.clear()
    yield holder
    st.cache_resource.clear()
    st.cache_data.clear()


@pytest.fixture
def data_env(monkeypatch):
    def _set(data_dir: Path) -> None:
        monkeypatch.setenv("F1_DATA_DIR", str(data_dir))
        monkeypatch.setenv("F1_REQUEST_INTERVAL_SECONDS", "0")
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


def _dashboard(data_env, data_dir: Path) -> AppTest:
    data_env(data_dir)
    app = AppTest.from_function(season_page_script, default_timeout=TIMEOUT)
    app.run()
    return app


def _html(app: AppTest) -> str:
    return "\n".join(m.value for m in app.markdown)


# --- página Temporada ------------------------------------------------------


def test_season_page_is_default_and_loads_2026(data_env, tmp_path, client, openf1_data):
    stub = StubClient(as_season(openf1_data, 2026))
    client["client"] = stub

    app = _dashboard(data_env, tmp_path / "lake")

    assert not app.exception
    html = _html(app)
    assert "Fórmula 1 · Temporada 2026" in html
    assert "<strong>Carlos Sainz</strong> soma <strong>25</strong> pontos" in html
    assert html.count('class="kpi-card"') == 4
    for caption in (
        "Grandes Prêmios da temporada",
        "Corridas curtas de sábado",
        "Em corridas, sem contar sprints",
        "Corridas + sprints",
    ):
        assert caption in html
    assert app.selectbox(key="filter_season").value == 2026
    assert any('setAttribute("translate", "no")' in h.value for h in app.html)
    winners = app.dataframe[0].value
    assert winners["Vencedor"].tolist() == ["SAI"]
    assert winners["Equipe"].tolist() == ["■ Ferrari"]
    assert "Cor" not in winners.columns
    assert "" not in winners.columns
    assert len(app.get("plotly_chart")) == 1
    assert "Clique em uma corrida" in " ".join(c.value for c in app.caption)

    calls = len(stub.calls)
    app.run()  # temporada já está no lake: nenhuma nova requisição
    assert len(stub.calls) == calls


def test_default_season_is_latest_with_a_completed_race(
    data_env, tmp_path, client, openf1_data
):
    """Fixtures só têm corrida em 2023: esse é o ano padrão (sem ?ano=)."""
    client["client"] = StubClient(openf1_data)
    app = _dashboard(data_env, tmp_path / "lake")

    assert app.selectbox(key="filter_season").value == 2023
    assert "Fórmula 1 · Temporada 2023" in _html(app)
    assert app.dataframe[0].value["GP"].tolist() == ["Singapore"]

    app.selectbox(key="filter_season").set_value(2026).run()

    assert not app.exception
    assert "Ainda não há resultados de corridas para 2026" in app.info[0].value


def test_access_error_shows_friendly_message_and_retries(
    data_env, tmp_path, client, openf1_data
):
    app = _dashboard(data_env, tmp_path / "lake")

    assert not app.exception
    assert "temporariamente indisponível" in app.warning[0].value
    assert "Ainda não há resultados" in app.info[0].value

    client["client"] = StubClient(as_season(openf1_data, 2026))
    app.run()  # a falha não ficou em cache
    assert not app.warning
    assert app.dataframe


def test_other_api_errors_show_generic_message(data_env, tmp_path, client):
    client["client"] = FailingClient({})
    app = _dashboard(data_env, tmp_path / "lake")

    assert not app.exception
    assert "Não foi possível baixar dados" in app.error[0].value


# --- detalhes da corrida -------------------------------------------------


def _race_details_script(data_dir: str, year: int) -> None:
    from pathlib import Path  # noqa: PLC0415 - AppTest executa só o corpo da função

    from f1.dashboard.loaders import load_season_data  # noqa: PLC0415 - AppTest executa só o corpo da função
    from f1.dashboard.views.season import render_race_details  # noqa: PLC0415 - AppTest executa só o corpo da função
    from f1.processing.standings import race_winners  # noqa: PLC0415 - AppTest executa só o corpo da função

    data = load_season_data(Path(data_dir), year)
    winners = race_winners(data.results, data.sessions, data.meetings, data.drivers)
    render_race_details(Path(data_dir), year, winners.iloc[0], data)


def _race_details(data_env, data_dir: Path) -> AppTest:
    data_env(data_dir)
    app = AppTest.from_function(
        _race_details_script, args=(str(data_dir), 2023), default_timeout=TIMEOUT
    )
    app.run()
    return app


def test_race_details_downloads_on_demand(data_env, populated_lake, client):
    # Lake só com o calendário e os resultados: detalhes vêm da API sob demanda.
    for dataset in ("laps", "stints", "pit_stops", "weather"):
        target = populated_lake / "silver" / dataset
        for part in target.rglob("*.parquet"):
            part.unlink()
    stub = StubClient({e: load_fixture(e) for e in Endpoint})
    client["client"] = stub

    app = _race_details(data_env, populated_lake)

    assert not app.exception
    assert "Rodada 1 · Singapore" in _html(app)
    result = app.dataframe[0].value
    assert result["Piloto"].tolist() == ["SAI", "VER"]
    assert result["Equipe"].tolist() == ["■ Ferrari", "■ Red Bull Racing"]
    assert result["Tempo / diferença"].tolist() == ["1:44:38.123", "+21,441 s"]
    assert len(app.get("plotly_chart")) == 3  # voltas, pneus, clima
    assert app.dataframe[1].value["Piloto"].tolist() == ["SAI", "VER"]  # pit stops
    assert {m.label for m in app.metric} == {
        "Ar (média)",
        "Pista (média)",
        "Umidade (média)",
        "Chuva",
    }
    assert {c[0].value for c in stub.calls} >= {"laps", "stints", "pit", "weather"}

    calls = len(stub.calls)
    app.run()
    assert len(stub.calls) == calls  # já baixado


def test_race_details_without_api_keeps_result(data_env, populated_lake):
    for part in (populated_lake / "silver" / "laps").rglob("*.parquet"):
        part.unlink()

    app = _race_details(data_env, populated_lake)

    assert not app.exception
    assert "temporariamente indisponível" in app.warning[0].value
    assert app.dataframe[0].value["Piloto"].tolist() == ["SAI", "VER"]
    assert "Sem tempos de volta" in " ".join(i.value for i in app.info)


# --- página Data Lake ----------------------------------------------------


def _lake_script() -> None:
    from f1.dashboard.views.lake import render_lake  # noqa: PLC0415 - AppTest executa só o corpo da função

    render_lake()


def _lake(data_env, data_dir: Path) -> AppTest:
    data_env(data_dir)
    app = AppTest.from_function(_lake_script, default_timeout=TIMEOUT)
    app.run()
    return app


def _metrics(app: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in app.metric}


def test_lake_page_shows_platform_metrics(data_env, populated_lake):
    app = _lake(data_env, populated_lake)

    assert not app.exception
    metrics = _metrics(app)
    assert metrics["Arquivos na bronze"] == "14"
    assert metrics["Registros processados"] == "31"
    assert metrics["Registros rejeitados"] == "1"
    assert metrics["Último run_id"] == "run-2"
    assert len(app.dataframe) == 2
    assert not app.info

    # Histórico: abre no dataset com rejeições (laps) e desenha a tendência.
    assert app.selectbox(key="rejections_dataset").value == "laps"
    assert len(app.get("plotly_chart")) == 1

    app.selectbox(key="rejections_dataset").set_value("meetings").run()
    assert not app.exception
    assert "Nenhuma rejeição em 1 carga(s)" in app.success[0].value
    assert len(app.get("plotly_chart")) == 1  # linha "Total" em 0%

    app.button[0].click().run()
    assert _metrics(app)["Registros processados"] == "31"


def test_lake_page_empty_points_to_season_page(data_env, tmp_path):
    app = _lake(data_env, tmp_path / "empty")

    assert not app.exception
    assert "Temporada" in app.info[0].value
    assert "Nenhuma carga registrada" in app.info[1].value
    assert _metrics(app)["Último run_id"] == "—"


# --- funções puras da página -------------------------------------------


def test_season_options_from_first_season():
    assert season_options(datetime(2026, 5, 1, tzinfo=UTC)) == [2026, 2025, 2024, 2023]


def test_summary_html_escapes_and_bolds():
    kpis = SeasonKpis(2, 0, 1, "A <b>B</b>", "AB", 50.0)
    html = summary_html(kpis)
    assert html.startswith("<strong>A &lt;b&gt;B&lt;/b&gt;</strong> soma")


def test_winners_display_columns(populated_lake):

    data = load_season_data(populated_lake, 2023)
    winners = race_winners(data.results, data.sessions, data.meetings, data.drivers)
    display = winners_display(winners)

    assert list(display.columns) == [
        "Rod.",
        "GP",
        "Data",
        "Vencedor",
        "Nacionalidade",
        "Equipe",
    ]
    row = display.iloc[0]
    assert [row["Rod."], row["GP"], row["Data"], row["Vencedor"], row["Equipe"]] == [
        1,
        "Singapore",  # coluna GP inalterada
        "17/09",
        "SAI",
        "■ Ferrari",
    ]
    cell = base64.b64decode(row["Nacionalidade"].split(",", 1)[1]).decode("utf-8")
    assert ">Espanha</text>" in cell  # driver_badge (sem rede: só o nome)


def test_race_details_quality_failure_shows_message(data_env, populated_lake, client):
    for part in (populated_lake / "silver" / "laps").rglob("*.parquet"):
        part.unlink()
    data = {e: load_fixture(e) for e in Endpoint}
    data[Endpoint.LAPS] = [{**lap, "lap_number": 0} for lap in data[Endpoint.LAPS]]
    client["client"] = StubClient(data)

    app = _race_details(data_env, populated_lake)

    assert not app.exception
    assert "não passaram na validação" in app.error[0].value
    assert app.dataframe[0].value["Piloto"].tolist() == ["SAI", "VER"]
