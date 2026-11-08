"""Testes do script Streamlit (src/f1/dashboard.py) com o AppTest."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from f1.config.settings import get_settings

APP = Path(__file__).parents[3] / "src" / "f1" / "dashboard.py"


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


def test_dashboard_without_data_shows_hint(run_app, tmp_path):
    app = run_app(tmp_path / "empty")

    assert not app.exception
    assert "Nenhum dado encontrado" in app.info[0].value
    assert _metrics(app)["Último run_id"] == "—"


def test_reload_button_reruns(run_app, populated_lake):
    app = run_app(populated_lake)
    app.button[0].click().run()

    assert not app.exception
    assert _metrics(app)["Registros processados"] == "31"
