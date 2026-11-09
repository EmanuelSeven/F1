from datetime import UTC, datetime, timedelta, timezone

import pandas as pd

from f1.processing.lineage import add_lineage_columns


def test_add_lineage_columns_values_and_dtypes():
    df = pd.DataFrame({"a": [1, 2]})
    at = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=-3)))

    out = add_lineage_columns(df, "run-1", "laps", ingested_at=at)

    assert out["_run_id"].tolist() == ["run-1", "run-1"]
    assert out["_source"].tolist() == ["laps", "laps"]
    assert out["_ingested_at"].iloc[0] == datetime(2026, 1, 1, 15, tzinfo=UTC)
    assert str(out["_ingested_at"].dtype) == "datetime64[ns, UTC]"
    assert "_run_id" not in df.columns


def test_add_lineage_columns_on_empty_frame_defaults_to_now():
    out = add_lineage_columns(pd.DataFrame({"a": []}), "r", "s")

    assert out.empty
    assert list(out.columns) == ["a", "_run_id", "_ingested_at", "_source"]
