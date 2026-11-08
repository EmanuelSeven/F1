"""Pipeline de calendário: ``meetings`` e ``sessions`` de uma temporada."""

import logging

from f1.domain.endpoints import Endpoint
from f1.domain.models import Filter, MeetingRef, Partition
from f1.domain.ports import OpenF1Source
from f1.pipelines.common import LakeStores, RunContext, load_dataset

logger = logging.getLogger(__name__)


def run_calendar(
    source: OpenF1Source, stores: LakeStores, ctx: RunContext, year: int
) -> list[MeetingRef]:
    """Carrega meetings e sessions do ano e retorna os meetings não cancelados.

    Meetings e sessões cancelados permanecem no silver (coluna ``is_cancelled``),
    mas não são processados pelas pipelines de sessão.
    """
    partition = Partition(season=year)
    meetings: list[MeetingRef] = []
    for endpoint in (Endpoint.MEETINGS, Endpoint.SESSIONS):
        records = source.fetch(endpoint, [Filter("year", year)])
        stores.raw.write(endpoint, partition, "raw", records)
        load_dataset(endpoint, records, partition, stores, ctx)
        if endpoint is Endpoint.MEETINGS:
            meetings = [MeetingRef.from_record(r) for r in records]
    active = [m for m in meetings if not m.is_cancelled]
    logger.info(
        "calendar_loaded",
        extra={"season": year, "meetings": len(meetings), "active": len(active)},
    )
    return active
