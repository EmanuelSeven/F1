import pandas as pd
import pytest

from f1.domain.endpoints import Endpoint
from f1.domain.models import MeetingRef, Partition
from f1.pipelines.common import RunContext
from f1.pipelines.meeting import MeetingNotFoundError, fetch_meeting, run_meeting
from f1.quality.validation import DataQualityError
from tests.conftest import FakeOpenF1Source

PARTITION = Partition(2023, 1219)
LINEAGE = ["_run_id", "_ingested_at", "_source"]


def test_fetch_meeting(fake_source):
    meeting = fetch_meeting(fake_source, 1219)
    assert meeting == MeetingRef.from_record(fake_source.fetch(Endpoint.MEETINGS)[0])


def test_fetch_meeting_not_found(fake_source):
    with pytest.raises(MeetingNotFoundError):
        fetch_meeting(fake_source, 1)


def test_run_meeting_loads_all_session_datasets(fake_source, stores, ctx, tmp_path):
    metrics = run_meeting(fake_source, stores, ctx, fetch_meeting(fake_source, 1219))

    expected = {
        "silver.drivers": 4,
        "silver.session_results": 4,
        "silver.laps": 8,
        "silver.stints": 4,
        "silver.pit_stops": 2,
        "silver.weather": 4,
    }
    assert {m.pipeline: m.records_processed for m in metrics} == expected
    assert all(m.records_rejected == 0 and m.run_id == "run-test" for m in metrics)

    bronze = tmp_path / "bronze/laps/season=2023/meeting_key=1219"
    assert sorted(p.name for p in bronze.iterdir()) == [
        "session_key=9161.json",
        "session_key=9165.json",
    ]
    laps = stores.silver.read_partition("laps", PARTITION)
    assert len(laps) == 8
    assert laps["_source"].unique().tolist() == ["laps"]


def test_run_meeting_is_idempotent(fake_source, stores, ctx):
    meeting = fetch_meeting(fake_source, 1219)
    run_meeting(fake_source, stores, ctx, meeting, [Endpoint.LAPS])
    first = stores.silver.read_partition("laps", PARTITION)

    run_meeting(fake_source, stores, RunContext("run-2"), meeting, [Endpoint.LAPS])
    second = stores.silver.read_partition("laps", PARTITION)

    pd.testing.assert_frame_equal(
        first.drop(columns=LINEAGE), second.drop(columns=LINEAGE)
    )
    assert second["_run_id"].unique().tolist() == ["run-2"]


def test_run_meeting_quarantines_invalid_rows(openf1_data, stores, tmp_path):
    laps = openf1_data[Endpoint.LAPS]
    openf1_data[Endpoint.LAPS] = [*laps, {**laps[-1], "lap_number": 0}]
    source = FakeOpenF1Source(openf1_data)
    ctx = RunContext("run-q", max_rejection_rate=0.5)

    [metrics] = run_meeting(
        source, stores, ctx, fetch_meeting(source, 1219), [Endpoint.LAPS]
    )

    assert (metrics.records_processed, metrics.records_rejected) == (8, 1)
    rejected = stores.quarantine.read_partition("laps", PARTITION)
    assert rejected["_reject_reason"].str.contains("lap_number").all()
    assert rejected["_run_id"].tolist() == ["run-q"]

    # Reexecução sem rejeitados limpa a quarentena.
    clean = FakeOpenF1Source({**openf1_data, Endpoint.LAPS: laps})
    run_meeting(clean, stores, ctx, fetch_meeting(clean, 1219), [Endpoint.LAPS])
    assert not (tmp_path / "quarantine/laps/season=2023/meeting_key=1219").exists()


def test_run_meeting_fails_above_rejection_rate(openf1_data, stores, ctx):
    openf1_data[Endpoint.PIT][0]["lap_number"] = 0
    source = FakeOpenF1Source(openf1_data)

    with pytest.raises(DataQualityError):
        run_meeting(source, stores, ctx, fetch_meeting(source, 1219), [Endpoint.PIT])
    assert len(stores.quarantine.read_partition("pit_stops", PARTITION)) == 1


def test_run_meeting_rejects_calendar_endpoints(fake_source, stores, ctx):
    with pytest.raises(ValueError, match="not session-level"):
        run_meeting(
            fake_source, stores, ctx, MeetingRef(1219, 2023, "x"), [Endpoint.MEETINGS]
        )


def test_run_meeting_skips_cancelled_sessions(fake_source, stores, ctx):
    run_meeting(
        fake_source, stores, ctx, MeetingRef(1210, 2023, "Imola"), [Endpoint.LAPS]
    )

    laps = stores.silver.read_partition("laps", Partition(2023, 1210))
    assert laps.empty
    assert all(c[0] is not Endpoint.LAPS for c in fake_source.calls)
