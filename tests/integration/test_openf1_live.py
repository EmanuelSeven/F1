"""Testes ponta a ponta contra a OpenF1 real (requer internet)."""

import pytest

from f1.config.settings import Settings
from f1.domain.endpoints import Endpoint
from f1.domain.models import MeetingRef, Partition
from f1.ingestion.openf1_client import OpenF1AccessError, OpenF1Client
from f1.pipelines.common import LakeStores, RunContext
from f1.pipelines.meeting import fetch_meeting, run_meeting
from f1.storage.bronze import JsonRawStore
from f1.storage.parquet_writer import ParquetDatasetStore
from f1.storage.quarantine import QuarantineStore

SINGAPORE_2023 = 1219

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    with OpenF1Client.from_settings(Settings(_env_file=None)) as live:
        yield live


def _meeting_or_skip(client: OpenF1Client) -> MeetingRef:
    try:
        return fetch_meeting(client, SINGAPORE_2023)
    except OpenF1AccessError as exc:  # sessão ao vivo bloqueia o acesso gratuito
        pytest.skip(str(exc))


def test_live_meeting_end_to_end(client, tmp_path):
    meeting = _meeting_or_skip(client)
    stores = LakeStores(
        raw=JsonRawStore(tmp_path / "bronze"),
        silver=ParquetDatasetStore(tmp_path / "silver"),
        quarantine=QuarantineStore(tmp_path / "quarantine"),
    )
    ctx = RunContext(run_id="integration", max_rejection_rate=0.05)

    metrics = run_meeting(
        client, stores, ctx, meeting, [Endpoint.DRIVERS, Endpoint.STINTS]
    )

    assert all(m.records_read > 0 for m in metrics)
    drivers = stores.silver.read_partition(
        "drivers", Partition(meeting.year, meeting.meeting_key)
    )
    assert drivers["driver_number"].notna().all()
