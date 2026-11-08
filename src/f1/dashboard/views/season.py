"""Página "Temporada": painel analítico de uma temporada de F1.

Os filtros vêm da barra lateral (``f1.dashboard.views.sidebar``); a aplicação
deles está em ``f1.processing.filters``; leituras e cargas em
``f1.dashboard.views.data``. Este módulo só compõe a tela.
"""

import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from f1.config.settings import get_settings
from f1.dashboard.loaders import RaceDetails, SeasonData, race_details_loaded
from f1.dashboard.views import charts
from f1.dashboard.views.data import (
    bootstrap_race,
    race_details,
    season_data,
    try_load,
)
from f1.dashboard.views.formatting import (
    format_day_month,
    format_lap,
    format_points,
    format_result_time,
    format_seconds,
    format_status,
    format_temperature,
    points_caption,
    points_subtitle,
    races_card,
    session_label,
    summary_sentence,
    winners_caption,
)
from f1.dashboard.views.sidebar import current_filters
from f1.dashboard.views.theme import kpi_card, section
from f1.domain.models import POINTS_KINDS, SessionKind
from f1.processing.filters import SeasonFilter, SeasonView, season_view
from f1.processing.standings import (
    RACE,
    SeasonKpis,
    lap_times,
    pit_stops,
    race_classification,
    session_weather,
    tyre_stints,
    weather_summary,
)

ROW_HEIGHT = 35
SQUARE = "■"
TEAM_COLUMN = "Equipe"
HIGHLIGHT_STYLE = "background-color: rgba(225, 6, 0, 0.22)"
PLOT_CONFIG = {"displayModeBar": False}
DETAIL_TABS = (
    "Resultado final",
    "Tempos de volta",
    "Estratégia de pneus",
    "Pit stops",
    "Clima",
)


# --- tabelas de exibição (puras) -----------------------------------------


def summary_html(kpis: SeasonKpis) -> str:
    """Frase-resumo em HTML, com os destaques em ``<strong>``."""
    sentence = escape(summary_sentence(kpis))
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", sentence)


def team_label(team: object) -> str:
    """Equipe com o quadradinho de cor: ``"■ Red Bull Racing"``."""
    return f"{SQUARE} {team}"


def winners_display(
    winners: pd.DataFrame, *, with_session: bool = False
) -> pd.DataFrame:
    columns: dict[str, object] = {
        "Rod.": winners["round"].astype("Int64"),
        "GP": winners["gp"],
    }
    if with_session:
        columns["Sessão"] = [session_label(n) for n in winners["session_name"]]
    columns["Data"] = [format_day_month(d) for d in winners["date_start"]]
    columns["Vencedor"] = winners["acronym"]
    columns[TEAM_COLUMN] = [team_label(t) for t in winners["team"]]
    return pd.DataFrame(columns)


def classification_display(classification: pd.DataFrame) -> pd.DataFrame:
    rows = classification.to_dict("records")
    return pd.DataFrame(
        {
            "Pos.": [
                "NC" if pd.isna(r["position"]) else str(int(r["position"]))
                for r in rows
            ],
            "Piloto": classification["acronym"],
            "Nome": classification["name"],
            TEAM_COLUMN: [team_label(t) for t in classification["team"]],
            "Voltas": classification["number_of_laps"],
            "Tempo / diferença": [
                format_result_time(r["position"], r["duration"], r["gap_to_leader"])
                for r in rows
            ],
            "Pontos": [
                format_points(0.0 if pd.isna(r["points"]) else float(r["points"]))
                for r in rows
            ],
            "Situação": [format_status(r["dnf"], r["dns"], r["dsq"]) for r in rows],
        }
    )


def pit_stops_display(stops: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Volta": stops["lap_number"],
            "Piloto": stops["acronym"],
            TEAM_COLUMN: [team_label(t) for t in stops["team"]],
            "Parada (s)": [format_seconds(v) for v in stops["stop_duration"]],
            "Pit lane (s)": [format_seconds(v) for v in stops["lane_duration"]],
        }
    )


