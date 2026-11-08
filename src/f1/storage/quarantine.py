"""Quarentena: registros rejeitados pela validação, com motivo e ``run_id``."""

import shutil
from pathlib import Path

import pandas as pd

from f1.domain.models import Partition
from f1.storage.parquet_writer import ParquetDatasetStore, write_partition

REJECT_REASON = "_reject_reason"
REQUIRED_COLUMNS = (REJECT_REASON, "_run_id")


class QuarantineStore(ParquetDatasetStore):
    """Grava rejeitados na mesma partição do dataset de origem.

    Sem rejeitados, a partição de quarentena é removida, para que a reexecução
    reflita apenas o resultado da última carga (idempotência).
    """

    def write_partition(
        self, dataset: str, partition: Partition, frame: pd.DataFrame
    ) -> Path | None:
        target = self.path_for(dataset, partition)
        if frame.empty:
            shutil.rmtree(target, ignore_errors=True)
            return None
        missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
        if missing:
            raise ValueError(f"quarantine frame missing columns: {missing}")
        return write_partition(frame, target)
