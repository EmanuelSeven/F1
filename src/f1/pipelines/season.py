"""Pipeline de temporada: calendário + todos os meetings já encerrados."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from f1.domain.endpoints import SESSION_ENDPOINTS, Endpoint
from f1.domain.ports import OpenF1Source
from f1.pipelines.calendar import run_calendar
from f1.pipelines.common import LakeStores, RunContext
from f1.pipelines.meeting import run_meeting
from f1.utils.metrics import PipelineMetrics

logger = logging.getLogger(__name__)


def run_season(  # noqa: PLR0913 - dependências injetadas explicitamente
    source: OpenF1Source,
    stores: LakeStores,
    ctx: RunContext,
    year: int,
    *,
    endpoints: Sequence[Endpoint] = SESSION_ENDPOINTS,
    now: datetime | None = None,
) -> list[PipelineMetrics]:
    """Executa o calendário do ano e, em sequência, cada meeting encerrado."""
    reference = now or datetime.now(UTC)
    meetings = run_calendar(source, stores, ctx, year)
    finished = [m for m in meetings if m.is_finished(reference)]
    logger.info(
        "season_started",
        extra={"run_id": ctx.run_id, "season": year, "meetings": len(finished)},
    )
    metrics: list[PipelineMetrics] = []
    for meeting in finished:
        metrics.extend(run_meeting(source, stores, ctx, meeting, endpoints))
    return metrics