def table_styles(
    display: pd.DataFrame, colours: Sequence[str], highlight: Sequence[int] = ()
) -> pd.DataFrame:
    """CSS por célula: cor da equipe na coluna ``Equipe`` e linhas em destaque."""
    styles = pd.DataFrame("", index=display.index, columns=display.columns)
    if TEAM_COLUMN in styles.columns:
        styles[TEAM_COLUMN] = [f"color: {c}" for c in colours]
    for row in highlight:
        styles.iloc[row] = [
            f"{css}; {HIGHLIGHT_STYLE}" if css else HIGHLIGHT_STYLE
            for css in styles.iloc[row]
        ]
    return styles


def chart_standings(standings: pd.DataFrame, *, show_zero: bool) -> pd.DataFrame:
    """Pilotos do gráfico de pontos: sem os de 0 ponto, salvo ``show_zero``."""
    if show_zero:
        return standings
    return standings.loc[standings["points"] > 0].reset_index(drop=True)


def selection_key(year: int, filt: SeasonFilter) -> str:
    """Chave da tabela de vencedores: muda quando as linhas mudam."""
    parts = [str(year), *filt.kinds, *filt.teams, *map(str, filt.drivers)]
    return "winners_" + "_".join(re.sub(r"\W+", "", p) for p in parts)


# --- componentes -----------------------------------------------------------


def _table(  # noqa: PLR0913 - opções de exibição explícitas
    display: pd.DataFrame,
    colours: Sequence[str],
    *,
    key: str,
    selectable: bool = False,
    highlight: Sequence[int] = (),
    max_rows: int = 25,
    column_config: dict[str, object] | None = None,
) -> list[int]:
    """Tabela com a equipe colorida; retorna as linhas selecionadas.

    O ``st.dataframe`` só aceita estilo por célula, por isso a célula ``Equipe``
    inteira (quadradinho + nome) recebe a cor.
    """
    styles = table_styles(display, colours, highlight)
    styled = display.style.apply(lambda _df: styles, axis=None)
    height = ROW_HEIGHT * (min(len(display), max_rows) + 1) + 3
    options: dict[str, object] = {
        "hide_index": True,
        "width": "stretch",
        "height": height,
        "key": key,
        "column_config": dict(column_config or {}),
    }
    if not selectable:
        st.dataframe(styled, **options)  # type: ignore[call-overload]
        return []
    event = st.dataframe(  # type: ignore[call-overload]
        styled, on_select="rerun", selection_mode="single-row", **options
    )
    selection = getattr(event, "selection", None)
    return [int(r) for r in getattr(selection, "rows", [])]


def _header(year: int) -> None:
    title = f"Fórmula 1 · temporada {year}"
    st.markdown(f'<div class="f1-title">{title}</div>', unsafe_allow_html=True)


def _kpi_cards(kpis: SeasonKpis) -> None:
    races, races_caption = races_card(kpis)
    sprints = str(kpis.sprints)
    leader = format_points(kpis.leader_points) if kpis.points_kinds else "—"
    cards = (
        ("Corridas", races, races_caption),
        ("Sprints", sprints, "Corridas curtas de sábado"),
        ("Vencedores diferentes", str(kpis.distinct_winners), winners_caption(kpis)),
        ("Pontos do líder", leader, points_caption(kpis.points_kinds)),
    )
    for column, (label, value, caption) in zip(st.columns(4), cards, strict=True):
        column.markdown(kpi_card(label, value, caption), unsafe_allow_html=True)


