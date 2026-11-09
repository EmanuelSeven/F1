"""Escrita atômica de partições Parquet (overwrite por partição)."""

from pathlib import Path

import pandas as pd

from f1.domain.models import Partition
from f1.storage.atomic import (
    path_lock,
    remove_stale_temps,
    swap_directory,
    temp_sibling,
)
from f1.storage.paths import partition_path

PART_FILE = "part-00000.parquet"


def write_partition(df: pd.DataFrame, partition_dir: Path) -> Path:
    """Sobrescreve a partição de forma atômica, garantindo idempotência.

    Grava num diretório de staging irmão e exclusivo desta gravação (prefixo
    ``_``, ignorado por leitores Parquet) e só então substitui a partição final.
    Gravações concorrentes na mesma partição são seguras: a última vence.
    """
    staging = temp_sibling(partition_dir, ".staging")
    staging.mkdir(parents=True)
    df.to_parquet(staging / PART_FILE, index=False, compression="zstd")
    with path_lock(partition_dir):
        swap_directory(staging, partition_dir)
        remove_stale_temps(partition_dir)
    return partition_dir


def read_partition(partition_dir: Path) -> pd.DataFrame:
    """Lê o arquivo de uma partição gravada por ``write_partition``."""
    return pd.read_parquet(partition_dir / PART_FILE)


class ParquetDatasetStore:
    """Implementa ``DatasetStore[pd.DataFrame]`` sobre um diretório base."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def path_for(self, dataset: str, partition: Partition) -> Path:
        return partition_path(self._base, dataset, partition)

    def write_partition(
        self, dataset: str, partition: Partition, frame: pd.DataFrame
    ) -> Path | None:
        return write_partition(frame, self.path_for(dataset, partition))

    def read_partition(self, dataset: str, partition: Partition) -> pd.DataFrame:
        return read_partition(self.path_for(dataset, partition))
