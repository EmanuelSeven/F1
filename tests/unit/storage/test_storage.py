import json

import pandas as pd
import pytest

from f1.domain.endpoints import Endpoint
from f1.domain.models import Partition
from f1.storage.bronze import JsonRawStore
from f1.storage.parquet_writer import ParquetDatasetStore, write_partition
from f1.storage.paths import SILVER, layer_path, partition_path
from f1.storage.quarantine import QuarantineStore

PARTITION = Partition(2023, 1219)


def test_partition_path_layout(tmp_path):
    base = layer_path(tmp_path, SILVER)
    assert partition_path(base, "laps", PARTITION) == (
        tmp_path / "silver" / "laps" / "season=2023" / "meeting_key=1219"
    )
    assert partition_path(base, "meetings", Partition(2023)).name == "season=2023"


def test_raw_store_writes_utf8_json_idempotently(tmp_path):
    store = JsonRawStore(tmp_path)
    records = [{"location": "São Paulo", "lap": 1}]

    first = store.write(Endpoint.LAPS, PARTITION, "session_key=9165", records)
    content = first.read_bytes()
    second = store.write(Endpoint.LAPS, PARTITION, "session_key=9165", records)

    assert first == second
    assert first == tmp_path / "laps/season=2023/meeting_key=1219/session_key=9165.json"
    assert second.read_bytes() == content
    assert json.loads(content.decode("utf-8")) == records
    assert [p.name for p in first.parent.iterdir()] == ["session_key=9165.json"]


def test_write_partition_overwrites_atomically(tmp_path):
    target = tmp_path / "laps" / "season=2023"
    write_partition(pd.DataFrame({"a": [1, 2, 3]}), target)
    write_partition(pd.DataFrame({"a": [9]}), target)

    assert pd.read_parquet(target)["a"].tolist() == [9]
    assert sorted(p.name for p in target.parent.iterdir()) == ["season=2023"]


def test_dataset_store_roundtrip_preserves_nullable_dtypes(tmp_path):
    store = ParquetDatasetStore(tmp_path)
    df = pd.DataFrame(
        {
            "n": pd.array([1, None], dtype="Int64"),
            "s": pd.array(["x", None], dtype="string"),
        }
    )
    store.write_partition("laps", PARTITION, df)

    result = store.read_partition("laps", PARTITION)
    pd.testing.assert_frame_equal(result, df)


def test_quarantine_writes_and_clears(tmp_path):
    store = QuarantineStore(tmp_path)
    rejected = pd.DataFrame(
        {"lap_number": [0], "_reject_reason": ["x"], "_run_id": ["r"]}
    )

    path = store.write_partition("laps", PARTITION, rejected)
    assert path is not None
    assert store.read_partition("laps", PARTITION)["_reject_reason"].tolist() == ["x"]

    assert store.write_partition("laps", PARTITION, rejected.iloc[0:0]) is None
    assert not path.exists()


def test_quarantine_requires_reason_and_run_id(tmp_path):
    with pytest.raises(ValueError, match="_reject_reason"):
        QuarantineStore(tmp_path).write_partition(
            "laps", PARTITION, pd.DataFrame({"a": [1]})
        )
