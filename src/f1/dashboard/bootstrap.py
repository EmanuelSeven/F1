"""Cargas sob demanda do dashboard (sem visualização).

- Temporada: calendário + ``drivers``/``session_results`` das corridas e sprints
  já encerradas do ano (poucas requisições; ver ``f1.pipelines.results``).
- Detalhes: ``laps``, ``stints``, ``pit_stops`` e ``weather`` apenas da corrida
  principal de um meeting.

Todas as funções propagam ``OpenF1AccessError``/``OpenF1Error``; quem chama
decide como exibir a falha.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime

from f1.config.settings import Settings
from f1.dashboard.loaders import DETAIL_ENDPOINTS
from f1.domain.models import MeetingRef, SessionRef
from f1.domain.ports import OpenF1Source
from f1.ingestion.openf1_client import OpenF1Client
from f1.pipelines.calendar import load_calendar
from f1.pipelines.common import RunContext
from f1.pipelines.factory import build_stores
from f1.pipelines.meeting import run_meeting
from f1.pipelines.results import run_results
from f1.utils.metrics import new_run_id

logger = logging.getLogger(__name__)

BOOTSTRAP_YEAR = 2024
FIRST_SEASON = 2023  # dados históricos gratuitos da OpenF1 começam em 2023

type SourceFactory = Callable[[Settings], AbstractContextManager[OpenF1Source]]


@dataclass(frozen=True)
class BootstrapResult:
    run_id: str
    year: int
    meetings: int
    sessions: int
    records: int


def _context(settings: Settings, event: str, **extra: object) -> RunContext:
    ctx = RunContext(
        run_id=new_run_id(), max_rejection_rate=settings.max_rejection_rate
    )
    logger.info(event, extra={"run_id": ctx.run_id, **extra})
    return ctx


def _factory(source_factory: SourceFactory | None) -> SourceFactory:
    return source_factory or OpenF1Client.from_settings


def run_season_bootstrap(
    settings: Settings,
    year: int = BOOTSTRAP_YEAR,
    source_factory: SourceFactory | None = None,
    now: datetime | None = None,
) -> BootstrapResult:
    """Calendário + resultados das corridas e sprints encerradas de ``year``.

    O cliente respeita ``F1_REQUEST_INTERVAL_SECONDS`` entre requisições e faz
    backoff em ``429``/``5xx``.
    """
    reference = now or datetime.now(UTC)
    ctx = _context(settings, "dashboard_season_bootstrap_started", season=year)
    stores = build_stores(settings)
    with _factory(source_factory)(settings) as source:
        calendar = load_calendar(source, stores, ctx, year)
        sessions = [
            s for s in calendar.sessions if s.awards_points and s.is_finished(reference)
        ]
        metrics = run_results(source, stores, ctx, year, sessions)
    return BootstrapResult(
        run_id=ctx.run_id,
        year=year,
        meetings=len(calendar.meetings),
        sessions=len(sessions),
        records=sum(m.records_processed for m in metrics),
    )


def _is_main_race(session: SessionRef) -> bool:
    return session.is_race


def run_race_details(
    settings: Settings,
    meeting: MeetingRef,
    source_factory: SourceFactory | None = None,
) -> BootstrapResult:
    """Voltas, stints, pit stops e clima da corrida principal de ``meeting``."""
    ctx = _context(
        settings,
        "dashboard_race_details_started",
        meeting_key=meeting.meeting_key,
    )
    with _factory(source_factory)(settings) as source:
        metrics = run_meeting(
            source,
            build_stores(settings),
            ctx,
            meeting,
            DETAIL_ENDPOINTS,
            session_filter=_is_main_race,
        )
    return BootstrapResult(
        run_id=ctx.run_id,
        year=meeting.year,
        meetings=1,
        sessions=1,
        records=sum(m.records_processed for m in metrics),
    )
