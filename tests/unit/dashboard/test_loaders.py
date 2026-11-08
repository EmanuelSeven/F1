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
    read_lineage,
)


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
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 2, tzinfo=UTC),
                    datetime(2024, 1, 3, tzinfo=UTC),
                ],
                dtype="datetime64[ns, UTC]",
            ),
        }
    )
    run = latest_run(lineage)
    assert run is not None
    assert (run.run_id, run.ingested_at) == ("new", datetime(2024, 1, 2, tzinfo=UTC))


def test_tables_have_one_row_per_item(populated_lake):
    summary = load_platform_summary(populated_lake)

    datasets = datasets_table(summary)
    assert len(datasets) == 8
    assert datasets.set_index("dataset").loc["laps", "rejeitados"] == 1
    layers = layers_table(summary)
    assert layers["camada"].tolist() == ["bronze", "silver", "quarantine"]
