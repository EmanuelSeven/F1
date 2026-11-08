"""Dados do dashboard: leituras em cache e cargas sob demanda da OpenF1.

Compartilhado pela barra lateral (que dispara a carga da temporada escolhida)
e pelas páginas. Cargas usam ``st.cache_resource`` (uma vez por processo;
falhas não ficam em cache) e leituras do lake usam ``st.cache_data``.
"""

from collections.abc import Callable, Iterable
from pathlib import Path

import streamlit as st

from f1.config.settings import get_settings
from f1.dashboard.bootstrap import (
    BootstrapResult,
    run_race_details,
    run_season_bootstrap,
)
from f1.dashboard.loaders import (
    PlatformSummary,
    RaceDetails,
    SeasonData,
    load_platform_summary,
    load_race_details,
    load_season_data,
    season_is_loaded,
)
from f1.domain.models import MeetingRef, SessionKind
from f1.ingestion.openf1_client import OpenF1AccessError, OpenF1Error
from f1.processing.standings import result_kinds
from f1.quality.validation import DataQualityError

CACHE_TTL_SECONDS = 300
SUMMARY_TTL_SECONDS = 60
ACCESS_DENIED_MESSAGE = (
    "A OpenF1 está temporariamente indisponível para acesso gratuito "
    "(normalmente porque há uma sessão de F1 ao vivo). Os dados já baixados "
    "continuam disponíveis; tente de novo quando a sessão terminar — basta "
    "recarregar a página."
)
QUALITY_ERROR_MESSAGE = (
    "Os dados recebidos da OpenF1 não passaram na validação de qualidade e não "
    "foram publicados (os registros rejeitados estão na quarentena do data lake)."
)
API_ERROR_MESSAGE = (
    "Não foi possível baixar dados da OpenF1 agora. Verifique sua conexão e "
    "recarregue a página."
)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def season_data(data_dir: Path, year: int) -> SeasonData:
    return load_season_data(data_dir, year)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def race_details(data_dir: Path, year: int, meeting_key: int) -> RaceDetails:
    return load_race_details(data_dir, year, meeting_key)


@st.cache_data(ttl=SUMMARY_TTL_SECONDS, show_spinner="Lendo o data lake...")
def lake_summary(data_dir: Path) -> PlatformSummary:
    return load_platform_summary(data_dir)


def clear_lake_caches() -> None:
    """Invalida as leituras do lake (após uma carga)."""
    season_data.clear()
    race_details.clear()
    lake_summary.clear()


def kinds_key(kinds: Iterable[SessionKind]) -> tuple[str, ...]:
    """Chave de cache estável para um conjunto de tipos de sessão."""
    return tuple(sorted(k.value for k in kinds))


@st.cache_resource(show_spinner="Carregando dados da OpenF1...")
def bootstrap_season(
    data_dir: Path, year: int, kinds: tuple[str, ...]
) -> BootstrapResult:
    """Carga da temporada para os tipos ``kinds``, uma vez por processo."""
    selected = tuple(SessionKind(k) for k in kinds)
    result = run_season_bootstrap(get_settings(), year, kinds=selected)
    clear_lake_caches()
    return result


@st.cache_resource(show_spinner="Baixando voltas, pneus, pit stops e clima...")
def bootstrap_race(data_dir: Path, year: int, meeting_key: int) -> BootstrapResult:
    """Detalhes de uma corrida, uma vez por processo."""
    meeting = MeetingRef(meeting_key=meeting_key, year=year, name="")
    result = run_race_details(get_settings(), meeting)
    clear_lake_caches()
    return result


def try_load(loader: Callable[..., BootstrapResult], *args: object) -> bool:
    """Executa uma carga da API; em falha, mostra mensagem amigável."""
    try:
        loader(*args)
    except OpenF1AccessError:
        st.warning(ACCESS_DENIED_MESSAGE)
        return False
    except OpenF1Error:
        st.error(API_ERROR_MESSAGE)
        return False
    except DataQualityError:
        st.error(QUALITY_ERROR_MESSAGE)
        return False
    return True


def missing_kinds(
    data_dir: Path, year: int, kinds: Iterable[SessionKind]
) -> set[SessionKind] | None:
    """Tipos pedidos que ainda não têm resultados (``None``: temporada ausente)."""
    if not season_is_loaded(data_dir, year):
        return None
    data = season_data(data_dir, year)
    return set(kinds) - result_kinds(data.results, data.sessions)


def ensure_season(data_dir: Path, year: int, kinds: tuple[SessionKind, ...]) -> None:
    """Garante no lake os resultados de ``year`` para os tipos ``kinds``.

    Tipos já carregados são mantidos (a carga regrava as partições com a união).
    """
    if not kinds:
        return
    missing = missing_kinds(data_dir, year, kinds)
    if missing is not None and not missing:
        return
    wanted = set(kinds)
    if missing is not None:
        data = season_data(data_dir, year)
        wanted |= result_kinds(data.results, data.sessions)
    try_load(bootstrap_season, data_dir, year, kinds_key(wanted))
