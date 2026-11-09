"""Página "Voltas": as 5 voltas mais rápidas por circuito.

Usa todos os filtros da barra lateral: temporada, tipo de sessão (padrão
corridas + sprints; Classificação costuma ter as voltas mais rápidas), Grande
Prêmio (o circuito; com "Todos", o mais recente) e equipe/piloto.
"""

import html
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from f1.config.settings import get_settings
from f1.dashboard.views import charts
from f1.dashboard.views.data import ensure_laps, race_details, season_data
from f1.dashboard.views.driver_badge import driver_html
from f1.dashboard.views.formatting import (
    KIND_LABELS,
    format_lap,
    session_label,
)
from f1.dashboard.views.sidebar import current_filters
from f1.dashboard.views.tables import (
    NATIONALITY_COLUMN,
    TEAM_COLUMN,
    nationality_cells,
    render_table,
    team_label,
)
from f1.dashboard.views.theme import section
from f1.domain.models import SessionKind
from f1.processing.fastest_laps import (
    TOP_LAPS,
    circuit_sessions,
    fastest_laps,
    latest_grand_prix,
)
from f1.processing.filters import allowed_drivers, grand_prix_options

PLOT_CONFIG = {"displayModeBar": False}


def kinds_text(kinds: tuple[SessionKind, ...]) -> str:
    """``(RACE, SPRINT)`` → ``"corrida e sprint"``."""
    names = [KIND_LABELS[k].lower() for k in kinds]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " e " + names[-1]


def laps_title(year: int) -> str:
    """Título da página: ``"Fórmula 1 · Top 5 Voltas Mais Rápidas 2026"``."""
    return f"Fórmula 1 · Top {TOP_LAPS} Voltas Mais Rápidas {year}"


def laps_subtitle(round_number: int, kinds: tuple[SessionKind, ...]) -> str:
    """Subcabeçalho: rodada do evento exibido e os tipos de sessão do filtro."""
    return (
        f"Rodada {round_number} · Exibindo as {TOP_LAPS} voltas mais rápidas em "
        f"{kinds_text(kinds)}"
    )


def laps_display(top: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Pos.": top["position"],
            "Piloto": top["acronym"],
            "Nome": top["name"],
            NATIONALITY_COLUMN: nationality_cells(top["country"]),
            TEAM_COLUMN: [team_label(t) for t in top["team"]],
            "Tempo": [format_lap(t) for t in top["lap_duration"]],
            "Diferença": [
                "—" if g == 0 else f"+{g:.3f} s".replace(".", ",") for g in top["gap"]
            ],
            "Sessão": [session_label(n) for n in top["session_name"]],
            "Volta": top["lap_number"],
        }
    )


def render_laps() -> None:
    """Conteúdo da página "Voltas"."""
    data_dir = get_settings().data_dir
    filters = current_filters()
    year, filt = filters.year, filters.season
    title = laps_title(year)
    st.markdown(f'<div class="f1-title">{title}</div>', unsafe_allow_html=True)
    if not filt.kinds:
        st.info("Escolha ao menos um tipo de sessão na barra lateral.")
        return
    now = datetime.now(UTC)
    data = season_data(data_dir, year)
    meeting_key = filt.meeting_key or latest_grand_prix(data.sessions, now)
    gps = grand_prix_options(data.sessions, data.meetings)
    match = gps.loc[gps["meeting_key"] == meeting_key]
    if meeting_key is None or match.empty:
        st.info(f"Ainda não há Grandes Prêmios disputados em {year}.")
        return
    gp = match.iloc[0]
    section(
        f"Circuito {gp['circuit']} · {gp['gp']}",
        laps_subtitle(int(gp["round"]), filt.kinds),
    )
    if filt.meeting_key is None:
        st.caption(
            "Mostrando o Grande Prêmio mais recente; escolha outro circuito em "
            "**Grande Prêmio** na barra lateral."
        )
    keys = circuit_sessions(data.sessions, int(meeting_key), filt.kinds, now)
    if not keys:
        st.info("As sessões selecionadas deste Grande Prêmio ainda não aconteceram.")
        return
    ensure_laps(data_dir, year, int(meeting_key), keys)
    laps = race_details(data_dir, year, int(meeting_key)).laps
    one_per_driver = st.toggle(
        "Uma volta por piloto",
        value=False,
        key="laps_one_per_driver",
        help="Mostra só a melhor volta de cada piloto.",
    )
    top = fastest_laps(
        laps,
        data.drivers,
        data.sessions,
        session_keys=keys,
        one_per_driver=one_per_driver,
        allowed=allowed_drivers(data.drivers, filt),
    )
    if top.empty:
        st.info("Sem tempos de volta para os filtros selecionados.")
        return
    best = top.iloc[0]
    st.markdown(
        f"Volta mais rápida: **{format_lap(best['lap_duration'])}**, de "
        f"**{driver_html(best)}** ({html.escape(str(best['team']))}), "
        f"{session_label(best['session_name'])}, volta {int(best['lap_number'])}.",
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        charts.fastest_laps_chart(top),
        config=PLOT_CONFIG,
        key=f"fastest_{year}_{meeting_key}",
    )
    render_table(laps_display(top), top["colour"].tolist(), key="fastest_laps_table")
    st.caption(
        "Tempos como registrados pela OpenF1; voltas anuladas pela direção de prova "
        "(ex.: limites de pista) podem aparecer."
    )
