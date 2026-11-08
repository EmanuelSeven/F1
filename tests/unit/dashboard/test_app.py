"""Testes do script Streamlit (src/f1/dashboard.py) com o AppTest."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from f1.config.settings import get_settings
from f1.domain.endpoints import Endpoint
from f1.ingestion.openf1_client import OpenF1Client, OpenF1Error
from tests.unit.dashboard.test_bootstrap import DeniedClient, StubClient

APP = Path(__file__).parents[3] / "src" / "f1" / "dashboard.py"


class FailingClient(StubClient):
    def fetch(self, endpoint, filters=()):
        raise OpenF1Error("connection reset")


@pytest.fixture(autouse=True)
def client_factory(monkeypatch):
    """Sem rede: por padrão a API responde 401. Cada teste pode trocar o cliente."""
    holder = {"client": DeniedClient({})}
    monkeypatch.setattr(OpenF1Client, "from_settings", lambda _s: holder["client"])
    st.cache_resource.clear()
    st.cache_data.clear()
    yield holder
    st.cache_resource.clear()
    st.cache_data.clear()


@pytest.fixture
def run_app(monkeypatch):
    def _run(data_dir: Path) -> AppTest:
        monkeypatch.setenv("F1_DATA_DIR", str(data_dir))
        get_settings.cache_clear()
        app = AppTest.from_file(str(APP), default_timeout=30)
        app.run()
        return app

    yield _run
    get_settings.cache_clear()


def _metrics(app: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in app.metric}


def _data_2024(openf1_data):
    for endpoint in (Endpoint.MEETINGS, Endpoint.SESSIONS):
        for record in openf1_data[endpoint]:
            record["year"] = 2024
    return openf1_data


def test_dashboard_shows_platform_metrics(run_app, populated_lake):
    app = run_app(populated_lake)

    assert not app.exception
    assert app.title[0].value == "F1 — Data Lake OpenF1"
    metrics = _metrics(app)
    assert metrics["Arquivos na bronze"] == "14"
    assert metrics["Registros processados"] == "31"
    assert metrics["Registros rejeitados"] == "1"
    assert metrics["Último run_id"] == "run-2"
    assert metrics["Última execução"].endswith("UTC")
    assert len(app.dataframe) == 2
    assert not app.info
    assert not app.success  # lake com dados: não roda a carga inicial


def test_empty_lake_runs_calendar_once(run_app, tmp_path, client_factory, openf1_data):
    stub = StubClient(_data_2024(openf1_data))
    client_factory["client"] = stub
    data_dir = tmp_path / "empty"

    app = run_app(data_dir)

    assert not app.exception
    assert "Calendário de 2024 carregado: 1 meetings" in app.success[0].value
    assert (data_dir / "silver/meetings/season=2024/part-00000.parquet").exists()
    assert _metrics(app)["Registros processados"] == "5"  # 2 meetings + 3 sessions
    assert not app.info

    calls = len(stub.calls)
    app.run()  # novo rerun: lake não está mais vazio e o recurso está em cache
    assert len(stub.calls) == calls


def test_access_error_shows_friendly_message_and_retries(
    run_app, tmp_path, client_factory, openf1_data
):
    app = run_app(tmp_path / "empty")

    assert not app.exception
    assert "temporariamente indisponível" in app.warning[0].value
    assert "Nenhum dado encontrado" in app.info[0].value
    assert _metrics(app)["Último run_id"] == "—"

    # A falha não fica em cache: quando a API volta, o próximo rerun carrega.
    client_factory["client"] = StubClient(_data_2024(openf1_data))
    app.run()
    assert not app.warning
    assert app.success


def test_other_api_errors_show_generic_message(run_app, tmp_path, client_factory):
    client_factory["client"] = FailingClient({})
    app = run_app(tmp_path / "empty")

    assert not app.exception
    assert "Não foi possível carregar" in app.error[0].value


def test_reload_button_reruns(run_app, populated_lake):
    app = run_app(populated_lake)
    app.button[0].click().run()

    assert not app.exception
    assert _metrics(app)["Registros processados"] == "31"
