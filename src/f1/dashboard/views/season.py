"""Página "Temporada": painel analítico de uma temporada de F1.

Leitura e agregação ficam em ``f1.dashboard.loaders`` e
``f1.processing.standings``; cargas da API em ``f1.dashboard.bootstrap``. Este
módulo só compõe a tela.
"""

import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from f1.config.settings import get_settings
from f1.dashboard.bootstrap import (
    BOOTSTRAP_YEAR,
    FIRST_SEASON,
    BootstrapResult,
    run_race_details,
    run_season_bootstrap,
)
from f1.dashboard.loaders import (
    RaceDetails,
    SeasonData,
    load_race_details,
    load_season_data,
    race_details_loaded,
    season_is_loaded,
)
from f1.dashboard.views import charts
from f1.dashboard.views.formatting import (
    format_day_month,
    format_lap,
    format_points,
    format_result_time,
    format_seconds,
    format_status,
    format_temperature,
    summary_sentence,
)
from f1.dashboard.views.theme import kpi_card, section
from f1.domain.models import MeetingRef
from f1.ingestion.openf1_client import OpenF1AccessError, OpenF1Error
from f1.processing.standings import (
    SeasonKpis,
    driver_standings,
    lap_times,
    pit_stops,
    race_classification,
    race_winners,
    season_kpis,
    session_weather,
    tyre_stints,
    weather_summary,
)
from f1.quality.validation import DataQualityError

CACHE_TTL_SECONDS = 300
ROW_HEIGHT = 35
SQUARE = "■"
PLOT_CONFIG = {"displayModeBar": False}
DETAIL_TABS = (
    "Resultado final",
    "Tempos de volta",
    "Estratégia de pneus",
    "Pit stops",
    "Clima",
)
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


# --- cache ---------------------------------------------------------------


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def season_data(data_dir: Path, year: int) -> SeasonData:
    return load_season_data(data_dir, year)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def race_details(data_dir: Path, year: int, meeting_key: int) -> RaceDetails:
    return load_race_details(data_dir, year, meeting_key)


@st.cache_resource(show_spinner="Carregando dados da OpenF1...")
def bootstrap_season(data_dir: Path, year: int) -> BootstrapResult:
    """Carga da temporada, uma vez por processo; falhas não ficam em cache."""
    result = run_season_bootstrap(get_settings(), year)
    season_data.clear()
    return result


@st.cache_resource(show_spinner="Baixando voltas, pneus, pit stops e clima...")
def bootstrap_race(data_dir: Path, year: int, meeting_key: int) -> BootstrapResult:
    """Detalhes de uma corrida, uma vez por processo; falhas não ficam em cache."""
    meeting = MeetingRef(meeting_key=meeting_key, year=year, name="")
    result = run_race_details(get_settings(), meeting)
    race_details.clear()
    return result


def _try_load(loader: Callable[..., BootstrapResult], *args: object) -> bool:
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


# --- tabelas de exibição (puras) -----------------------------------------


def season_options(now: datetime) -> list[int]:
    """Temporadas disponíveis no seletor, da mais recente para a mais antiga."""
    return list(range(now.year, FIRST_SEASON - 1, -1))


def summary_html(kpis: SeasonKpis) -> str:
    """Frase-resumo em HTML, com os destaques em ``<strong>``."""
    sentence = escape(summary_sentence(kpis))
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", sentence)


def winners_display(winners: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Rod.": winners["round"].astype("Int64"),
            "GP": winners["gp"],
            "Data": [format_day_month(d) for d in winners["date_start"]],
            "Vencedor": winners["acronym"],
            "Cor": SQUARE,
            "Equipe": winners["team"],
        }
    )


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
            "Cor": SQUARE,
            "Equipe": classification["team"],
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
            "Cor": SQUARE,
            "Equipe": stops["team"],
            "Parada (s)": [format_seconds(v) for v in stops["stop_duration"]],
            "Pit lane (s)": [format_seconds(v) for v in stops["lane_duration"]],
        }
    )


# --- componentes -----------------------------------------------------------


def _coloured(
    display: pd.DataFrame, colours: Sequence[str]
) -> "pd.io.formats.style.Styler":
    """Pinta o quadradinho da coluna ``Cor`` com a cor da equipe."""
    styles = [f"color: {c}; font-size: 1.05rem" for c in colours]
    return display.style.apply(lambda _col: styles, subset=["Cor"])


