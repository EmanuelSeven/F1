from datetime import UTC, datetime

import pandas as pd

from f1.dashboard.loaders import (
    datasets_table,
    iter_data_files,
    latest_run,
    layers_table,
    load_dataset_summary,
    load_layer_status,
    load_platform_summary,
    load_race_details,
    load_season_data,
    race_details_loaded,
    read_dataset,
    read_lineage,
    rejection_trend,
    season_is_loaded,
)
from f1.domain.endpoints import Endpoint
from f1.domain.models import Partition
from f1.storage.parquet_writer import ParquetDatasetStore
from f1.storage.rejection_history import COLUMNS, rejection_rows


def _history(*loads: tuple[str, int, int, list[str], int]) -> pd.DataFrame:
    """Linhas do histórico: (run_id, hora, meeting_key, motivos, lidos)."""
    frames = [
        rejection_rows(
            run_id=run_id,
            recorded_at=datetime(2026, 11, 9, hour, tzinfo=UTC),
            dataset="laps",
            partition=Partition(2023, meeting_key),
            rejected=pd.DataFrame({"_reject_reason": reasons}),
            records_read=read,
            aborted=False,
        )
        for run_id, hour, meeting_key, reasons, read in loads
    ]
    return pd.concat(frames, ignore_index=True).astype(COLUMNS)


def test_rejection_trend_rate_per_rule_and_run():
    history = _history(
        ("r1", 10, 1, ["a:x", "a:x; b:y"], 10),
        ("r1", 10, 2, ["a:x"], 10),
        ("r2", 11, 1, [], 20),  # carga limpa: zero para todas as regras
        ("r3", 12, 2, ["b:y"], 5),
    )

    trend = rejection_trend(history, "laps")

    rows = trend[["run_id", "rule", "rejected", "records_read", "rate"]]
    assert rows.values.tolist() == [
        ["r1", "a:x", 3, 20, 0.15],
        ["r1", "b:y", 1, 20, 0.05],
        ["r2", "a:x", 0, 20, 0.0],
        ["r2", "b:y", 0, 20, 0.0],
        ["r3", "a:x", 0, 5, 0.0],
        ["r3", "b:y", 1, 5, 0.2],
    ]


def test_rejection_trend_filters_meeting_and_dataset():
    history = _history(
        ("r1", 10, 1, ["a:x"], 10),
        ("r2", 11, 2, ["a:x"], 4),
    )

    trend = rejection_trend(history, "laps", meeting_key=2)
    assert trend[["run_id", "rate"]].values.tolist() == [["r2", 0.25]]
    assert rejection_trend(history, "stints").empty
    assert rejection_trend(_history(("r1", 10, 1, [], 10)), "laps").empty


def test_platform_summary_counts_layers_records_and_rejections(populated_lake):
    summary = load_platform_summary(populated_lake)

    # bronze: meetings + sessions (calendário) + 6 datasets x 2 sessões
    assert summary.bronze_files == 14
    # silver: 2 meetings + 3 sessions + 4+4+8+4+2+4 do meeting 1219
    assert summary.records_processed == 31
    assert summary.records_rejected == 1
    assert summary.last_run is not None
    assert summary.last_run.run_id == "run-2"
    assert summary.last_run.ingested_at.tzinfo is not None


def test_dataset_summary_for_laps(populated_lake):
    laps = load_dataset_summary(populated_lake, "laps")

    assert (laps.partitions, laps.records, laps.rejected) == (1, 8, 1)
    assert laps.last_run is not None and laps.last_run.run_id == "run-2"


def test_layer_status_lists_datasets(populated_lake):
    quarantine = load_layer_status(populated_lake, "quarantine")

    assert quarantine.exists
    assert quarantine.datasets == ("laps",)
    assert quarantine.files == 1
    assert quarantine.size_bytes > 0


def test_empty_lake(tmp_path):
    summary = load_platform_summary(tmp_path / "missing")

    assert summary.bronze_files == 0
    assert summary.records_processed == 0
    assert summary.last_run is None
    assert not any(layer.exists for layer in summary.layers)
    assert all(d.last_run is None for d in summary.datasets)


def test_iter_data_files_ignores_staging_and_temp(tmp_path):
    (tmp_path / "laps" / "_season=2023.staging").mkdir(parents=True)
    (tmp_path / "laps" / "_season=2023.staging" / "part-00000.parquet").write_bytes(b"")
    (tmp_path / "laps" / "season=2023").mkdir()
    (tmp_path / "laps" / "season=2023" / "part-00000.parquet").write_bytes(b"")
    (tmp_path / "laps" / "season=2023" / "_x.json.tmp").write_bytes(b"")

    files = list(iter_data_files(tmp_path, "*.parquet"))

    assert [f.parent.name for f in files] == ["season=2023"]


def test_read_lineage_without_files_is_typed_empty():
    lineage = read_lineage([])
    assert lineage.empty
    assert str(lineage["_ingested_at"].dtype) == "datetime64[ns, UTC]"
    assert latest_run(lineage) is None


def test_latest_run_picks_most_recent():
    lineage = pd.DataFrame(
        {
            "_run_id": pd.array(["old", "new", None], dtype="string"),
            "_ingested_at": pd.Series(
                [
                    datetime(2026, 1, 1, tzinfo=UTC),
                    datetime(2026, 1, 2, tzinfo=UTC),
                    datetime(2026, 1, 3, tzinfo=UTC),
                ],
                dtype="datetime64[ns, UTC]",
            ),
        }
    )
    run = latest_run(lineage)
    assert run is not None
    assert (run.run_id, run.ingested_at) == ("new", datetime(2026, 1, 2, tzinfo=UTC))


def test_tables_have_one_row_per_item(populated_lake):
    summary = load_platform_summary(populated_lake)

    datasets = datasets_table(summary)
    assert len(datasets) == 9  # inclui starting_grid
    assert datasets.set_index("dataset").loc["laps", "rejeitados"] == 1
    layers = layers_table(summary)
    assert layers["camada"].tolist() == ["bronze", "silver", "quarantine"]


def test_read_dataset_empty_is_typed(tmp_path):
    df = read_dataset(tmp_path, Endpoint.SESSION_RESULT, 2026)

    assert df.empty
    assert str(df["points"].dtype) == "Float64"


def test_read_dataset_adds_columns_missing_from_old_partitions(populated_lake):
    store = ParquetDatasetStore(populated_lake / "silver")
    partition = Partition(2023, 1219)
    old = store.read_partition("session_results", partition).drop(columns=["points"])
    store.write_partition("session_results", partition, old)

    df = read_dataset(populated_lake, Endpoint.SESSION_RESULT, 2023)

    assert len(df) == 4
    assert df["points"].isna().all()


def test_season_and_race_readers(populated_lake):
    assert season_is_loaded(populated_lake, 2023)
    assert not season_is_loaded(populated_lake, 2026)
    assert race_details_loaded(populated_lake, 2023, 1219)
    assert not race_details_loaded(populated_lake, 2023, 1)

    season = load_season_data(populated_lake, 2023)
    assert (len(season.meetings), len(season.sessions)) == (2, 3)
    assert (len(season.drivers), len(season.results)) == (4, 4)

    details = load_race_details(populated_lake, 2023, 1219)
    assert (len(details.laps), len(details.stints)) == (8, 4)
    assert (len(details.pit_stops), len(details.weather)) == (2, 4)
