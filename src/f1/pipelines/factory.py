"""Composição dos stores do data lake a partir das configurações."""

from f1.config.settings import Settings
from f1.pipelines.common import LakeStores
from f1.storage.bronze import JsonRawStore
from f1.storage.parquet_writer import ParquetDatasetStore
from f1.storage.paths import (
    BRONZE,
    QUARANTINE,
    REJECTION_HISTORY,
    SILVER,
    layer_path,
)
from f1.storage.quarantine import QuarantineStore
from f1.storage.rejection_history import RejectionHistoryStore


def build_stores(settings: Settings) -> LakeStores:
    """Stores bronze, silver, quarentena e histórico sob ``settings.data_dir``."""
    data_dir = settings.data_dir
    return LakeStores(
        raw=JsonRawStore(layer_path(data_dir, BRONZE)),
        silver=ParquetDatasetStore(layer_path(data_dir, SILVER)),
        quarantine=QuarantineStore(layer_path(data_dir, QUARANTINE)),
        rejections=RejectionHistoryStore(layer_path(data_dir, REJECTION_HISTORY)),
    )
