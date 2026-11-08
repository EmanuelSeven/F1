import pytest

from f1.domain.endpoints import Endpoint
from f1.domain.models import Partition, SessionRef
from f1.pipelines.results import run_results

QUALI = SessionRef(9161, 1219, "Qualifying", "Qualifying")
RACE = SessionRef(9165, 1219, "Race", "Race")


def test_run_results_loads_drivers_and_results_per_meeting(
    fake_source, stores, ctx, tmp_path
):
    metrics = run_results(fake_source, stores, ctx, 2023, [RACE])

    assert [(m.pipeline, m.records_processed) for m in metrics] == [
        ("silver.drivers", 2),
        ("silver.session_results", 2),
    ]
    partition = Partition(2023, 1219)
    results = stores.silver.read_partition("session_results", partition)
    assert results["session_key"].unique().tolist() == [9165]
    assert results["points"].tolist() == [25.0, 10.0]
    bronze = tmp_path / "bronze/session_result/season=2023/meeting_key=1219"
    assert [p.name for p in bronze.iterdir()] == ["session_key=9165.json"]


def test_run_results_batches_session_keys(fake_source, stores, ctx):
    run_results(fake_source, stores, ctx, 2023, [QUALI, RACE])
    filters = [c[1][0] for c in fake_source.calls]
    assert [f.value for f in filters] == [(9161, 9165), (9161, 9165)]

    fake_source.calls.clear()
    run_results(fake_source, stores, ctx, 2023, [QUALI, RACE], chunk_size=1)
    assert len(fake_source.calls) == 4  # 2 endpoints x 2 lotes


def test_run_results_writes_empty_bronze_for_sessions_without_data(
    fake_source, stores, ctx, tmp_path
):
    missing = SessionRef(1, 1219, "Sprint", "Race")
    run_results(fake_source, stores, ctx, 2023, [missing])

    raw = tmp_path / "bronze/drivers/season=2023/meeting_key=1219/session_key=1.json"
    assert raw.read_text(encoding="utf-8") == "[]"
    assert stores.silver.read_partition("drivers", Partition(2023, 1219)).empty


def test_run_results_is_idempotent(fake_source, stores, ctx):
    run_results(fake_source, stores, ctx, 2023, [RACE])
    first = stores.silver.read_partition("drivers", Partition(2023, 1219))
    run_results(fake_source, stores, ctx, 2023, [RACE])
    second = stores.silver.read_partition("drivers", Partition(2023, 1219))

    assert len(first) == len(second) == 2


def test_run_results_rejects_invalid_chunk(fake_source, stores, ctx):
    with pytest.raises(ValueError, match="chunk_size"):
        run_results(fake_source, stores, ctx, 2023, [RACE], chunk_size=0)


def test_result_endpoints_are_drivers_and_results(fake_source, stores, ctx):
    run_results(fake_source, stores, ctx, 2023, [RACE])
    assert {c[0] for c in fake_source.calls} == {
        Endpoint.DRIVERS,
        Endpoint.SESSION_RESULT,
    }
