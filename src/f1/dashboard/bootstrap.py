"""Carga inicial do data lake para o dashboard (sem visualização).

Quando o lake está vazio, o dashboard executa a pipeline de calendário de
``BOOTSTRAP_YEAR`` para ter algo a exibir.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

from f1.config.settings import Settings
from f1.domain.ports import OpenF1Source
from f1.ingestion.openf1_client import OpenF1Client
from f1.pipelines.calendar import run_calendar
from f1.pipelines.common import RunContext
from f1.pipelines.factory import build_stores
from f1.utils.metrics import new_run_id

logger = logging.getLogger(__name__)

BOOTSTRAP_YEAR = 2024

type SourceFactory = Callable[[Settings], AbstractContextManager[OpenF1Source]]


@dataclass(frozen=True)
class BootstrapResult:
    run_id: str
    year: int
    meetings: int


def run_initial_calendar(
    settings: Settings,
    year: int = BOOTSTRAP_YEAR,
    source_factory: SourceFactory | None = None,
) -> BootstrapResult:
    """Executa ``run_calendar`` para ``year`` e grava em ``settings.data_dir``.

    Raises:
        OpenF1AccessError: a API negou o acesso (ex.: sessão ao vivo).
        OpenF1Error: outras falhas de comunicação com a API.

    ``source_factory`` padrão: ``OpenF1Client.from_settings`` (resolvido na chamada).
    """
    factory = source_factory or OpenF1Client.from_settings
    ctx = RunContext(
        run_id=new_run_id(), max_rejection_rate=settings.max_rejection_rate
    )
    logger.info(
        "dashboard_bootstrap_started", extra={"run_id": ctx.run_id, "season": year}
    )
    with factory(settings) as source:
        meetings = run_calendar(source, build_stores(settings), ctx, year)
    return BootstrapResult(run_id=ctx.run_id, year=year, meetings=len(meetings))
