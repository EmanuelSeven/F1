"""Barra lateral comum a todas as páginas: marca, filtros e rodapé.

Os valores ficam em ``st.session_state`` (chaves ``filter_*``) e o ano também
em ``st.query_params["ano"]``, para valerem ao trocar de página e ao
compartilhar o link. A interpretação dos filtros está em
``f1.processing.filters``.
"""

from collections.abc import Callable, Sequence
from copy import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.navigation.page import StreamlitPage

from f1.dashboard.bootstrap import FIRST_SEASON
from f1.dashboard.views.data import (
    default_year,
    ensure_season,
    lake_summary,
    refresh_bucket,
    season_data,
)
from f1.dashboard.views.formatting import KIND_LABELS, format_brasilia, format_count
from f1.domain.models import POINTS_KINDS, SessionKind
from f1.processing.filters import (
    SeasonFilter,
    driver_options,
    grand_prix_options,
    team_options,
)

KEY_SEASON = "filter_season"
KEY_KINDS = "filter_kinds"
KEY_GP = "filter_gp"
KEY_TEAMS = "filter_teams"
KEY_DRIVERS = "filter_drivers"
KEY_KINDS_SAVED = "filter_kinds_saved"  # sobrevive a páginas sem o widget
KEY_KINDS_LOCKED = "filter_kinds_locked"
KEY_SEASON_LOCKED = "filter_season_locked"
KEY_STATE = "dashboard_filters"
QUERY_YEAR = "ano"
KIND_ORDER: tuple[SessionKind, ...] = tuple(SessionKind)
DEFAULT_KINDS: list[str] = [k.value for k in POINTS_KINDS]
BRAND_HTML = (
    '<div class="f1-brand"><span class="f1-brand-mark">FORMULA 1</span>'
    '<span class="f1-brand-sub"> · Analytics</span></div>'
)


class KindsFilter(StrEnum):
    """Como o filtro "Tipo de sessão" aparece numa página."""

    EDITABLE = "editable"  # a página usa o filtro
    LOCKED = "locked"  # desabilitado, com explicação; a página usa o padrão
    HIDDEN = "hidden"  # oculto; a página não depende do tipo de sessão


@dataclass(frozen=True)
class PageFilters:
    """Filtros que uma página usa."""

    kinds: KindsFilter = KindsFilter.EDITABLE
    note: str | None = None
    season: bool = True  # usa o filtro de temporada
    details: bool = True  # usa Grande Prêmio e equipe/piloto
    season_note: str | None = None


EDITABLE_PAGE = PageFilters()
SEASON_PAGE = PageFilters(
    KindsFilter.LOCKED,
    "Não se aplica a esta página: pontos, vencedores e KPIs da temporada "
    "consideram sempre corridas e sprints.",
)
LAKE_PAGE = PageFilters(KindsFilter.HIDDEN)
LAPS_PAGE = EDITABLE_PAGE  # "Voltas": o tipo de sessão escolhe as sessões
LATEST_PAGE = PageFilters(
    KindsFilter.HIDDEN,
    season=False,
    details=False,
    season_note=(
        "Não se aplica a esta página: ela mostra sempre a corrida concluída "
        "mais recente."
    ),
)
_DETAIL_DEFAULTS: tuple[tuple[str, object], ...] = (
    (KEY_GP, None),
    (KEY_TEAMS, []),
    (KEY_DRIVERS, []),
)


def _current_year() -> int:
    return datetime.now(UTC).year


@dataclass(frozen=True)
class DashboardFilters:
    year: int = field(default_factory=_current_year)
    season: SeasonFilter = field(default_factory=SeasonFilter)
    # Espaço do seletor de temporada em páginas que não usam o filtro: a
    # página o preenche (ex.: com o ano da corrida exibida).
    season_slot: DeltaGenerator | None = field(default=None, compare=False)


def season_options(now: datetime) -> list[int]:
    """Temporadas disponíveis, da mais recente para a mais antiga."""
    return list(range(now.year, FIRST_SEASON - 1, -1))


def initial_year(
    options: Sequence[int], query_value: object, default: Callable[[], int]
) -> int:
    """Ano inicial: o da URL (``?ano=``), se válido; senão ``default()``.

    ``default`` só é chamado sem ano válido na URL (a consulta é evitada). Um
    padrão fora de ``options`` vira o ano mais recente da lista.
    """
    try:
        year = int(str(query_value))
    except ValueError:
        year = 0
    if year in options:
        return year
    fallback = default()
    return fallback if fallback in options else options[0]


