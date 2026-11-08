"""Resolução de caminhos do data lake: ``{base}/{dataset}/season=Y[/meeting_key=N]``."""

from pathlib import Path

from f1.domain.models import Partition

BRONZE = "bronze"
SILVER = "silver"
QUARANTINE = "quarantine"


def layer_path(data_dir: Path, layer: str) -> Path:
    """Diretório raiz de uma camada (``bronze``, ``silver``, ``quarantine``)."""
    return data_dir / layer


def partition_path(base: Path, dataset: str, partition: Partition) -> Path:
    """Diretório de uma partição de dataset."""
    return base.joinpath(dataset, *partition.segments())
