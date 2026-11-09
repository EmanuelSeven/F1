import pytest

from f1.pipelines.common import LakeStores, RunContext
from f1.storage.bronze import JsonRawStore
from f1.storage.parquet_writer import ParquetDatasetStore
from f1.storage.quarantine import QuarantineStore
from f1.storage.rejection_history import RejectionHistoryStore


@pytest.fixture
def stores(tmp_path) -> LakeStores:
    return LakeStores(
        raw=JsonRawStore(tmp_path / "bronze"),
        silver=ParquetDatasetStore(tmp_path / "silver"),
        quarantine=QuarantineStore(tmp_path / "quarantine"),
        rejections=RejectionHistoryStore(tmp_path / "rejection_history"),
    )


@pytest.fixture
def ctx() -> RunContext:
    return RunContext(run_id="run-test", max_rejection_rate=0.05)
