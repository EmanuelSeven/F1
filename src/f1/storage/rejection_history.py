"""Histórico de rejeições: contagem por carga e regra, só com acréscimos.

Ao contrário da quarentena (retrato da última carga), cada carga grava um
arquivo novo em ``{base}/{dataset}/season=Y[/meeting_key=N]/run_id={id}.parquet``.
Nada é sobrescrito por outra carga, então dá para ver a evolução entre cargas.
Regravar o mesmo ``run_id`` na mesma partição substitui só o arquivo dele.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from f1.domain.models import REJECT_REASON, Partition
from f1.storage.atomic import path_lock, replace_file, temp_sibling
from f1.storage.paths import partition_path

REASON_SEPARATOR = "; "  # ``validate`` junta as regras violadas por uma linha

RUN_ID = "run_id"
RECORDED_AT = "recorded_at"
DATASET = "dataset"
SEASON = "season"
MEETING_KEY = "meeting_key"
RULE = "rule"
REJECTED = "rejected"
RECORDS_READ = "records_read"
ABORTED = "aborted"
# Linhas rejeitadas na carga (cada linha conta uma vez, mesmo violando várias
# regras). Ausente nos arquivos gravados antes desta coluna existir.
ROWS_REJECTED = "rows_rejected"

COLUMNS: dict[str, str] = {
    RUN_ID: "string",
    RECORDED_AT: "datetime64[ns, UTC]",
    DATASET: "string",
    SEASON: "Int64",
    MEETING_KEY: "Int64",
    RULE: "string",
    REJECTED: "Int64",
    RECORDS_READ: "Int64",
    ABORTED: "boolean",
    ROWS_REJECTED: "Int64",
}


def empty_history() -> pd.DataFrame:
    """Histórico vazio com as colunas tipadas."""
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in COLUMNS.items()})


def count_by_rule(rejected: pd.DataFrame) -> pd.Series:
    """Linhas rejeitadas por regra (``coluna:check``).

    Uma linha que viola duas regras conta uma vez em cada uma delas.
    """
    if rejected.empty:
        return pd.Series(dtype="Int64")
    rules = rejected[REJECT_REASON].dropna().str.split(REASON_SEPARATOR).explode()
    return rules.value_counts().sort_index().astype("Int64")


def rejection_rows(  # noqa: PLR0913 - uma linha do histórico tem estes campos
    *,
    run_id: str,
    recorded_at: datetime,
    dataset: str,
    partition: Partition,
    rejected: pd.DataFrame,
    records_read: int,
    aborted: bool,
) -> pd.DataFrame:
    """Uma linha por regra violada na carga.

    Sem rejeições, grava uma linha com ``rule`` nulo e ``rejected=0``: assim o
    histórico diferencia "a carga rodou e não rejeitou nada" de "não rodou".
    """
    counts = count_by_rule(rejected)
    rules: list[str | None] = list(counts.index) if not counts.empty else [None]
    values: list[int] = [int(v) for v in counts] if not counts.empty else [0]
    size = len(rules)
    frame = pd.DataFrame(
        {
            RUN_ID: [run_id] * size,
            RECORDED_AT: [recorded_at] * size,
            DATASET: [dataset] * size,
            SEASON: [partition.season] * size,
            MEETING_KEY: [partition.meeting_key] * size,
            RULE: rules,
            REJECTED: values,
            RECORDS_READ: [records_read] * size,
            ABORTED: [aborted] * size,
            ROWS_REJECTED: [len(rejected)] * size,
        }
    )
    return frame.astype(COLUMNS)


class RejectionHistoryStore:
    """Acrescenta ao histórico um arquivo por carga e partição."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def path_for(self, dataset: str, partition: Partition, run_id: str) -> Path:
        directory = partition_path(self._base, dataset, partition)
        return directory / f"run_id={run_id}.parquet"

    def append(self, dataset: str, partition: Partition, frame: pd.DataFrame) -> Path:
        """Grava o arquivo da carga de forma atômica (temporário + renomeação)."""
        run_ids = frame[RUN_ID].dropna().unique()
        if len(run_ids) != 1:
            raise ValueError("rejection history frame needs exactly one run_id")
        target = self.path_for(dataset, partition, str(run_ids[0]))
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = temp_sibling(target, ".tmp")
        frame.to_parquet(staging, index=False, compression="zstd")
        with path_lock(target):
            replace_file(staging, target)
        return target
