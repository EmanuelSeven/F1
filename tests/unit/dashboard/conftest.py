from pathlib import Path

import pytest

from f1.domain.endpoints import Endpoint
from f1.ingestion.openf1_client import OpenF1AccessError, OpenF1Error
from f1.pipelines.calendar import run_calendar
from f1.pipelines.common import LakeStores, RunContext
from f1.pipelines.meeting import fetch_meeting, run_meeting
from f1.storage.bronze import JsonRawStore
from f1.storage.parquet_writer import ParquetDatasetStore
from f1.storage.quarantine import QuarantineStore
from tests.conftest import FakeOpenF1Source


def _stores(data_dir: Path) -> LakeStores:
    return LakeStores(
        raw=JsonRawStore(data_dir / "bronze"),
        silver=ParquetDatasetStore(data_dir / "silver"),
        quarantine=QuarantineStore(data_dir / "quarantine"),
    )


@pytest.fixture
def populated_lake(tmp_path, openf1_data) -> Path:
    """Lake gerado pelas pipelines reais: 2 execuções, 1 lap rejeitada na 2ª."""
    data_dir = tmp_path / "data"
    stores = _stores(data_dir)
    source = FakeOpenF1Source(openf1_data)
    run_calendar(source, stores, RunContext("run-1"), 2023)

    laps = openf1_data[Endpoint.LAPS]
    openf1_data[Endpoint.LAPS] = [*laps, {**laps[-1], "lap_number": 0}]
    ctx = RunContext("run-2", max_rejection_rate=0.5)
    run_meeting(source, stores, ctx, fetch_meeting(source, 1219))
    return data_dir


class StubClient(FakeOpenF1Source):
    """Fonte falsa usável como context manager (como o OpenF1Client)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


class DeniedClient(StubClient):
    def fetch(self, endpoint, filters=()):
        raise OpenF1AccessError("Live F1 session in progress")


class FailingClient(StubClient):
    def fetch(self, endpoint, filters=()):
        raise OpenF1Error("connection reset")


def as_season(openf1_data, year: int):
    """Fixtures (Singapura 2023) relabeladas como outra temporada."""
    for endpoint in (Endpoint.MEETINGS, Endpoint.SESSIONS):
        for record in openf1_data[endpoint]:
            record["year"] = year
    return openf1_data


def season_page_script() -> None:
    """Roteador reduzido à página Temporada (o AppTest não troca de página).

    Para uso com ``AppTest.from_function``: só o corpo da função é executado.
    """
    from f1.config.settings import get_settings  # noqa: PLC0415
    from f1.dashboard.views.season import render_season  # noqa: PLC0415
    from f1.dashboard.views.sidebar import (  # noqa: PLC0415
        SEASON_PAGE,
        render_sidebar_filters,
        render_sidebar_footer,
    )
    from f1.dashboard.views.theme import prevent_translation  # noqa: PLC0415

    prevent_translation()
    data_dir = get_settings().data_dir
    render_sidebar_filters(data_dir, SEASON_PAGE)
    render_season()
    render_sidebar_footer(data_dir)
