"""Página "Última corrida": a corrida mais recente já concluída.

Não usa o filtro de temporada: procura no ano atual (e, no início do ano, no
anterior). Resultados são atualizados no máximo a cada ``LATEST_TTL_SECONDS``;
se a última corrida ainda não tiver resultados (acabou de terminar) ou a
OpenF1 estiver indisponível, mostra a corrida anterior com um aviso.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from f1.config.settings import get_settings
from f1.dashboard.loaders import SeasonData
from f1.dashboard.views.data import (
    ACCESS_DENIED_MESSAGE,
    ensure_grid,
    ensure_laps,
    ensure_season,
    grid_data,
    kinds_key,
    race_details,
    refresh_bucket,
    refresh_results,
    season_data,
)
from f1.dashboard.views.formatting import (
    change_style,
    format_change,
    format_finish,
    format_lap,
    format_points,
    status_code,
)
from f1.dashboard.views.sidebar import LATEST_PAGE, show_locked_season
from f1.dashboard.views.tables import TEAM_COLUMN, render_table, team_label
from f1.dashboard.views.theme import kpi_card, podium_card, section
from f1.domain.models import POINTS_KINDS
from f1.processing.fastest_laps import fastest_laps
from f1.processing.last_race import (
    RaceChoice,
    championship_after,
    choose_last_race,
    classification_with_grid,
    race_grid,
    race_highlights,
)
from f1.processing.standings import race_schedule, result_kinds

PODIUM_PLACES = ("1º", "2º", "3º")


@dataclass(frozen=True)
class LatestRace:
    year: int
    data: SeasonData
    choice: RaceChoice
    race: pd.Series  # corrida exibida (sempre com resultados)
    pending_name: str | None  # GP cujos resultados ainda não saíram
    access_denied: bool = False


def _meeting(data: SeasonData, meeting_key: int) -> pd.Series:
    rows = data.meetings.loc[data.meetings["meeting_key"] == meeting_key]
    return rows.iloc[0] if not rows.empty else pd.Series(dtype=object)


def meeting_name(data: SeasonData, meeting_key: int) -> str:
    """Nome do GP (ex.: ``"São Paulo Grand Prix"``)."""
    meeting = _meeting(data, meeting_key)
    return str(meeting.get("meeting_name") or meeting.get("country_name") or "—")


def find_latest_race(data_dir: Path, now: datetime) -> LatestRace | None:
    """Escolhe a corrida a exibir no ano atual (ou no anterior, se preciso)."""
    pending: str | None = None
    access_denied = False
    for year in (now.year, now.year - 1):
        ensure_season(data_dir, year, POINTS_KINDS)
        data = season_data(data_dir, year)
        choice = choose_last_race(data.sessions, data.results, now)
        if choice.results_pending:
            kinds = result_kinds(data.results, data.sessions) | set(POINTS_KINDS)
            outcome = refresh_results(
                data_dir, year, kinds_key(kinds), refresh_bucket(now)
            )
            access_denied = access_denied or outcome.access_denied
            data = season_data(data_dir, year)
            choice = choose_last_race(data.sessions, data.results, now)
        if choice.results_pending and pending is None and choice.latest is not None:
            pending = meeting_name(data, int(choice.latest["meeting_key"]))
        if choice.shown is not None:
            return LatestRace(year, data, choice, choice.shown, pending, access_denied)
    return None


def classification_display(table: pd.DataFrame) -> pd.DataFrame:
    rows = table.to_dict("records")
    return pd.DataFrame(
        {
            "Pos.": [
                "NC" if pd.isna(r["position"]) else str(int(r["position"]))
                for r in rows
            ],
            "Piloto": table["name"],
            TEAM_COLUMN: [team_label(t) for t in table["team"]],
            "Largada": ["—" if pd.isna(g) else str(int(g)) for g in table["grid"]],
            "Posições": [format_change(g) for g in table["gained"]],
            "Tempo / diferença": [
                format_finish(r["position"], r["duration"], r["gap_to_leader"])
                for r in rows
            ],
            "Pontos": [
                format_points(0.0 if pd.isna(r["points"]) else float(r["points"]))
                for r in rows
            ],
            "Situação": [status_code(r["dnf"], r["dns"], r["dsq"]) for r in rows],
        }
    )


def championship_display(table: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Pos.": table["position"],
            "Piloto": table["name"],
            TEAM_COLUMN: [team_label(t) for t in table["team"]],
            "Pontos": [format_points(float(p)) for p in table["points"]],
            "Variação": [format_change(c) for c in table["change"]],
        }
    )


def _header(latest: LatestRace, race: pd.Series) -> None:
    meeting = _meeting(latest.data, int(race["meeting_key"]))
    gp = meeting_name(latest.data, int(race["meeting_key"]))
    circuit = meeting.get("circuit_short_name") or meeting.get("location") or "—"
    country = meeting.get("country_name") or "—"
    title = f"{gp} · {circuit}, {country}"
    st.markdown(f'<div class="f1-title">{title}</div>', unsafe_allow_html=True)
    date = race["date_start"]
    when = date.strftime("%d/%m/%Y") if isinstance(date, datetime) else "—"
    st.markdown(f'<div class="f1-date">{when}</div>', unsafe_allow_html=True)
    total = race_schedule(latest.data.sessions, datetime.now(UTC)).scheduled
    st.caption(f"Rodada {int(race['round'])} de {total} · temporada {latest.year}")


def _podium(table: pd.DataFrame) -> None:
    top = table.loc[table["position"].isin([1, 2, 3])].head(3)
    for column, place, row in zip(
        st.columns(3), PODIUM_PLACES, top.to_dict("records"), strict=False
    ):
        time = format_finish(row["position"], row["duration"], row["gap_to_leader"])
        column.markdown(
            podium_card(
                place, str(row["name"]), str(row["team"]), str(row["colour"]), time
            ),
            unsafe_allow_html=True,
        )


def _highlights(table: pd.DataFrame, fastest: pd.DataFrame) -> None:
    facts = race_highlights(table, fastest)
    fastest_value = (
        "—" if facts.fastest_time is None else format_lap(facts.fastest_time)
    )
    fastest_caption = (
        "Sem tempos de volta"
        if facts.fastest_name is None
        else f"{facts.fastest_name} · volta {facts.fastest_lap}"
    )
    gain_value = "—" if facts.top_gain is None else format_change(facts.top_gain)
    gain_caption = facts.top_gainer_name or "Ninguém ganhou posições"
    cards = (
        ("Volta mais rápida", fastest_value, fastest_caption),
        ("Mais posições ganhas", gain_value, gain_caption),
        ("Abandonos", str(facts.retirements), "DNF na corrida"),
    )
    for column, (label, value, caption) in zip(st.columns(3), cards, strict=True):
        column.markdown(kpi_card(label, value, caption), unsafe_allow_html=True)


def render_latest() -> None:
    """Conteúdo da página "Última corrida"."""
    data_dir = get_settings().data_dir
    now = datetime.now(UTC)
    latest = find_latest_race(data_dir, now)
    note = LATEST_PAGE.season_note
    if latest is None:
        show_locked_season(now.year, note)
        st.info("Ainda não há corridas concluídas com resultados disponíveis.")
        return
    show_locked_season(latest.year, note)
    if latest.pending_name:
        message = f"Resultados de {latest.pending_name} ainda não disponíveis"
        detail = (
            ACCESS_DENIED_MESSAGE
            if latest.access_denied
            else "A corrida terminou há pouco; os resultados aparecem assim que a "
            "OpenF1 publicar. Mostrando a corrida anterior."
        )
        st.warning(f"**{message}.** {detail}")
    race = latest.race
    year, meeting_key = latest.year, int(race["meeting_key"])
    session_key = int(race["session_key"])
    _header(latest, race)

    ensure_grid(data_dir, year, meeting_key, now)
    grid = race_grid(
        grid_data(data_dir, year, meeting_key), latest.data.sessions, meeting_key
    )
    table = classification_with_grid(
        latest.data.results, latest.data.drivers, grid, session_key
    )
    ensure_laps(data_dir, year, meeting_key, [session_key])
    fastest = fastest_laps(
        race_details(data_dir, year, meeting_key).laps,
        latest.data.drivers,
        latest.data.sessions,
        session_keys=[session_key],
        top=1,
    )

    section("Pódio")
    _podium(table)
    section("Destaques")
    _highlights(table, fastest)
    section("Classificação")
    render_table(
        classification_display(table),
        table["colour"].tolist(),
        key=f"latest_result_{session_key}",
        column_styles={"Posições": [change_style(g) for g in table["gained"]]},
    )
    section(
        "Campeonato", "Top 5 de pilotos após esta corrida, com a variação de posição."
    )
    standings = championship_after(
        latest.data.results,
        latest.data.sessions,
        latest.data.drivers,
        int(race["round"]),
    )
    render_table(
        championship_display(standings),
        standings["colour"].tolist(),
        key=f"latest_championship_{session_key}",
        column_styles={"Variação": [change_style(c) for c in standings["change"]]},
    )
