"""Pipeline de calendário: ``meetings`` e ``sessions`` de uma temporada."""

import logging
from dataclasses import dataclass

from f1.domain.endpoints import Endpoint
from f1.domain.models import Filter, MeetingRef, Partition, Record, SessionRef
from f1.domain.ports import OpenF1Source
from f1.pipelines.common import LakeStores, RunContext, load_dataset

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Calendar:
    """Meetings e sessões não cancelados de uma temporada."""

    year: int
    meetings: tuple[MeetingRef, ...]
    sessions: tuple[SessionRef, ...]


def load_calendar(
    source: OpenF1Source, stores: LakeStores, ctx: RunContext, year: int
) -> Calendar:
    """Carrega meetings e sessions do ano (bronze → silver → quarentena).

    Meetings e sessões cancelados permanecem no silver (coluna ``is_cancelled``),
    mas ficam fora do ``Calendar`` retornado.
    """
    partition = Partition(season=year)
    loaded: dict[Endpoint, list[Record]] = {}
    for endpoint in (Endpoint.MEETINGS, Endpoint.SESSIONS):
        records = source.fetch(endpoint, [Filter("year", year)])
        stores.raw.write(endpoint, partition, "raw", records)
        load_dataset(endpoint, records, partition, stores, ctx)
        loaded[endpoint] = records
    meetings = [MeetingRef.from_record(r) for r in loaded[Endpoint.MEETINGS]]
    sessions = [SessionRef.from_record(r) for r in loaded[Endpoint.SESSIONS]]
    calendar = Calendar(
        year=year,
        meetings=tuple(m for m in meetings if not m.is_cancelled),
        sessions=tuple(s for s in sessions if not s.is_cancelled),
    )
    logger.info(
        "calendar_loaded",
        extra={
            "season": year,
            "meetings": len(meetings),
            "active": len(calendar.meetings),
            "sessions": len(calendar.sessions),
        },
    )
    return calendar


def run_calendar(
    source: OpenF1Source, stores: LakeStores, ctx: RunContext, year: int
) -> list[MeetingRef]:
    """Carrega o calendário e retorna os meetings não cancelados."""
    return list(load_calendar(source, stores, ctx, year).meetings)
