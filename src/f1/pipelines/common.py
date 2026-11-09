"""Etapa comum: registros brutos → normalização → validação → silver/quarentena."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from f1.domain.endpoints import Endpoint, spec_for
from f1.domain.models import Partition, Record
from f1.domain.ports import AppendStore, DatasetStore, RawStore
from f1.processing.lineage import add_lineage_columns
from f1.processing.normalize import normalize
from f1.quality.schemas import schema_for
from f1.quality.validation import DataQualityError, ValidationResult, validate
from f1.storage.rejection_history import rejection_rows
from f1.utils.metrics import PipelineMetrics, track_pipeline


@dataclass(frozen=True)
class LakeStores:
    raw: RawStore
    silver: DatasetStore[pd.DataFrame]
    quarantine: DatasetStore[pd.DataFrame]
    rejections: AppendStore[pd.DataFrame]


@dataclass(frozen=True)
class RunContext:
    run_id: str
    max_rejection_rate: float = 0.05


def load_dataset(
    endpoint: Endpoint,
    records: Sequence[Record],
    partition: Partition,
    stores: LakeStores,
    ctx: RunContext,
) -> PipelineMetrics:
    """Normaliza, valida e sobrescreve a partição silver (e a de quarentena).

    Também acrescenta a contagem de rejeições ao histórico, inclusive quando a
    carga é abortada por excesso de rejeições.
    """
    dataset = spec_for(endpoint).dataset
    with track_pipeline(
        f"silver.{dataset}", destination=f"{dataset}/{partition}", run_id=ctx.run_id
    ) as metrics:
        metrics.records_read = len(records)
        frame = normalize(endpoint, records)
        try:
            result = validate(frame, schema_for(endpoint), ctx.max_rejection_rate)
        except DataQualityError as exc:
            metrics.records_rejected = len(exc.result.rejected)
            _write_quarantine(endpoint, exc.result, partition, stores, ctx)
            _record_rejections(
                dataset, exc.result, partition, stores, ctx, aborted=True
            )
            raise
        metrics.records_processed = len(result.valid)
        metrics.records_rejected = len(result.rejected)
        stores.silver.write_partition(
            dataset, partition, _with_lineage(result.valid, endpoint, ctx)
        )
        _write_quarantine(endpoint, result, partition, stores, ctx)
        _record_rejections(dataset, result, partition, stores, ctx, aborted=False)
    return metrics


def _with_lineage(
    df: pd.DataFrame, endpoint: Endpoint, ctx: RunContext
) -> pd.DataFrame:
    return add_lineage_columns(df.reset_index(drop=True), ctx.run_id, endpoint.value)


def _write_quarantine(
    endpoint: Endpoint,
    result: ValidationResult,
    partition: Partition,
    stores: LakeStores,
    ctx: RunContext,
) -> None:
    stores.quarantine.write_partition(
        spec_for(endpoint).dataset,
        partition,
        _with_lineage(result.rejected, endpoint, ctx),
    )


def _record_rejections(  # noqa: PLR0913
    dataset: str,
    result: ValidationResult,
    partition: Partition,
    stores: LakeStores,
    ctx: RunContext,
    *,
    aborted: bool,
) -> None:
    rows = rejection_rows(
        run_id=ctx.run_id,
        recorded_at=datetime.now(UTC),
        dataset=dataset,
        partition=partition,
        rejected=result.rejected,
        records_read=result.total,
        aborted=aborted,
    )
    stores.rejections.append(dataset, partition, rows)