def _points_column(view: SeasonView, year: int) -> None:
    st.markdown("#### Pontos por piloto")
    st.caption(points_subtitle(view.kpis.points_kinds))
    show_zero = st.toggle(
        "Mostrar pilotos sem pontos", value=False, key=f"show_zero_{year}"
    )
    rows = chart_standings(view.standings, show_zero=show_zero)
    if view.standings.empty:
        st.info("Nenhum piloto corresponde aos filtros.")
    elif rows.empty:
        st.info("Nenhum piloto dos filtros marcou pontos.")
    else:
        st.plotly_chart(
            charts.points_bar(rows), config=PLOT_CONFIG, key=f"points_{year}"
        )


def _winners_column(view: SeasonView, year: int) -> pd.Series | None:
    by_race = view.kpis.primary == (SessionKind.RACE,)
    noun = "corrida" if by_race else "sessão"
    st.markdown(f"#### Vencedores por {noun}")
    st.caption(f"Clique em uma {noun} para ver os detalhes abaixo.")
    if view.winners.empty:
        st.info("Nenhuma vitória dos pilotos filtrados.")
        return None
    rows = _table(
        winners_display(view.winners, with_session=not by_race),
        view.winners["colour"].tolist(),
        key=selection_key(year, view.filter),
        selectable=True,
        highlight=view.highlighted_rows,
        column_config={"Rod.": st.column_config.NumberColumn(width=56)},
    )
    return view.winners.iloc[rows[0]] if rows else None


def _season_section(view: SeasonView, year: int) -> pd.Series | None:
    section("Temporada")
    left, right = st.columns([1.05, 1], gap="large")
    with left:
        _points_column(view, year)
    with right:
        return _winners_column(view, year)


# --- detalhes da corrida ------------------------------------------------


def _laps_tab(
    details: RaceDetails, data: SeasonData, session_key: int, order: Sequence[str]
) -> None:
    hide_slow = st.toggle(
        "Ocultar voltas lentas (volta 1, saída do box e safety car)",
        value=True,
        key=f"hide_slow_{session_key}",
    )
    laps = lap_times(details.laps, data.drivers, session_key, exclude_slow=hide_slow)
    if laps.empty:
        st.info("Sem tempos de volta para esta corrida.")
        return
    available = [a for a in order if a in set(laps["acronym"])]
    chosen = st.multiselect(
        "Pilotos",
        available,
        default=available[:3],
        key=f"lap_drivers_{session_key}",
    )
    selected = laps.loc[laps["acronym"].isin(chosen)]
    if selected.empty:
        st.caption("Escolha ao menos um piloto.")
        return
    best = selected.loc[selected["lap_duration"].idxmin()]
    best_lap = format_lap(best["lap_duration"])
    st.caption(
        f"Volta mais rápida entre os selecionados: **{best_lap}** "
        f"({best['acronym']}, volta {int(best['lap_number'])})."
    )
    st.plotly_chart(
        charts.lap_times_chart(selected), config=PLOT_CONFIG, key=f"laps_{session_key}"
    )


def _tyres_tab(
    details: RaceDetails, data: SeasonData, session_key: int, order: Sequence[str]
) -> None:
    stints = tyre_stints(details.stints, data.drivers, session_key, order)
    if stints.empty:
        st.info("Sem dados de pneus para esta corrida.")
        return
    st.plotly_chart(
        charts.tyre_strategy_chart(stints),
        config=PLOT_CONFIG,
        key=f"tyres_{session_key}",
    )


def _pits_tab(details: RaceDetails, data: SeasonData, session_key: int) -> None:
    stops = pit_stops(details.pit_stops, data.drivers, session_key)
    if stops.empty:
        st.info("Sem pit stops registrados para esta corrida.")
        return
    timed = stops.dropna(subset=["stop_duration"])
    if not timed.empty:
        fastest = timed.loc[timed["stop_duration"].idxmin()]
        st.caption(
            f"Parada mais rápida: **{format_seconds(fastest['stop_duration'])} s** "
            f"({fastest['acronym']}, volta {int(fastest['lap_number'])}) · "
            f"{len(stops)} paradas no total."
        )
    _table(
        pit_stops_display(stops), stops["colour"].tolist(), key=f"pits_{session_key}"
    )


