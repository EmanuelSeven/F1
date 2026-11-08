"""Barra lateral comum a todas as páginas: marca, filtros e rodapé.

Os valores ficam em ``st.session_state`` (chaves ``filter_*``) e o ano também
em ``st.query_params["ano"]``, para valerem ao trocar de página e ao
compartilhar o link. A interpretação dos filtros está em
``f1.processing.filters``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from f1.dashboard.bootstrap import BOOTSTRAP_YEAR, FIRST_SEASON
from f1.dashboard.views.data import ensure_season, lake_summary, season_data
from f1.dashboard.views.formatting import KIND_LABELS
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
KEY_STATE = "dashboard_filters"
QUERY_YEAR = "ano"
KIND_ORDER: tuple[SessionKind, ...] = tuple(SessionKind)
DEFAULT_KINDS: list[str] = [k.value for k in POINTS_KINDS]
BRAND_HTML = (
    '<div class="f1-brand"><span class="f1-brand-mark">FORMULA 1</span>'
    '<span class="f1-brand-sub"> · Analytics</span></div>'
)


@dataclass(frozen=True)
class DashboardFilters:
    year: int = BOOTSTRAP_YEAR
    season: SeasonFilter = field(default_factory=SeasonFilter)


def season_options(now: datetime) -> list[int]:
    """Temporadas disponíveis, da mais recente para a mais antiga."""
    return list(range(now.year, FIRST_SEASON - 1, -1))


def initial_year(options: Sequence[int], query_value: object) -> int:
    """Ano inicial: o da URL (``?ano=``), se válido; senão ``BOOTSTRAP_YEAR``."""
    try:
        year = int(str(query_value))
    except ValueError:
        year = BOOTSTRAP_YEAR
    if year in options:
        return year
    return BOOTSTRAP_YEAR if BOOTSTRAP_YEAR in options else options[0]


def selected_kinds(values: Sequence[str]) -> tuple[SessionKind, ...]:
    """Tipos marcados, na ordem canônica (corrida, sprint, classificação, treino)."""
    chosen = set(values)
    return tuple(k for k in KIND_ORDER if k.value in chosen)


def reset_filters() -> None:
    """Callback de "Limpar filtros": volta tudo ao padrão, exceto a temporada."""
    st.session_state[KEY_KINDS] = list(DEFAULT_KINDS)
    st.session_state[KEY_GP] = None
    st.session_state[KEY_TEAMS] = []
    st.session_state[KEY_DRIVERS] = []


def current_filters() -> DashboardFilters:
    """Filtros aplicados na execução atual (definidos pela barra lateral)."""
    value = st.session_state.get(KEY_STATE)
    return value if isinstance(value, DashboardFilters) else DashboardFilters()


def _init_state(options: Sequence[int]) -> None:
    state = st.session_state
    if KEY_SEASON not in state:
        state[KEY_SEASON] = initial_year(options, st.query_params.get(QUERY_YEAR))
    if KEY_KINDS not in state:
        state[KEY_KINDS] = list(DEFAULT_KINDS)
    for key, empty in ((KEY_GP, None), (KEY_TEAMS, []), (KEY_DRIVERS, [])):
        if key not in state:
            state[key] = empty


def _keep_valid(key: str, valid: Sequence[object]) -> None:
    """Descarta valores que não existem mais (ex.: ao trocar de temporada)."""
    current = st.session_state.get(key)
    if isinstance(current, list):
        st.session_state[key] = [v for v in current if v in valid]
    elif current is not None and current not in valid:
        st.session_state[key] = None


def render_sidebar_filters(data_dir: Path) -> DashboardFilters:
    """Desenha a marca e os filtros; carrega a temporada escolhida se preciso."""
    options = season_options(datetime.now(UTC))
    _init_state(options)
    with st.sidebar:
        st.markdown(BRAND_HTML, unsafe_allow_html=True)
        st.markdown(
            '<div class="f1-sidebar-title">Filtros</div>', unsafe_allow_html=True
        )
        year = int(st.selectbox("Temporada", options, key=KEY_SEASON))
        kinds = selected_kinds(
            st.multiselect(
                "Tipo de sessão",
                [k.value for k in KIND_ORDER],
                format_func=lambda v: KIND_LABELS[SessionKind(v)],
                key=KEY_KINDS,
                placeholder="Escolha ao menos um tipo",
            )
        )
    st.query_params[QUERY_YEAR] = str(year)

    ensure_season(data_dir, year, kinds)  # mensagens aparecem na área principal
    data = season_data(data_dir, year)
    gps = grand_prix_options(data.sessions, data.meetings)
    gp_labels = dict(zip(gps["meeting_key"].astype(int), gps["label"], strict=True))
    teams = team_options(data.drivers)

    with st.sidebar:
        _keep_valid(KEY_GP, list(gp_labels))
        meeting_key = st.selectbox(
            "Grande Prêmio",
            [None, *gp_labels],
            format_func=lambda k: "Todos" if k is None else gp_labels[k],
            key=KEY_GP,
        )
        _keep_valid(KEY_TEAMS, teams)
        has_people = bool(st.session_state[KEY_TEAMS] or st.session_state[KEY_DRIVERS])
        with st.expander("Equipe e piloto", expanded=has_people):
            chosen_teams = st.multiselect(
                "Equipes", teams, key=KEY_TEAMS, placeholder="Todas"
            )
            people = driver_options(data.drivers, data.sessions, chosen_teams)
            labels = {
                int(n): f"{a} · {name}"
                for n, a, name in zip(
                    people["driver_number"],
                    people["acronym"],
                    people["name"],
                    strict=True,
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
        st.button("Limpar filtros", on_click=reset_filters, width="stretch")

    filters = DashboardFilters(
        year=year,
        season=SeasonFilter(
            kinds=kinds,
            meeting_key=meeting_key,
            teams=tuple(chosen_teams),
            drivers=tuple(int(n) for n in chosen_drivers),
        ),
    )
    st.session_state[KEY_STATE] = filters
    return filters


def render_sidebar_footer(data_dir: Path) -> None:
    """Rodapé com a fonte e a data da última ingestão no lake."""
    summary = lake_summary(data_dir)
    run = summary.last_run
    when = run.ingested_at.strftime("%d/%m/%Y %H:%M UTC") if run else "—"
    st.sidebar.caption(f"Dados: OpenF1 · última atualização {when}")
