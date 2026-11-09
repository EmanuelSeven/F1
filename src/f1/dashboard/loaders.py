"""Leitura e agregação do data lake para o dashboard (sem visualização).

O resumo do lake lê apenas metadados e colunas de linhagem; as leituras da
temporada e da corrida carregam os datasets silver de uma partição.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from f1.domain.endpoints import DATASET_SPECS, Endpoint, spec_for
from f1.domain.models import INGESTED_AT, RUN_ID, Partition
from f1.processing.normalize import normalize
from f1.storage import rejection_history as history
from f1.storage.parquet_writer import PART_FILE
from f1.storage.paths import (
    BRONZE,
    QUARANTINE,
    REJECTION_HISTORY,
    SILVER,
    layer_path,
    partition_path,
)

LAYERS: tuple[str, ...] = (BRONZE, SILVER, QUARANTINE)
SEASON_ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint.MEETINGS,
    Endpoint.SESSIONS,
    Endpoint.DRIVERS,
    Endpoint.SESSION_RESULT,
)
DETAIL_ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint.LAPS,
    Endpoint.STINTS,
    Endpoint.PIT,
    Endpoint.WEATHER,
)
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


def is_lake_empty(data_dir: Path) -> bool:
    """``True`` se nenhuma camada tiver arquivos de dados."""
    return not any(
        next(iter_data_files(layer_path(data_dir, layer), pattern), None)
        for layer, pattern in _LAYER_PATTERNS.items()
    )


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


def load_rejection_history(data_dir: Path) -> pd.DataFrame:
    """Todas as linhas do histórico de rejeições (vazio, com colunas tipadas)."""
    base = layer_path(data_dir, REJECTION_HISTORY)
    frames = [pd.read_parquet(f) for f in iter_data_files(base, "*.parquet")]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return history.empty_history()
    return pd.concat(frames, ignore_index=True).astype(history.COLUMNS)


TREND_COLUMNS = [
    history.RUN_ID,
    history.RECORDED_AT,
    history.RULE,
    history.REJECTED,
    history.RECORDS_READ,
    "rate",
    history.ABORTED,
]


def rejection_trend(
    rows: pd.DataFrame, dataset: str, meeting_key: int | None = None
) -> pd.DataFrame:
    """Taxa de rejeição por carga e regra de um dataset, em ordem cronológica.

    Cada carga soma as partições que gravou (ou só ``meeting_key``, se dado).
    Uma regra sem linhas numa carga que rodou conta como zero rejeições nela.
    """
    rows = rows[rows[history.DATASET] == dataset]
    if meeting_key is not None:
        rows = rows[rows[history.MEETING_KEY] == meeting_key]
    if rows.empty:
        return pd.DataFrame(columns=TREND_COLUMNS)
    partition = [history.RUN_ID, history.SEASON, history.MEETING_KEY]
    runs = (
        rows.drop_duplicates(partition)
        .groupby(history.RUN_ID, as_index=False)
        .agg(
            recorded_at=(history.RECORDED_AT, "min"),
            records_read=(history.RECORDS_READ, "sum"),
            aborted=(history.ABORTED, "any"),
        )
    )
    violated = rows.dropna(subset=[history.RULE])
    rules = sorted(violated[history.RULE].unique())
    if not rules:
        return pd.DataFrame(columns=TREND_COLUMNS)
    counts = violated.groupby([history.RUN_ID, history.RULE], as_index=False)[
        history.REJECTED
    ].sum()
    grid = runs.merge(pd.DataFrame({history.RULE: rules}), how="cross")
    trend = grid.merge(counts, on=[history.RUN_ID, history.RULE], how="left")
    trend[history.REJECTED] = trend[history.REJECTED].fillna(0).astype(int)
    read = trend[history.RECORDS_READ].astype(float)
    trend["rate"] = (trend[history.REJECTED] / read.where(read > 0)).fillna(0.0)
    return trend.sort_values([history.RECORDED_AT, history.RULE], ignore_index=True)[
        TREND_COLUMNS
    ]


@dataclass(frozen=True)
class SeasonData:
    year: int
    meetings: pd.DataFrame
    sessions: pd.DataFrame
    drivers: pd.DataFrame
    results: pd.DataFrame


@dataclass(frozen=True)
class RaceDetails:
    laps: pd.DataFrame
    stints: pd.DataFrame
    pit_stops: pd.DataFrame
    weather: pd.DataFrame


def _silver_partition(data_dir: Path, endpoint: Endpoint, partition: Partition) -> Path:
    base = layer_path(data_dir, SILVER)
    return partition_path(base, spec_for(endpoint).dataset, partition)


def read_dataset(
    data_dir: Path, endpoint: Endpoint, season: int, meeting_key: int | None = None
) -> pd.DataFrame:
    """Lê as partições silver de um dataset (temporada inteira ou um meeting).

    Sem dados, retorna um DataFrame vazio com as colunas tipadas do dataset.
    Partições gravadas antes de uma coluna nova existir recebem a coluna nula.
    """
    root = _silver_partition(data_dir, endpoint, Partition(season, meeting_key))
    frames = [pd.read_parquet(f) for f in iter_data_files(root, "*.parquet")]
    frames = [f for f in frames if not f.empty]
    template = normalize(endpoint, [])
    if not frames:
        return template
    df = pd.concat(frames, ignore_index=True)
    for column in template.columns:
        if column not in df.columns:
            df[column] = pd.Series(pd.NA, index=df.index, dtype=template[column].dtype)
    return df


def season_is_loaded(data_dir: Path, year: int) -> bool:
    """Calendário e ao menos um resultado da temporada já estão no silver."""
    meetings = _silver_partition(data_dir, Endpoint.MEETINGS, Partition(year))
    results = _silver_partition(data_dir, Endpoint.SESSION_RESULT, Partition(year))
    has_results = next(iter_data_files(results, "*.parquet"), None) is not None
    return (meetings / PART_FILE).is_file() and has_results


def load_season_data(data_dir: Path, year: int) -> SeasonData:
    """Datasets silver usados pela página da temporada."""
    frames = {e: read_dataset(data_dir, e, year) for e in SEASON_ENDPOINTS}
    return SeasonData(
        year=year,
        meetings=frames[Endpoint.MEETINGS],
        sessions=frames[Endpoint.SESSIONS],
        drivers=frames[Endpoint.DRIVERS],
        results=frames[Endpoint.SESSION_RESULT],
    )


def race_details_loaded(data_dir: Path, year: int, meeting_key: int) -> bool:
    """Voltas, stints, pit stops e clima do meeting já estão no silver."""
    partition = Partition(year, meeting_key)
    return all(
        (_silver_partition(data_dir, e, partition) / PART_FILE).is_file()
        for e in DETAIL_ENDPOINTS
    )


def load_race_details(data_dir: Path, year: int, meeting_key: int) -> RaceDetails:
    """Datasets de detalhe de um meeting (todas as sessões gravadas)."""
    frames = {e: read_dataset(data_dir, e, year, meeting_key) for e in DETAIL_ENDPOINTS}
    return RaceDetails(
        laps=frames[Endpoint.LAPS],
        stints=frames[Endpoint.STINTS],
        pit_stops=frames[Endpoint.PIT],
        weather=frames[Endpoint.WEATHER],
    )


def lap_session_keys(data_dir: Path, year: int, meeting_key: int) -> set[int]:
    """Sessões do meeting que já têm voltas no silver."""
    laps = read_dataset(data_dir, Endpoint.LAPS, year, meeting_key)
    return {int(k) for k in laps["session_key"].dropna().unique()}