def _weather_tab(details: RaceDetails, session_key: int) -> None:
    weather = session_weather(details.weather, session_key)
    if weather.empty:
        st.info("Sem dados de clima para esta corrida.")
        return
    summary = weather_summary(weather)
    air, track, humidity, rain = st.columns(4)
    air.metric("Ar (média)", format_temperature(summary.air_avg))
    track.metric(
        "Pista (média)",
        format_temperature(summary.track_avg),
        help=(
            f"Mín. {format_temperature(summary.track_min)} · "
            f"máx. {format_temperature(summary.track_max)}"
        ),
    )
    humidity_text = (
        "—" if summary.humidity_avg is None else f"{summary.humidity_avg:.0f}%"
    )
    humidity.metric("Umidade (média)", humidity_text)
    rain.metric("Chuva", "Sim" if summary.rained else "Não")
    st.plotly_chart(
        charts.weather_chart(weather), config=PLOT_CONFIG, key=f"weather_{session_key}"
    )


def render_race_details(
    data_dir: Path, year: int, race: pd.Series, data: SeasonData
) -> None:
    """Detalhes da sessão escolhida.

    Corridas principais têm resultado, voltas, pneus, pit stops e clima; as
    demais sessões mostram só o resultado.
    """
    session_key = int(race["session_key"])
    meeting_key = int(race["meeting_key"])
    is_race = str(race.get("kind", RACE)) == RACE
    date = race["date_start"]
    when = date.strftime("%d/%m/%Y") if isinstance(date, datetime) else "—"
    title = f"Rodada {int(race['round'])} · {race['gp']}"
    if not is_race:
        title += f" · {session_label(race.get('session_name', ''))}"
    section(title, f"{when} · vencedor: {race['name']} ({race['team']})")
    classification = race_classification(data.results, data.drivers, session_key)
    tabs = st.tabs(list(DETAIL_TABS) if is_race else [DETAIL_TABS[0]])
    with tabs[0]:
        _table(
            classification_display(classification),
            classification["colour"].tolist(),
            key=f"result_{session_key}",
        )
    if not is_race:
        st.caption(
            "Tempos de volta, pneus, pit stops e clima estão disponíveis só para "
            "corridas principais."
        )
        return
    if not race_details_loaded(data_dir, year, meeting_key):
        try_load(bootstrap_race, data_dir, year, meeting_key)
    details = race_details(data_dir, year, meeting_key)
    order = classification["acronym"].tolist()
    with tabs[1]:
        _laps_tab(details, data, session_key, order)
    with tabs[2]:
        _tyres_tab(details, data, session_key, order)
    with tabs[3]:
        _pits_tab(details, data, session_key)
    with tabs[4]:
        _weather_tab(details, session_key)


def season_filter(filters: SeasonFilter) -> SeasonFilter:
    """Filtro da página: "Tipo de sessão" não se aplica (sempre corridas + sprints)."""
    return replace(filters, kinds=POINTS_KINDS)


def render_season() -> None:
    """Conteúdo da página "Temporada" (respeita os filtros da barra lateral).

    O filtro "Tipo de sessão" não se aplica aqui: pontos, vencedores e KPIs
    consideram sempre corridas e sprints.
    """
    data_dir = get_settings().data_dir
    filters = current_filters()
    year = filters.year
    _header(year)
    data = season_data(data_dir, year)
    view = season_view(
        data.results,
        data.sessions,
        data.meetings,
        data.drivers,
        season_filter(filters.season),
    )
    if view.all_winners.empty and view.standings.empty:
        st.info(f"Ainda não há resultados de corridas para {year}.")
        return
    st.markdown(
        f'<div class="f1-summary">{summary_html(view.kpis)}</div>',
        unsafe_allow_html=True,
    )
    _kpi_cards(view.kpis)
    selected = _season_section(view, year)
    target = selected if selected is not None else view.focus_row()
    if target is not None:
        render_race_details(data_dir, year, target, data)
