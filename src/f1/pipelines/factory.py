"""Composição dos stores do data lake a partir das configurações."""

import pandas as pd

from f1.config.settings import Settings
from f1.domain.ports import AppendStore
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
from f1.storage.supabase_history import MirroredHistoryStore, SupabaseHistorySink


def build_stores(settings: Settings) -> LakeStores:
    """Stores bronze, silver, quarentena e histórico sob ``settings.data_dir``.

    Com ``F1_SUPABASE_URL`` e ``F1_SUPABASE_KEY``, o histórico também é
    enviado ao Supabase.
    """
    data_dir = settings.data_dir
    rejections: AppendStore[pd.DataFrame] = RejectionHistoryStore(
        layer_path(data_dir, REJECTION_HISTORY)
    )
    if settings.supabase_url and settings.supabase_key:
        sink = SupabaseHistorySink(
            settings.supabase_url,
            settings.supabase_key,
            settings.history_environment,
        )
        rejections = MirroredHistoryStore(rejections, sink)
    return LakeStores(
        raw=JsonRawStore(layer_path(data_dir, BRONZE)),
        silver=ParquetDatasetStore(layer_path(data_dir, SILVER)),
        quarantine=QuarantineStore(layer_path(data_dir, QUARANTINE)),
        rejections=rejections,
    )
