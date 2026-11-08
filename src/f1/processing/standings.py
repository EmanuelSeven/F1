"""Agregações analíticas da temporada (funções puras sobre DataFrames silver).

Entradas são os datasets silver ``meetings``, ``sessions``, ``drivers`` e
``session_results`` (ou os datasets de volta da corrida). Pontos vêm da coluna
``points`` da OpenF1, que já inclui o ponto da volta mais rápida.

``kinds`` escolhe os tipos de sessão analisados (padrão: corridas e sprints).
Pontos somam todos os tipos escolhidos; vencedores, vitórias e pódios usam os
"tipos principais" (``primary_kinds``): a corrida, se escolhida, senão os
próprios tipos (ex.: só classificação → poles).
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from f1.domain.models import (
    POINTS_KINDS,
    SessionKind,
    classify_session,
    primary_kinds,
)

RACE = SessionKind.RACE.value
SPRINT = SessionKind.SPRINT.value
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
    events: int = 0  # sessões principais com vencedor
    events_won: int = 0  # dessas, vencidas por pilotos da seleção
    filtered: bool = False  # seleção restrita por equipe/piloto
    primary: tuple[SessionKind, ...] = (SessionKind.RACE,)
    points_kinds: tuple[SessionKind, ...] = POINTS_KINDS
    scheduled_races: int = 0  # corridas principais no calendário
    upcoming_races: int = 0  # dessas, ainda não largaram

    @property
    def in_progress(self) -> bool:
        """Há corridas futuras no calendário (temporada em andamento)."""
        return self.upcoming_races > 0


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


def classified_sessions(sessions: pd.DataFrame) -> pd.DataFrame:
    """Sessões de fins de semana de GP, com ``kind`` e ``round``, em ordem.

    Exclui sessões canceladas, sem categoria e de meetings sem corrida (ex.:
    testes de pré-temporada). ``round`` numera as corridas principais; as demais
    sessões herdam a rodada do seu fim de semana.
    """
    cancelled = sessions["is_cancelled"].fillna(False).astype(bool)
    df = sessions.loc[~cancelled].sort_values("date_start", kind="stable").copy()
    df["kind"] = [
        k.value if k is not None else None
        for k in map(classify_session, df["session_name"], df["session_type"])
    ]
    races = df.loc[df["kind"] == RACE, "meeting_key"].drop_duplicates()
    rounds = {int(key): n for n, key in enumerate(races, start=1)}
    df["round"] = df["meeting_key"].map(rounds).astype("Int64")
    df = df.loc[df["kind"].notna() & df["round"].notna()]
    columns = ["session_key", "meeting_key", "session_name", "kind", "round"]
    return df[[*columns, "date_start"]].reset_index(drop=True)


@dataclass(frozen=True)
class RaceSchedule:
    scheduled: int
    upcoming: int


def race_schedule(sessions: pd.DataFrame, now: datetime) -> RaceSchedule:
    """Corridas principais previstas no calendário e quantas ainda não largaram."""
    races = points_sessions(sessions, (SessionKind.RACE,))
    starts = pd.to_datetime(races["date_start"], utc=True)
    upcoming = starts.isna() | (starts > pd.Timestamp(now))
    return RaceSchedule(scheduled=len(races), upcoming=int(upcoming.sum()))


def points_sessions(
    sessions: pd.DataFrame, kinds: Sequence[SessionKind] = POINTS_KINDS
) -> pd.DataFrame:
    """Sessões dos tipos ``kinds`` (padrão: corridas e sprints), com a rodada."""
    df = classified_sessions(sessions)
    return df.loc[df["kind"].isin([k.value for k in kinds])].reset_index(drop=True)


def result_kinds(results: pd.DataFrame, sessions: pd.DataFrame) -> set[SessionKind]:
    """Tipos de sessão que já têm resultados no lake."""
    keys = set(results["session_key"].dropna().astype(int))
    df = classified_sessions(sessions)
    return {SessionKind(k) for k in df.loc[df["session_key"].isin(keys), "kind"]}


def finished_kinds(sessions: pd.DataFrame, now: datetime) -> set[SessionKind]:
    """Tipos de sessão com ao menos uma sessão já encerrada no calendário.

    Ex.: numa temporada sem sprints, ``SPRINT`` nunca aparece, e portanto não
    há resultados de sprint a buscar.
    """
    df = classified_sessions(sessions)
    ends = sessions.set_index("session_key")["date_end"].fillna(
        sessions.set_index("session_key")["date_start"]
    )
    end = pd.to_datetime(df["session_key"].map(ends), utc=True)
    done = df.loc[(end <= pd.Timestamp(now)).fillna(False)]
    return {SessionKind(k) for k in done["kind"]}


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


def driver_identity(info: pd.DataFrame) -> pd.Series:
    """Chave do piloto: o nome (um piloto pode usar números diferentes no ano).

    Ex.: em 2024 Oliver Bearman correu com o #38 (Ferrari) e o #50 (Haas).
    """
    number = info["driver_number"].astype("string")
    name = info["name"].astype("string").str.strip().str.upper()
    return name.mask(name == "").fillna(number).astype(str)


def _numbers_by_identity(info: pd.DataFrame) -> dict[str, frozenset[int]]:
    groups: dict[str, set[int]] = {}
    for identity, number in zip(info["identity"], info["driver_number"], strict=True):
        if pd.notna(number):
            groups.setdefault(str(identity), set()).add(int(number))
    return {key: frozenset(numbers) for key, numbers in groups.items()}


def driver_numbers(drivers: pd.DataFrame) -> dict[int, frozenset[int]]:
    """Para cada número de carro, todos os números usados pelo mesmo piloto."""
    info = driver_info(drivers)
    info["identity"] = driver_identity(info)
    by_identity = _numbers_by_identity(info)
    return {
        number: by_identity[key] for key in by_identity for number in by_identity[key]
    }


def driver_directory(drivers: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    """Um registro por piloto, com os dados da sessão mais recente.

    ``driver_number`` é o número mais recente; ``driver_numbers``, todos os
    números usados pelo piloto na temporada.
    """
    info = driver_info(drivers).merge(
        sessions[["session_key", "date_start"]], on="session_key", how="left"
    )
    info["identity"] = driver_identity(info)
    numbers = {k: tuple(sorted(v)) for k, v in _numbers_by_identity(info).items()}
    info = info.sort_values("date_start", kind="stable", na_position="first")
    latest = info.groupby("identity", sort=False).tail(1).copy()
    latest["driver_numbers"] = latest["identity"].map(numbers)
    columns = [*_DRIVER_COLUMNS[1:], "driver_numbers", "identity"]
    return latest[columns].reset_index(drop=True)


def scored_results(
    results: pd.DataFrame,
    sessions: pd.DataFrame,
    kinds: Sequence[SessionKind] = POINTS_KINDS,
) -> pd.DataFrame:
    """Resultados dos tipos ``kinds`` com ``kind``, ``round``, pontos e vitórias.

    ``is_win``/``is_podium`` valem só para os tipos principais (``primary_kinds``).
    """
    scored = results.merge(points_sessions(sessions, kinds), on="session_key")
    scored["points"] = scored["points"].astype("Float64").fillna(0.0)
    primary = [k.value for k in primary_kinds(tuple(kinds))]
    in_primary = scored["kind"].isin(primary)
    position = scored["position"]
    scored["is_win"] = (in_primary & (position == 1)).fillna(False).astype(bool)
    is_podium = in_primary & (position >= 1) & (position <= PODIUM)
    scored["is_podium"] = is_podium.fillna(False).astype(bool)
    return scored


def driver_standings(
    results: pd.DataFrame,
    sessions: pd.DataFrame,
    drivers: pd.DataFrame,
    kinds: Sequence[SessionKind] = POINTS_KINDS,
) -> pd.DataFrame:
    """Classificação de pilotos: pontos dos ``kinds``, vitórias e pódios.

    Uma linha por piloto, mesmo que ele tenha usado mais de um número no ano.
    """
    scored = scored_results(results, sessions, kinds)
    info = driver_info(drivers)
    info["identity"] = driver_identity(info)
    scored = scored.merge(
        info[["session_key", "driver_number", "identity"]],
        on=["session_key", "driver_number"],
        how="left",
    )
    scored["identity"] = scored["identity"].fillna(scored["driver_number"].astype(str))
    totals = scored.groupby("identity", as_index=False).agg(
        points=("points", "sum"),
        wins=("is_win", "sum"),
        podiums=("is_podium", "sum"),
        scored_number=("driver_number", "last"),
    )
    directory = driver_directory(drivers, sessions)
    table = totals.merge(directory, on="identity", how="left")
    number = table["scored_number"].astype(int)
    table["driver_number"] = table["driver_number"].fillna(number).astype(int)
    table["driver_numbers"] = [
        ns if isinstance(ns, tuple) else (int(n),)
        for ns, n in zip(table["driver_numbers"], number, strict=True)
    ]
    table["acronym"] = table["acronym"].fillna(number.astype(str))
    table["name"] = table["name"].fillna(number.astype(str))
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
    return table[["position", "driver_number", *columns, "driver_numbers"]]


def race_winners(
    results: pd.DataFrame,
    sessions: pd.DataFrame,
    meetings: pd.DataFrame,
    drivers: pd.DataFrame,
    kinds: Sequence[SessionKind] = POINTS_KINDS,
) -> pd.DataFrame:
    """Vencedor (1º colocado) de cada sessão principal já disputada.

    Com os tipos padrão, são as corridas principais (uma por rodada).
    """
    events = points_sessions(sessions, primary_kinds(tuple(kinds)))
    winners = results.loc[results["position"] == 1, ["session_key", "driver_number"]]
    df = events.merge(winners, on="session_key", how="inner")
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
    df = df.sort_values(["round", "date_start"], kind="stable").reset_index(drop=True)
    columns = ["round", "meeting_key", "session_key", "gp", "date_start"]
    driver = ["driver_number", "acronym", "name", "team", "colour"]
    return df[[*columns, *driver, "session_name", "kind"]]


def season_kpis(
    results: pd.DataFrame,
    sessions: pd.DataFrame,
    standings: pd.DataFrame,
    kinds: Sequence[SessionKind] = POINTS_KINDS,
    allowed: Collection[int] | None = None,
) -> SeasonKpis:
    """Indicadores da seleção.

    ``standings`` já deve estar filtrada; ``allowed`` (números de piloto)
    restringe os vencedores contados.
    """
    selected = tuple(kinds)
    scored = scored_results(results, sessions, selected)
    session_kinds = scored.drop_duplicates("session_key")["kind"]
    wins = scored.loc[scored["is_win"]]
    events = int(wins["session_key"].nunique())
    if allowed is not None:
        wins = wins.loc[wins["driver_number"].isin(list(allowed))]
    points_kinds = tuple(k for k in selected if k in POINTS_KINDS)
    has_leader = (
        bool(points_kinds)
        and not standings.empty
        and float(standings["points"].iloc[0]) > 0
    )
    leader = standings.iloc[0] if has_leader else None
    return SeasonKpis(
        races=int((session_kinds == RACE).sum()),
        sprints=int((session_kinds == SPRINT).sum()),
        distinct_winners=int((standings["wins"] > 0).sum())
        if not standings.empty
        else 0,
        leader_name=str(leader["name"]) if leader is not None else None,
        leader_acronym=str(leader["acronym"]) if leader is not None else None,
        leader_points=float(leader["points"]) if leader is not None else 0.0,
        events=events,
        events_won=int(wins["session_key"].nunique()),
        filtered=allowed is not None,
        primary=primary_kinds(selected),
        points_kinds=points_kinds,
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