def selected_kinds(values: Sequence[str]) -> tuple[SessionKind, ...]:
    """Tipos marcados, na ordem canônica (corrida, sprint, classificação, treino)."""
    chosen = set(values)
    return tuple(k for k in KIND_ORDER if k.value in chosen)


def reset_filters() -> None:
    """Callback de "Limpar filtros": volta tudo ao padrão, exceto a temporada."""
    state = st.session_state
    state[KEY_KINDS_SAVED] = list(DEFAULT_KINDS)
    state[KEY_KINDS] = list(DEFAULT_KINDS)
    for key, empty in _DETAIL_DEFAULTS:
        state[key] = copy(empty)
        state[_saved(key)] = copy(empty)


def current_filters() -> DashboardFilters:
    """Filtros aplicados na execução atual (definidos pela barra lateral)."""
    value = st.session_state.get(KEY_STATE)
    return value if isinstance(value, DashboardFilters) else DashboardFilters()


def _saved(key: str) -> str:
    """Chave que guarda o valor de um filtro fora do widget.

    O Streamlit descarta o estado de widgets que não são desenhados numa
    execução; como alguns filtros somem em certas páginas, o valor também fica
    numa chave comum, restaurada quando o widget volta.
    """
    return f"{key}_saved"


def _restore(key: str, empty: object) -> None:
    state = st.session_state
    if key not in state:
        state[key] = copy(state.get(_saved(key), empty))


def _remember(key: str, value: object) -> None:
    st.session_state[_saved(key)] = copy(value)


def _init_state(options: Sequence[int], data_dir: Path) -> None:
    state = st.session_state
    if KEY_SEASON not in state:
        saved = state.get(_saved(KEY_SEASON))
        state[KEY_SEASON] = (
            saved
            if saved in options
            else initial_year(
                options,
                st.query_params.get(QUERY_YEAR),
                lambda: default_year(
                    data_dir, tuple(options), refresh_bucket(datetime.now(UTC))
                ),
            )
        )
    if KEY_KINDS_SAVED not in state:
        state[KEY_KINDS_SAVED] = list(DEFAULT_KINDS)
    for key, empty in _DETAIL_DEFAULTS:
        _restore(key, empty)


def _keep_valid(key: str, valid: Sequence[object]) -> None:
    """Descarta valores que não existem mais (ex.: ao trocar de temporada)."""
    current = st.session_state.get(key)
    if isinstance(current, list):
        st.session_state[key] = [v for v in current if v in valid]
    elif current is not None and current not in valid:
        st.session_state[key] = None


def _kinds_filter(page: PageFilters) -> tuple[SessionKind, ...]:
    """Desenha (ou não) o filtro "Tipo de sessão" e retorna os tipos efetivos."""
    options = [k.value for k in KIND_ORDER]
    if page.kinds is KindsFilter.HIDDEN:
        return POINTS_KINDS
    if page.kinds is KindsFilter.LOCKED:
        st.multiselect(
            "Tipo de sessão",
            options,
            default=DEFAULT_KINDS,
            format_func=lambda v: KIND_LABELS[SessionKind(v)],
            key=KEY_KINDS_LOCKED,
            disabled=True,
            help=page.note,
        )
        if page.note:
            st.caption(page.note)
        return POINTS_KINDS
    if KEY_KINDS not in st.session_state:  # descartado numa página sem o widget
        st.session_state[KEY_KINDS] = list(st.session_state[KEY_KINDS_SAVED])
    values = st.multiselect(
        "Tipo de sessão",
        options,
        format_func=lambda v: KIND_LABELS[SessionKind(v)],
        key=KEY_KINDS,
        placeholder="Escolha ao menos um tipo",
    )
    st.session_state[KEY_KINDS_SAVED] = list(values)
    return selected_kinds(values)


def _navigation(pages: Sequence[StreamlitPage]) -> None:
    """Links das páginas (a navegação fica na barra lateral, acima dos filtros)."""
    for page in pages:
        st.page_link(page, label=page.title, icon=page.icon or None)
    st.divider()


