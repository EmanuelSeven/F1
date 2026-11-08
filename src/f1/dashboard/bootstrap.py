"""Cargas sob demanda do dashboard (sem visualização).

- Temporada: calendário + ``drivers``/``session_results`` das corridas e sprints
  já encerradas do ano (poucas requisições; ver ``f1.pipelines.results``).
- Detalhes: ``laps``, ``stints``, ``pit_stops`` e ``weather`` apenas da corrida
  principal de um meeting.

Todas as funções propagam ``OpenF1AccessError``/``OpenF1Error``; quem chama
decide como exibir a falha.
"""

import logging
from collections.abc import Callable, Collection, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime

from f1.config.settings import Settings
from f1.dashboard.loaders import DETAIL_ENDPOINTS
from f1.domain.endpoints import Endpoint
from f1.domain.models import POINTS_KINDS, MeetingRef, SessionKind, SessionRef
from f1.domain.ports import OpenF1Source
from f1.ingestion.openf1_client import OpenF1Client
from f1.pipelines.calendar import load_calendar
from f1.pipelines.common import RunContext
from f1.pipelines.factory import build_stores
from f1.pipelines.meeting import run_meeting
from f1.pipelines.results import run_meeting_grid, run_results
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
    kinds: tuple[SessionKind, ...] = POINTS_KINDS,
) -> BootstrapResult:
    """Calendário + resultados das sessões encerradas dos tipos ``kinds``.

    Considera só fins de semana de GP (meetings com corrida). A partição de
    resultados de cada meeting passa a conter exatamente esses tipos; para
    acrescentar tipos, passe a união com os já carregados. O cliente respeita
    ``F1_REQUEST_INTERVAL_SECONDS`` entre requisições e faz backoff em
    ``429``/``5xx``.
    """
    reference = now or datetime.now(UTC)
    ctx = _context(settings, "dashboard_season_bootstrap_started", season=year)
    stores = build_stores(settings)
    with _factory(source_factory)(settings) as source:
        calendar = load_calendar(source, stores, ctx, year)
        gp_weekends = {s.meeting_key for s in calendar.sessions if s.is_race}
        sessions = [
            s
            for s in calendar.sessions
            if s.kind in kinds
            and s.meeting_key in gp_weekends
            and s.is_finished(reference)
        ]
        metrics = run_results(source, stores, ctx, year, sessions)
    return BootstrapResult(
        run_id=ctx.run_id,
        year=year,
        meetings=len(calendar.meetings),
        sessions=len(sessions),
        records=sum(m.records_processed for m in metrics),
    )


def run_race_details(
    settings: Settings,
    meeting: MeetingRef,
    source_factory: SourceFactory | None = None,
    keep_sessions: Collection[int] = (),
) -> BootstrapResult:
    """Voltas, stints, pit stops e clima da corrida principal de ``meeting``.

    As partições são regravadas por meeting; ``keep_sessions`` são sessões que
    já estão no lake (ex.: voltas da classificação) e devem continuar lá.
    """
    keep = {int(k) for k in keep_sessions}
    return _load_meeting_sessions(
        settings,
        meeting,
        DETAIL_ENDPOINTS,
        lambda s: s.is_race or s.session_key in keep,
        source_factory,
    )


def run_meeting_laps(
    settings: Settings,
    meeting: MeetingRef,
    session_keys: Collection[int],
    source_factory: SourceFactory | None = None,
) -> BootstrapResult:
    """Voltas das sessões ``session_keys`` de ``meeting``.

    A partição ``laps`` do meeting passa a ter exatamente essas sessões; para
    acrescentar sessões, passe a união com as que já estão no lake.
    """
    keys = {int(k) for k in session_keys}
    return _load_meeting_sessions(
        settings,
        meeting,
        (Endpoint.LAPS,),
        lambda s: s.session_key in keys,
        source_factory,
    )


def _load_meeting_sessions(
    settings: Settings,
    meeting: MeetingRef,
    endpoints: Sequence[Endpoint],
    session_filter: Callable[[SessionRef], bool],
    source_factory: SourceFactory | None,
) -> BootstrapResult:
    ctx = _context(
        settings,
        "dashboard_meeting_load_started",
        meeting_key=meeting.meeting_key,
        endpoints=[e.value for e in endpoints],
    )
    with _factory(source_factory)(settings) as source:
        metrics = run_meeting(
            source,
            build_stores(settings),
            ctx,
            meeting,
            endpoints,
            session_filter=session_filter,
        )
    return BootstrapResult(
        run_id=ctx.run_id,
        year=meeting.year,
        meetings=1,
        sessions=len(endpoints),
        records=sum(m.records_processed for m in metrics),
    )


def run_grid(
    settings: Settings,
    year: int,
    meeting_key: int,
    source_factory: SourceFactory | None = None,
) -> BootstrapResult:
    """Grade de largada de um meeting (uma requisição)."""
    ctx = _context(settings, "dashboard_grid_started", meeting_key=meeting_key)
    with _factory(source_factory)(settings) as source:
        metrics = run_meeting_grid(
            source, build_stores(settings), ctx, year, meeting_key
        )
    return BootstrapResult(
        run_id=ctx.run_id,
        year=year,
        meetings=1,
        sessions=0,
        records=metrics.records_processed,
    )
