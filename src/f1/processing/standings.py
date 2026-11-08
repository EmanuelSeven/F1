"""Agregações analíticas da temporada (funções puras sobre DataFrames silver).

Entradas são os datasets silver ``meetings``, ``sessions``, ``drivers`` e
``session_results`` (ou os datasets de volta da corrida). Pontos vêm da coluna
``points`` da OpenF1, que já inclui o ponto da volta mais rápida.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from f1.domain.models import RACE_SESSION, SPRINT_SESSION

RACE = "race"
SPRINT = "sprint"
FALLBACK_COLOUR = "#9CA3AF"
SLOW_LAP_FACTOR = 1.15
PODIUM = 3

_DRIVER_COLUMNS = ["session_key", "driver_number", "acronym", "name", "team", "colour"]


@dataclass(frozen=True)
class SeasonKpis:
    races: int
    sprints: int
    distinct_winners: int
    leader_name: str | None
    leader_acronym: str | None
    leader_points: float


@dataclass(frozen=True)
class WeatherSummary:
    air_avg: float | None
    track_avg: float | None
    track_min: float | None
    track_max: float | None
    humidity_avg: float | None
    rained: bool


def team_colour(value: object) -> str:
    """Cor da equipe no formato ``#RRGGBB`` (cinza quando ausente)."""
    if isinstance(value, str) and len(value.strip()) == 6:  # noqa: PLR2004 - RRGGBB
        return f"#{value.strip().upper()}"
    return FALLBACK_COLOUR


def points_sessions(sessions: pd.DataFrame) -> pd.DataFrame:
    """Corridas e sprints não canceladas, em ordem cronológica, com a rodada.

    A rodada (``round``) numera as corridas principais; a sprint herda a rodada
    do seu fim de semana.
    """
    cancelled = sessions["is_cancelled"].fillna(False).astype(bool)
    mask = sessions["session_name"].isin([RACE_SESSION, SPRINT_SESSION]) & ~cancelled
    df = sessions.loc[mask].sort_values("date_start", kind="stable").copy()
    df["kind"] = df["session_name"].map({RACE_SESSION: RACE, SPRINT_SESSION: SPRINT})
    races = df.loc[df["kind"] == RACE, "meeting_key"].drop_duplicates()
    rounds = {int(key): n for n, key in enumerate(races, start=1)}
    df["round"] = df["meeting_key"].map(rounds).astype("Int64")
    columns = ["session_key", "meeting_key", "session_name", "kind", "round"]
    return df[[*columns, "date_start"]].reset_index(drop=True)


def driver_acronyms(drivers: pd.DataFrame) -> pd.Series:
    """Sigla de 3 letras de cada piloto (ex.: ``LAW``).

    Usa ``name_acronym`` normalizado (sem espaços, em maiúsculas); se vier vazio,
    as 3 primeiras letras do sobrenome; em último caso, o número do piloto.
    """
    acronym = drivers["name_acronym"].astype("string").str.strip().str.upper()
    from_last = drivers["last_name"].astype("string").str.strip().str[:3].str.upper()
    number = drivers["driver_number"].astype("string")
    filled = acronym.mask(acronym == "").fillna(from_last.mask(from_last == ""))
    return filled.fillna(number).astype(str)


def driver_info(drivers: pd.DataFrame) -> pd.DataFrame:
    """Sigla, nome, equipe e cor por ``(session_key, driver_number)``."""
    first = drivers["first_name"].fillna("")
    last = drivers["last_name"].fillna("")
    full = (first + " " + last).str.strip()
    fallback = drivers["full_name"].fillna(drivers["driver_number"].astype("string"))
    out = pd.DataFrame(
        {
            "session_key": drivers["session_key"],
            "driver_number": drivers["driver_number"],
            "acronym": driver_acronyms(drivers),
            "name": full.where(full != "", fallback).astype(str),
            "team": drivers["team_name"].fillna("—").astype(str),
            "colour": [team_colour(v) for v in drivers["team_colour"]],
        }
    )
    return out.drop_duplicates(["session_key", "driver_number"], keep="last")


