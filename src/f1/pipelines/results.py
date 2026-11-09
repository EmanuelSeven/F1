"""Pipeline de resultados: ``drivers`` e ``session_results`` de várias sessões.

Busca os dados de muitas sessões com poucas requisições (filtro ``session_key``
com múltiplos valores) e grava no padrão do meeting: bronze com um arquivo por
sessão, silver/quarentena com uma partição por meeting.
"""

import logging
from collections import defaultdict
from collections.abc import Sequence

from f1.domain.endpoints import Endpoint
from f1.domain.models import Filter, Partition, Record, SessionRef, as_int
from f1.domain.ports import OpenF1Source
from f1.pipelines.common import LakeStores, RunContext, load_dataset
from f1.utils.metrics import PipelineMetrics

logger = logging.getLogger(__name__)

RESULT_ENDPOINTS: tuple[Endpoint, ...] = (Endpoint.DRIVERS, Endpoint.SESSION_RESULT)
DEFAULT_CHUNK_SIZE = 25


def run_results(  # noqa: PLR0913 - dependências injetadas explicitamente
    source: OpenF1Source,
    stores: LakeStores,
    ctx: RunContext,
    year: int,
    sessions: Sequence[SessionRef],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[PipelineMetrics]:
    """Carrega drivers e session_results das ``sessions`` (overwrite por meeting).

    A partição de cada meeting passa a conter apenas as sessões informadas.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    by_meeting: dict[int, list[SessionRef]] = defaultdict(list)
    for session in sessions:
        by_meeting[session.meeting_key].append(session)

    metrics: list[PipelineMetrics] = []
    for endpoint in RESULT_ENDPOINTS:
        by_session = _fetch_by_session(source, endpoint, sessions, chunk_size)
        for meeting_key, meeting_sessions in sorted(by_meeting.items()):
            partition = Partition(season=year, meeting_key=meeting_key)
            records: list[Record] = []
            for session in meeting_sessions:
                batch = by_session.get(session.session_key, [])
                name = f"session_key={session.session_key}"
                stores.raw.write(endpoint, partition, name, batch)
                records.extend(batch)
            metrics.append(load_dataset(endpoint, records, partition, stores, ctx))
    logger.info(
        "results_loaded",
        extra={
            "run_id": ctx.run_id,
            "season": year,
            "sessions": len(sessions),
            "meetings": len(by_meeting),
        },
    )
    return metrics


def run_meeting_grid(
    source: OpenF1Source,
    stores: LakeStores,
    ctx: RunContext,
    year: int,
    meeting_key: int,
) -> PipelineMetrics:
    """Grade de largada de um meeting (uma requisição; overwrite da partição).

    A OpenF1 associa a grade à sessão de classificação que a definiu (a da
    corrida e, em fins de semana com sprint, também a da sprint).
    """
    partition = Partition(season=year, meeting_key=meeting_key)
    records = source.fetch(Endpoint.STARTING_GRID, [Filter("meeting_key", meeting_key)])
    stores.raw.write(Endpoint.STARTING_GRID, partition, "meeting", records)
    return load_dataset(Endpoint.STARTING_GRID, records, partition, stores, ctx)


def _fetch_by_session(
    source: OpenF1Source,
    endpoint: Endpoint,
    sessions: Sequence[SessionRef],
    chunk_size: int,
) -> dict[int, list[Record]]:
    keys = [s.session_key for s in sessions]
    grouped: dict[int, list[Record]] = defaultdict(list)
    for start in range(0, len(keys), chunk_size):
        chunk = tuple(keys[start : start + chunk_size])
        for record in source.fetch(endpoint, [Filter("session_key", chunk)]):
            grouped[as_int(record, "session_key")].append(record)
    return grouped
