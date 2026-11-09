"""Dados do dashboard: leituras em cache e cargas sob demanda da OpenF1.

Compartilhado pela barra lateral (que dispara a carga da temporada escolhida)
e pelas páginas. Cargas usam ``st.cache_resource`` (uma vez por processo;
falhas não ficam em cache) e leituras do lake usam ``st.cache_data``.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from f1.config.settings import get_settings
from f1.dashboard.bootstrap import (
    BootstrapResult,
    SourceFactory,
    run_grid,
    run_meeting_laps,
    run_race_details,
    run_season_bootstrap,
)
from f1.dashboard.loaders import (
    PlatformSummary,
    RaceDetails,
    SeasonData,
    lap_session_keys,
    load_platform_summary,
    load_race_details,
    load_rejection_history,
    load_season_data,
    read_dataset,
    season_is_loaded,
)
from f1.domain.endpoints import Endpoint
from f1.domain.models import Filter, MeetingRef, SessionKind
from f1.ingestion.openf1_client import (
    OpenF1AccessError,
    OpenF1Client,
    OpenF1Error,
)
from f1.processing.last_race import default_season, has_completed_race
from f1.processing.normalize import normalize
from f1.processing.standings import finished_kinds, result_kinds
from f1.quality.validation import DataQualityError

CACHE_TTL_SECONDS = 300
LATEST_TTL_SECONDS = 600  # página Última corrida: cache curto
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


@st.cache_data(ttl=SUMMARY_TTL_SECONDS, show_spinner=False)
def rejection_history(data_dir: Path) -> pd.DataFrame:
    return load_rejection_history(data_dir)


def clear_lake_caches() -> None:
    """Invalida as leituras do lake (após uma carga)."""
    season_data.clear()
    race_details.clear()
    lake_summary.clear()
    rejection_history.clear()


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
    keep = lap_session_keys(data_dir, year, meeting_key)  # ex.: voltas da quali
    result = run_race_details(get_settings(), meeting, keep_sessions=keep)
    clear_lake_caches()
    return result


@st.cache_resource(show_spinner="Baixando tempos de volta...")
def bootstrap_laps(
    data_dir: Path, year: int, meeting_key: int, session_keys: tuple[int, ...]
) -> BootstrapResult:
    """Voltas das sessões ``session_keys`` de um meeting, uma vez por processo."""
    meeting = MeetingRef(meeting_key=meeting_key, year=year, name="")
    result = run_meeting_laps(get_settings(), meeting, session_keys)
    clear_lake_caches()
    return result


def ensure_laps(
    data_dir: Path, year: int, meeting_key: int, session_keys: Iterable[int]
) -> None:
    """Garante no lake as voltas das ``session_keys`` (mantém as já gravadas)."""
    wanted = {int(k) for k in session_keys}
    present = lap_session_keys(data_dir, year, meeting_key)
    if not wanted or wanted <= present:
        return
    union = tuple(sorted(wanted | present))
    try_load(bootstrap_laps, data_dir, year, meeting_key, union)


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
    """Tipos pedidos que ainda não têm resultados (``None``: temporada ausente).

    Só conta tipos com sessões já encerradas: numa temporada sem sprints, por
    exemplo, não há resultados de sprint a buscar.
    """
    if not season_is_loaded(data_dir, year):
        return None
    data = season_data(data_dir, year)
    possible = finished_kinds(data.sessions, datetime.now(UTC))
    return (set(kinds) & possible) - result_kinds(data.results, data.sessions)


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


@dataclass(frozen=True)
class RefreshOutcome:
    """Resultado de uma atualização da API (falhas também ficam em cache)."""

    ok: bool
    access_denied: bool = False


def refresh_bucket(now: datetime) -> int:
    """Janela de ``LATEST_TTL_SECONDS``: a mesma chave de cache dentro dela."""
    return int(now.timestamp() // LATEST_TTL_SECONDS)


@st.cache_resource(show_spinner="Buscando os resultados mais recentes da OpenF1...")
def refresh_results(
    data_dir: Path, year: int, kinds: tuple[str, ...], bucket: int
) -> RefreshOutcome:
    """Recarrega calendário e resultados de ``year`` (no máximo 1x por janela).

    Diferente das outras cargas, a falha também é guardada em cache durante a
    janela, para não repetir requisições a cada interação enquanto a OpenF1
    estiver indisponível.
    """
    selected = tuple(SessionKind(k) for k in kinds)
    try:
        run_season_bootstrap(get_settings(), year, kinds=selected)
    except OpenF1AccessError:
        return RefreshOutcome(ok=False, access_denied=True)
    except (OpenF1Error, DataQualityError):
        return RefreshOutcome(ok=False)
    clear_lake_caches()
    grid_data.clear()
    return RefreshOutcome(ok=True)


@st.cache_data(ttl=LATEST_TTL_SECONDS, show_spinner=False)
def grid_data(data_dir: Path, year: int, meeting_key: int) -> pd.DataFrame:
    return read_dataset(data_dir, Endpoint.STARTING_GRID, year, meeting_key)


@st.cache_resource(show_spinner="Baixando a grade de largada...")
def bootstrap_grid(
    data_dir: Path, year: int, meeting_key: int, bucket: int
) -> BootstrapResult:
    """Grade de largada (tentada de novo a cada janela enquanto estiver vazia)."""
    result = run_grid(get_settings(), year, meeting_key)
    grid_data.clear()
    clear_lake_caches()
    return result


def ensure_grid(data_dir: Path, year: int, meeting_key: int, now: datetime) -> None:
    if grid_data(data_dir, year, meeting_key).empty:
        try_load(bootstrap_grid, data_dir, year, meeting_key, refresh_bucket(now))


def season_has_completed_race(
    data_dir: Path,
    year: int,
    now: datetime,
    source_factory: SourceFactory | None = None,
) -> bool:
    """``year`` tem corrida concluída? Usa o lake ou, se faltar, a API.

    Na API é uma requisição leve (só as sessões ``Race`` do ano).

    Raises:
        OpenF1Error: a API não pôde ser consultada.
    """
    sessions = read_dataset(data_dir, Endpoint.SESSIONS, year)
    if sessions.empty:
        factory = source_factory or OpenF1Client.from_settings
        with factory(get_settings()) as source:
            records = source.fetch(
                Endpoint.SESSIONS,
                [Filter("year", year), Filter("session_name", "Race")],
            )
        sessions = normalize(Endpoint.SESSIONS, records)
    return has_completed_race(sessions, now)


@st.cache_data(ttl=LATEST_TTL_SECONDS, show_spinner=False)
def default_year(data_dir: Path, years: tuple[int, ...], bucket: int) -> int:
    """Ano padrão do filtro "Temporada" (em cache por janela de 10 min)."""
    now = datetime.now(UTC)
    return default_season(
        years, lambda year: season_has_completed_race(data_dir, year, now)
    )