def driver_directory(drivers: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    """Um registro por piloto, com os dados da sessão mais recente."""
    info = driver_info(drivers).merge(
        sessions[["session_key", "date_start"]], on="session_key", how="left"
    )
    info = info.sort_values("date_start", kind="stable", na_position="first")
    latest = info.groupby("driver_number", sort=False).tail(1)
    return latest[_DRIVER_COLUMNS[1:]].reset_index(drop=True)


def scored_results(results: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    """Resultados de corridas e sprints com ``kind``, ``round`` e pontos."""
    scored = results.merge(points_sessions(sessions), on="session_key", how="inner")
    scored["points"] = scored["points"].astype("Float64").fillna(0.0)
    in_race = scored["kind"] == RACE
    position = scored["position"]
    scored["is_win"] = (in_race & (position == 1)).fillna(False).astype(bool)
    is_podium = in_race & (position >= 1) & (position <= PODIUM)
    scored["is_podium"] = is_podium.fillna(False).astype(bool)
    return scored


def driver_standings(
    results: pd.DataFrame, sessions: pd.DataFrame, drivers: pd.DataFrame
) -> pd.DataFrame:
    """Classificação de pilotos: pontos (corridas + sprints), vitórias e pódios."""
    scored = scored_results(results, sessions)
    totals = scored.groupby("driver_number", as_index=False).agg(
        points=("points", "sum"), wins=("is_win", "sum"), podiums=("is_podium", "sum")
    )
    table = totals.merge(
        driver_directory(drivers, sessions), on="driver_number", how="left"
    )
    number = table["driver_number"].astype(str)
    table["acronym"] = table["acronym"].fillna(number)
    table["name"] = table["name"].fillna(number)
    table["team"] = table["team"].fillna("—")
    table["colour"] = table["colour"].fillna(FALLBACK_COLOUR)
    table["points"] = table["points"].astype(float)
    table[["wins", "podiums"]] = table[["wins", "podiums"]].astype(int)
    table = table.sort_values(
        ["points", "wins", "podiums", "acronym"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    table.insert(0, "position", range(1, len(table) + 1))
    columns = ["acronym", "name", "team", "colour", "points", "wins", "podiums"]
    return table[["position", "driver_number", *columns]]


def race_winners(
    results: pd.DataFrame,
    sessions: pd.DataFrame,
    meetings: pd.DataFrame,
    drivers: pd.DataFrame,
) -> pd.DataFrame:
    """Vencedor de cada corrida principal já disputada, por rodada."""
    races = points_sessions(sessions)
    races = races.loc[races["kind"] == RACE]
    winners = results.loc[results["position"] == 1, ["session_key", "driver_number"]]
    df = races.merge(winners, on="session_key", how="inner")
    df = df.merge(
        meetings[["meeting_key", "meeting_name", "country_name"]],
        on="meeting_key",
        how="left",
    )
    df = df.merge(driver_info(drivers), on=["session_key", "driver_number"], how="left")
    name = df["meeting_name"].fillna(df["country_name"]).fillna("—").astype(str)
    df["gp"] = name.str.replace(r"\s*Grand Prix$", "", regex=True)
    df["acronym"] = df["acronym"].fillna(df["driver_number"].astype(str))
    df["team"] = df["team"].fillna("—")
    df["colour"] = df["colour"].fillna(FALLBACK_COLOUR)
    df = df.sort_values("round", kind="stable").reset_index(drop=True)
    columns = ["round", "meeting_key", "session_key", "gp", "date_start"]
    return df[[*columns, "driver_number", "acronym", "name", "team", "colour"]]


def season_kpis(
    results: pd.DataFrame, sessions: pd.DataFrame, standings: pd.DataFrame
) -> SeasonKpis:
    """Indicadores da temporada a partir das sessões com resultado."""
    scored = scored_results(results, sessions)
    kinds = scored.drop_duplicates("session_key")["kind"]
    winners = scored.loc[scored["is_win"], "driver_number"]
    has_leader = not standings.empty and float(standings["points"].iloc[0]) > 0
    leader = standings.iloc[0] if has_leader else None
    return SeasonKpis(
        races=int((kinds == RACE).sum()),
        sprints=int((kinds == SPRINT).sum()),
        distinct_winners=int(winners.nunique()),
        leader_name=str(leader["name"]) if leader is not None else None,
        leader_acronym=str(leader["acronym"]) if leader is not None else None,
        leader_points=float(leader["points"]) if leader is not None else 0.0,
    )


def race_classification(
    results: pd.DataFrame, drivers: pd.DataFrame, session_key: int
) -> pd.DataFrame:
    """Resultado final de uma sessão, com dados do piloto naquela sessão."""
    rows = results.loc[results["session_key"] == session_key]
    df = rows.merge(
        driver_info(drivers), on=["session_key", "driver_number"], how="left"
    )
    df["acronym"] = df["acronym"].fillna(df["driver_number"].astype(str))
    df["team"] = df["team"].fillna("—")
    df["colour"] = df["colour"].fillna(FALLBACK_COLOUR)
    df = df.sort_values(
        ["position", "number_of_laps"],
        ascending=[True, False],
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)
    columns = ["position", "driver_number", "acronym", "name", "team", "colour"]
    extra = ["number_of_laps", "duration", "gap_to_leader", "points", "dnf", "dns"]
    return df[[*columns, *extra, "dsq"]]


def _with_driver(
    frame: pd.DataFrame, drivers: pd.DataFrame, session_key: int
) -> pd.DataFrame:
    rows = frame.loc[frame["session_key"] == session_key]
    df = rows.merge(
        driver_info(drivers), on=["session_key", "driver_number"], how="left"
    )
    df["acronym"] = df["acronym"].fillna(df["driver_number"].astype(str))
    df["colour"] = df["colour"].fillna(FALLBACK_COLOUR)
    return df


def lap_times(
    laps: pd.DataFrame,
    drivers: pd.DataFrame,
    session_key: int,
    *,
    exclude_slow: bool = True,
) -> pd.DataFrame:
    """Tempos de volta válidos de uma sessão.

    Com ``exclude_slow``, remove a volta 1, voltas de saída do box e voltas acima
    de ``SLOW_LAP_FACTOR`` x a mediana (safety car, entrada no box).
    """
    df = _with_driver(laps, drivers, session_key)
    df = df.loc[df["lap_duration"].notna()]
    if exclude_slow and not df.empty:
        out_lap = df["is_pit_out_lap"].fillna(False).astype(bool)
        limit = float(df["lap_duration"].median()) * SLOW_LAP_FACTOR
        keep = (df["lap_number"] > 1) & ~out_lap & (df["lap_duration"] <= limit)
        df = df.loc[keep]
    df = df.sort_values(["driver_number", "lap_number"], kind="stable")
    columns = ["driver_number", "acronym", "colour", "lap_number", "lap_duration"]
    return df[columns].reset_index(drop=True)


def tyre_stints(
    stints: pd.DataFrame,
    drivers: pd.DataFrame,
    session_key: int,
    order: Sequence[str] = (),
) -> pd.DataFrame:
    """Stints por piloto, na ordem de ``order`` (siglas) quando informada."""
    df = _with_driver(stints, drivers, session_key)
    df = df.loc[df["lap_start"].notna() & df["lap_end"].notna()].copy()
    df["compound"] = df["compound"].fillna("UNKNOWN")
    df["laps"] = (df["lap_end"] - df["lap_start"] + 1).astype("Int64")
    rank = {acronym: n for n, acronym in enumerate(order)}
    df["_order"] = df["acronym"].map(rank).fillna(len(rank))
    df = df.sort_values(["_order", "acronym", "stint_number"], kind="stable")
    columns = ["driver_number", "acronym", "stint_number", "compound", "lap_start"]
    return df[[*columns, "lap_end", "laps", "tyre_age_at_start"]].reset_index(drop=True)


def pit_stops(
    pits: pd.DataFrame, drivers: pd.DataFrame, session_key: int
) -> pd.DataFrame:
    """Pit stops de uma sessão, em ordem de volta."""
    df = _with_driver(pits, drivers, session_key)
    df["team"] = df["team"].fillna("—")
    df = df.sort_values(["lap_number", "acronym"], kind="stable")
    columns = ["lap_number", "driver_number", "acronym", "team", "colour"]
    return df[[*columns, "stop_duration", "lane_duration"]].reset_index(drop=True)


def session_weather(weather: pd.DataFrame, session_key: int) -> pd.DataFrame:
    """Leituras de clima de uma sessão, em ordem temporal."""
    df = weather.loc[weather["session_key"] == session_key]
    return df.sort_values("date", kind="stable").reset_index(drop=True)


def weather_summary(weather: pd.DataFrame) -> WeatherSummary:
    """Médias e extremos de temperatura e se choveu."""

    def _stat(column: str, func: str) -> float | None:
        values = weather[column].dropna() if column in weather else pd.Series()
        return None if values.empty else round(float(values.agg(func)), 1)

    rained = bool(weather["rainfall"].fillna(False).astype(bool).any())
    return WeatherSummary(
        air_avg=_stat("air_temperature", "mean"),
        track_avg=_stat("track_temperature", "mean"),
        track_min=_stat("track_temperature", "min"),
        track_max=_stat("track_temperature", "max"),
        humidity_avg=_stat("humidity", "mean"),
        rained=rained,
    )