def _detail_filters(
    data_dir: Path, year: int
) -> tuple[int | None, list[str], list[int]]:
    """Grande Prêmio e equipe/piloto (opções dependentes do ano)."""
    data = season_data(data_dir, year)
    gps = grand_prix_options(data.sessions, data.meetings)
    gp_labels = dict(zip(gps["meeting_key"].astype(int), gps["label"], strict=True))
    teams = team_options(data.drivers)

    _keep_valid(KEY_GP, list(gp_labels))
    meeting_key = st.selectbox(
        "Grande Prêmio",
        [None, *gp_labels],
        format_func=lambda k: "Todos" if k is None else gp_labels[k],
        key=KEY_GP,
    )
    _remember(KEY_GP, meeting_key)
    _keep_valid(KEY_TEAMS, teams)
    has_people = bool(st.session_state[KEY_TEAMS] or st.session_state[KEY_DRIVERS])
    with st.expander("Equipe e piloto", expanded=has_people):
        chosen_teams = st.multiselect(
            "Equipes", teams, key=KEY_TEAMS, placeholder="Todas"
        )
        _remember(KEY_TEAMS, chosen_teams)
        people = driver_options(data.drivers, data.sessions, chosen_teams)
        labels = {
            int(n): str(name)
            for n, a, name in zip(
                people["driver_number"], people["acronym"], people["name"], strict=True
            )
        }
        _keep_valid(KEY_DRIVERS, list(labels))
        chosen_drivers = st.multiselect(
            "Pilotos",
            list(labels),
            format_func=lambda n: labels[n],
            key=KEY_DRIVERS,
            placeholder="Todos",
        )
        _remember(KEY_DRIVERS, chosen_drivers)
    st.button("Limpar filtros", on_click=reset_filters, width="stretch")
    return meeting_key, list(chosen_teams), [int(n) for n in chosen_drivers]


def render_sidebar_filters(
    data_dir: Path,
    page: PageFilters = EDITABLE_PAGE,
    pages: Sequence[StreamlitPage] = (),
) -> DashboardFilters:
    """Desenha marca, navegação (``pages``) e os filtros que a ``page`` usa.

    Carrega a temporada escolhida se a página depender dela.
    """
    options = season_options(datetime.now(UTC))
    _init_state(options, data_dir)
    with st.sidebar:
        st.markdown(BRAND_HTML, unsafe_allow_html=True)
        if pages:
            _navigation(pages)
        st.markdown(
            '<div class="f1-sidebar-title">Filtros</div>', unsafe_allow_html=True
        )
        slot: DeltaGenerator | None = None
        if page.season:
            year = int(st.selectbox("Temporada", options, key=KEY_SEASON))
            _remember(KEY_SEASON, year)
            st.query_params[QUERY_YEAR] = str(year)
        else:
            # O seletor sai da página (o ano escolhido fica guardado); a página
            # preenche o espaço com o seu próprio ano (show_locked_season).
            year = int(st.session_state[KEY_SEASON])
            _remember(KEY_SEASON, year)
            slot = st.empty()
            if page.season_note:
                st.caption(page.season_note)
        kinds = _kinds_filter(page)

    meeting_key: int | None = None
    teams: list[str] = []
    drivers: list[int] = []
    if page.season:
        ensure_season(data_dir, year, kinds)  # mensagens aparecem na área principal
    if page.season and page.details:
        with st.sidebar:
            meeting_key, teams, drivers = _detail_filters(data_dir, year)

    filters = DashboardFilters(
        year=year,
        season=SeasonFilter(
            kinds=kinds,
            meeting_key=meeting_key,
            teams=tuple(teams),
            drivers=tuple(drivers),
        ),
        season_slot=slot,
    )
    st.session_state[KEY_STATE] = filters
    return filters


def show_locked_season(year: int, note: str | None = None) -> None:
    """Preenche o seletor de temporada desabilitado com ``year``.

    Usado por páginas que não seguem o filtro (ex.: "Última corrida", que
    mostra o ano da corrida exibida).
    """
    slot = current_filters().season_slot
    if slot is None:
        return
    slot.selectbox(
        "Temporada",
        [year],
        index=0,
        key=KEY_SEASON_LOCKED,
        disabled=True,
        help=note,
    )


def render_sidebar_footer(data_dir: Path, page_views: int | None = None) -> None:
    """Rodapé com a fonte, a data da última ingestão e o total de acessos."""
    summary = lake_summary(data_dir)
    run = summary.last_run
    when = format_brasilia(run.ingested_at if run else None)
    text = f"Dados: OpenF1 · última atualização {when}"
    if page_views is not None:
        text += f" · 👁️ {format_count(page_views)} acessos"
    st.sidebar.caption(text)