def _table(  # noqa: PLR0913 - opções de exibição explícitas
    display: pd.DataFrame,
    colours: Sequence[str],
    *,
    key: str,
    selectable: bool = False,
    max_rows: int = 25,
    column_config: dict[str, object] | None = None,
) -> list[int]:
    """Tabela com quadradinho colorido; retorna as linhas selecionadas."""
    config: dict[str, object] = {"Cor": st.column_config.TextColumn("", width=36)}
    config.update(column_config or {})
    height = ROW_HEIGHT * (min(len(display), max_rows) + 1) + 3
    options: dict[str, object] = {
        "hide_index": True,
        "width": "stretch",
        "height": height,
        "key": key,
        "column_config": config,
    }
    if not selectable:
        st.dataframe(_coloured(display, colours), **options)  # type: ignore[call-overload]
        return []
    event = st.dataframe(  # type: ignore[call-overload]
        _coloured(display, colours),
        on_select="rerun",
        selection_mode="single-row",
        **options,
    )
    selection = getattr(event, "selection", None)
    return [int(r) for r in getattr(selection, "rows", [])]


def _header() -> int:
    title_col, select_col = st.columns([5, 1], vertical_alignment="bottom")
    options = season_options(datetime.now(UTC))
    default = options.index(BOOTSTRAP_YEAR) if BOOTSTRAP_YEAR in options else 0
    with select_col:
        year = int(st.selectbox("Temporada", options, index=default, key="season_year"))
    with title_col:
        title = f"Fórmula 1 · temporada {year}"
        st.markdown(f'<div class="f1-title">{title}</div>', unsafe_allow_html=True)
    return year


def _kpi_cards(kpis: SeasonKpis) -> None:
    cards = (
        ("Corridas", str(kpis.races), "Grandes Prêmios da temporada"),
        ("Sprints", str(kpis.sprints), "Corridas curtas de sábado"),
        (
            "Vencedores diferentes",
            str(kpis.distinct_winners),
            "Em corridas, sem contar sprints",
        ),
        ("Pontos do líder", format_points(kpis.leader_points), "Corridas + sprints"),
    )
    for column, (label, value, caption) in zip(st.columns(4), cards, strict=True):
        column.markdown(kpi_card(label, value, caption), unsafe_allow_html=True)


def _season_section(
    standings: pd.DataFrame, winners: pd.DataFrame, year: int
) -> pd.Series | None:
    section("Temporada")
    left, right = st.columns([1.05, 1], gap="large")
    with left:
        st.markdown("#### Pontos por piloto")
        st.caption(
            "Soma dos pontos de corridas e sprints "
            "(inclui o ponto da volta mais rápida)."
        )
        st.plotly_chart(
            charts.points_bar(standings), config=PLOT_CONFIG, key=f"points_{year}"
        )
    with right:
        st.markdown("#### Vencedores por corrida")
        st.caption("Clique em uma corrida para ver os detalhes abaixo.")
        rows = _table(
            winners_display(winners),
            winners["colour"].tolist(),
            key=f"winners_{year}",
            selectable=True,
            column_config={"Rod.": st.column_config.NumberColumn(width=56)},
        )
    return winners.iloc[rows[0]] if rows else None


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
            f"Parada mais rápida: **{float(fastest['stop_duration']):.1f} s** "
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
    """Detalhes da corrida selecionada: resultado, voltas, pneus, pits e clima."""
    session_key = int(race["session_key"])
    meeting_key = int(race["meeting_key"])
    date = race["date_start"]
    when = date.strftime("%d/%m/%Y") if isinstance(date, datetime) else "—"
    section(
        f"Rodada {int(race['round'])} · {race['gp']}",
        f"{when} · vencedor: {race['name']} ({race['team']})",
    )
    classification = race_classification(data.results, data.drivers, session_key)
    order = classification["acronym"].tolist()
    tabs = st.tabs(list(DETAIL_TABS))
    with tabs[0]:
        _table(
            classification_display(classification),
            classification["colour"].tolist(),
            key=f"result_{session_key}",
        )
    if not race_details_loaded(data_dir, year, meeting_key):
        _try_load(bootstrap_race, data_dir, year, meeting_key)
    details = race_details(data_dir, year, meeting_key)
    with tabs[1]:
        _laps_tab(details, data, session_key, order)
    with tabs[2]:
        _tyres_tab(details, data, session_key, order)
    with tabs[3]:
        _pits_tab(details, data, session_key)
    with tabs[4]:
        _weather_tab(details, session_key)


def render_season() -> None:
    """Conteúdo da página "Temporada"."""
    data_dir = get_settings().data_dir
    year = _header()
    if not season_is_loaded(data_dir, year):
        _try_load(bootstrap_season, data_dir, year)
    data = season_data(data_dir, year)
    standings = driver_standings(data.results, data.sessions, data.drivers)
    if standings.empty:
        st.info(f"Ainda não há resultados de corridas para {year}.")
        return
    winners = race_winners(data.results, data.sessions, data.meetings, data.drivers)
    kpis = season_kpis(data.results, data.sessions, standings)
    st.markdown(
        f'<div class="f1-summary">{summary_html(kpis)}</div>', unsafe_allow_html=True
    )
    _kpi_cards(kpis)
    race = _season_section(standings, winners, year)
    if race is not None:
        render_race_details(data_dir, year, race, data)
