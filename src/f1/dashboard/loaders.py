"""Leitura e agregação do data lake para o dashboard (sem visualização).

Lê apenas metadados e as colunas de linhagem dos arquivos Parquet, sem carregar
os datasets inteiros.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from f1.domain.endpoints import DATASET_SPECS
from f1.domain.models import INGESTED_AT, RUN_ID
from f1.storage.paths import BRONZE, QUARANTINE, SILVER, layer_path

LAYERS: tuple[str, ...] = (BRONZE, SILVER, QUARANTINE)
_LAYER_PATTERNS = {BRONZE: "*.json", SILVER: "*.parquet", QUARANTINE: "*.parquet"}
_LINEAGE_COLUMNS = [RUN_ID, INGESTED_AT]


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    ingested_at: datetime


@dataclass(frozen=True)
class LayerStatus:
    layer: str
    path: Path
    exists: bool
    files: int
    datasets: tuple[str, ...]
    size_bytes: int


@dataclass(frozen=True)
class DatasetSummary:
    dataset: str
    partitions: int
    records: int
    rejected: int
    last_run: RunInfo | None


@dataclass(frozen=True)
class PlatformSummary:
    data_dir: Path
    layers: tuple[LayerStatus, ...]
    datasets: tuple[DatasetSummary, ...]
    last_run: RunInfo | None

    @property
    def bronze_files(self) -> int:
        return self.layer(BRONZE).files

    @property
    def records_processed(self) -> int:
        return sum(d.records for d in self.datasets)

    @property
    def records_rejected(self) -> int:
        return sum(d.rejected for d in self.datasets)

    def layer(self, name: str) -> LayerStatus:
        return next(item for item in self.layers if item.layer == name)


def iter_data_files(base: Path, pattern: str) -> Iterator[Path]:
    """Arquivos de dados sob ``base``, ignorando staging/temporários (prefixo ``_``)."""
    if not base.is_dir():
        return
    for path in sorted(base.rglob(pattern)):
        relative = path.relative_to(base).parts
        if path.is_file() and not any(part.startswith("_") for part in relative):
            yield path


def load_layer_status(data_dir: Path, layer: str) -> LayerStatus:
    """Quantidade de arquivos, datasets e tamanho de uma camada."""
    base = layer_path(data_dir, layer)
    files = list(iter_data_files(base, _LAYER_PATTERNS[layer]))
    datasets = sorted({f.relative_to(base).parts[0] for f in files})
    return LayerStatus(
        layer=layer,
        path=base,
        exists=base.is_dir(),
        files=len(files),
        datasets=tuple(datasets),
        size_bytes=sum(f.stat().st_size for f in files),
    )


def read_lineage(files: list[Path]) -> pd.DataFrame:
    """Concatena ``_run_id`` e ``_ingested_at`` dos arquivos Parquet informados."""
    frames = [pd.read_parquet(f, columns=_LINEAGE_COLUMNS) for f in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(
            {
                RUN_ID: pd.Series(dtype="string"),
                INGESTED_AT: pd.Series(dtype="datetime64[ns, UTC]"),
            }
        )
    return pd.concat(frames, ignore_index=True)


def latest_run(lineage: pd.DataFrame) -> RunInfo | None:
    """Execução mais recente pela coluna ``_ingested_at``."""
    valid = lineage.dropna(subset=[INGESTED_AT, RUN_ID])
    if valid.empty:
        return None
    position = int(valid[INGESTED_AT].to_numpy().argmax())
    timestamp = pd.Timestamp(valid[INGESTED_AT].iloc[position])
    return RunInfo(
        run_id=str(valid[RUN_ID].iloc[position]),
        ingested_at=timestamp.to_pydatetime(),
    )


def load_dataset_summary(data_dir: Path, dataset: str) -> DatasetSummary:
    """Registros processados (silver) e rejeitados (quarentena) de um dataset."""
    silver = list(iter_data_files(layer_path(data_dir, SILVER) / dataset, "*.parquet"))
    rejected = list(
        iter_data_files(layer_path(data_dir, QUARANTINE) / dataset, "*.parquet")
    )
    lineage = read_lineage(silver)
    return DatasetSummary(
        dataset=dataset,
        partitions=len(silver),
        records=len(lineage),
        rejected=len(read_lineage(rejected)),
        last_run=latest_run(pd.concat([lineage, read_lineage(rejected)])),
    )


def load_platform_summary(data_dir: Path) -> PlatformSummary:
    """Resumo completo do data lake: camadas, datasets e última execução."""
    datasets = tuple(
        load_dataset_summary(data_dir, spec.dataset) for spec in DATASET_SPECS.values()
    )
    runs = [d.last_run for d in datasets if d.last_run is not None]
    return PlatformSummary(
        data_dir=data_dir,
        layers=tuple(load_layer_status(data_dir, layer) for layer in LAYERS),
        datasets=datasets,
        last_run=max(runs, key=lambda run: run.ingested_at, default=None),
    )


def datasets_table(summary: PlatformSummary) -> pd.DataFrame:
    """Uma linha por dataset silver, pronta para exibição tabular."""
    return pd.DataFrame(
        [
            {
                "dataset": d.dataset,
                "partições": d.partitions,
                "registros": d.records,
                "rejeitados": d.rejected,
                "último run_id": d.last_run.run_id if d.last_run else None,
                "última execução": d.last_run.ingested_at if d.last_run else None,
            }
            for d in summary.datasets
        ]
    )


def layers_table(summary: PlatformSummary) -> pd.DataFrame:
    """Uma linha por camada do data lake."""
    return pd.DataFrame(
        [
            {
                "camada": item.layer,
                "disponível": item.exists,
                "arquivos": item.files,
                "datasets": len(item.datasets),
                "tamanho (KB)": round(item.size_bytes / 1024, 1),
                "caminho": str(item.path),
            }
            for item in summary.layers
        ]
    )
