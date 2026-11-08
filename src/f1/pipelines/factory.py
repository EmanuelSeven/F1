"""Composição dos stores do data lake a partir das configurações."""

from f1.config.settings import Settings
from f1.pipelines.common import LakeStores
from f1.storage.bronze import JsonRawStore
from f1.storage.parquet_writer import ParquetDatasetStore
from f1.storage.paths import BRONZE, QUARANTINE, SILVER, layer_path
from f1.storage.quarantine import QuarantineStore


def build_stores(settings: Settings) -> LakeStores:
    """Stores bronze, silver e quarentena sob ``settings.data_dir``."""
    return LakeStores(
        raw=JsonRawStore(layer_path(settings.data_dir, BRONZE)),
        silver=ParquetDatasetStore(layer_path(settings.data_dir, SILVER)),
        quarantine=QuarantineStore(layer_path(settings.data_dir, QUARANTINE)),
    )
