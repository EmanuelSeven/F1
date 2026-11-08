from pathlib import Path

import pytest

from f1.domain.endpoints import Endpoint
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
