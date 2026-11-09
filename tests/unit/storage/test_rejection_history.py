from datetime import UTC, datetime

import pandas as pd
import pytest

from f1.domain.models import Partition
from f1.storage.rejection_history import (
    RejectionHistoryStore,
    count_by_rule,
    rejection_rows,
)

PARTITION = Partition(2023, 1219)
NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


def _rows(run_id: str, reasons: list[str], records_read: int = 10) -> pd.DataFrame:
    return rejection_rows(
        run_id=run_id,
        recorded_at=NOW,
        dataset="laps",
        partition=PARTITION,
        rejected=pd.DataFrame({"_reject_reason": reasons}),
        records_read=records_read,
        aborted=False,
    )


def test_count_by_rule_splits_rows_with_several_rules():
    rejected = pd.DataFrame({"_reject_reason": ["a:x; b:y", "a:x", "b:y; c:z"]})
    assert count_by_rule(rejected).to_dict() == {"a:x": 2, "b:y": 2, "c:z": 1}


def test_rejection_rows_one_per_rule():
    rows = _rows("r1", ["a:x; b:y", "a:x"])
    columns = ["rule", "rejected", "records_read", "rows_rejected"]
    assert rows[columns].values.tolist() == [
        ["a:x", 2, 10, 2],  # rows_rejected: 2 linhas, mesmo com 3 violações
        ["b:y", 1, 10, 2],
    ]
    assert rows["meeting_key"].tolist() == [1219, 1219]


def test_rejection_rows_records_clean_load():
    [row] = _rows("r1", []).to_dict("records")
    assert pd.isna(row["rule"])
    assert (row["rejected"], row["records_read"]) == (0, 10)


def test_append_keeps_previous_runs(tmp_path):
    store = RejectionHistoryStore(tmp_path)
    first = store.append("laps", PARTITION, _rows("r1", ["a:x"]))
    store.append("laps", PARTITION, _rows("r2", []))
    store.append("laps", PARTITION, _rows("r1", ["a:x", "a:x"]))  # mesma carga

    files = sorted(p.name for p in first.parent.iterdir())
    assert files == ["run_id=r1.parquet", "run_id=r2.parquet"]
    assert pd.read_parquet(first)["rejected"].tolist() == [2]


def test_append_requires_single_run_id(tmp_path):
    rows = pd.concat([_rows("r1", []), _rows("r2", [])])
    with pytest.raises(ValueError, match="run_id"):
        RejectionHistoryStore(tmp_path).append("laps", PARTITION, rows)
