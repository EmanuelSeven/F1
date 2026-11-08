"""Métricas padronizadas de execução de pipelines."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from uuid import uuid4

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    """Gera um identificador único de execução."""
    return uuid4().hex


@dataclass
class PipelineMetrics:
    pipeline: str
    destination: str
    run_id: str = field(default_factory=new_run_id)
    records_read: int = 0
    records_processed: int = 0
    records_rejected: int = 0


@contextmanager
def track_pipeline(
    pipeline: str, destination: str, run_id: str | None = None
) -> Iterator[PipelineMetrics]:
    """Registra início, término, duração e falhas de uma etapa de pipeline."""
    metrics = PipelineMetrics(pipeline=pipeline, destination=destination)
    if run_id is not None:
        metrics.run_id = run_id
    started = time.perf_counter()
    logger.info("pipeline_started", extra=asdict(metrics))
    try:
        yield metrics
    except Exception:
        duration = round(time.perf_counter() - started, 3)
        logger.exception(
            "pipeline_failed", extra={**asdict(metrics), "duration_seconds": duration}
        )
        raise
    duration = round(time.perf_counter() - started, 3)
    logger.info(
        "pipeline_finished", extra={**asdict(metrics), "duration_seconds": duration}
    )
