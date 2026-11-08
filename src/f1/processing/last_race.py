"""Última corrida concluída: escolha, classificação com largada e destaques.

Funções puras sobre os datasets silver. "Concluída" = corrida principal com
``date_end`` no passado; a corrida exibida é a mais recente que também já tem
resultados (quando a última ainda não tem, a anterior é exibida).
"""

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from f1.domain.models import POINTS_KINDS, QUALIFYING_TYPE
from f1.processing.standings import (
    RACE,
    classified_sessions,
    driver_standings,
    race_classification,
)

CHAMPIONSHIP_TOP = 5


@dataclass(frozen=True)
class RaceChoice:
    """Corrida a exibir e a corrida concluída mais recente."""

    shown: pd.Series | None  # mais recente com resultados
    latest: pd.Series | None  # mais recente concluída (pode não ter resultados)

    @property
    def results_pending(self) -> bool:
        """A corrida mais recente terminou, mas ainda não tem resultados."""
        if self.latest is None:
            return False
        return self.shown is None or int(self.shown["session_key"]) != int(
            self.latest["session_key"]
        )


@dataclass(frozen=True)
class RaceHighlights:
    fastest_name: str | None
    fastest_acronym: str | None
    fastest_time: float | None
    fastest_lap: int | None
    top_gainer_name: str | None
    top_gain: int | None
    retirements: int


def completed_races(sessions: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Corridas principais com ``date_end`` no passado, em ordem, com a rodada."""
    races = classified_sessions(sessions)
    races = races.loc[races["kind"] == RACE]
    ends = sessions.set_index("session_key")["date_end"]
    races = races.assign(date_end=races["session_key"].map(ends))
    finished = pd.to_datetime(races["date_end"], utc=True) <= pd.Timestamp(now)
    return races.loc[finished.fillna(False)].reset_index(drop=True)


def sessions_with_results(results: pd.DataFrame) -> set[int]:
    """Sessões com ao menos um piloto classificado."""
    rows = results.loc[results["position"].notna(), "session_key"]
    return {int(k) for k in rows.dropna().unique()}


def choose_last_race(
    sessions: pd.DataFrame, results: pd.DataFrame, now: datetime
) -> RaceChoice:
    """Escolhe a corrida exibida e detecta resultados ainda não publicados."""
    done = completed_races(sessions, now)
    if done.empty:
        return RaceChoice(shown=None, latest=None)
    available = done.loc[done["session_key"].isin(sessions_with_results(results))]
    shown = None if available.empty else available.iloc[-1]
    return RaceChoice(shown=shown, latest=done.iloc[-1])


def race_grid(
    grid: pd.DataFrame, sessions: pd.DataFrame, meeting_key: int
) -> pd.DataFrame:
    """Grade de largada da corrida principal do meeting.

    A OpenF1 associa a grade à classificação que a definiu; a da corrida
    principal é a da sessão ``Qualifying`` (não a da classificação sprint).
    """
    quali = sessions.loc[
        (sessions["meeting_key"] == meeting_key)
        & (sessions["session_name"] == QUALIFYING_TYPE),
        "session_key",
    ]
    rows = grid.loc[grid["session_key"].isin(list(quali))]
    out = rows[["driver_number", "position"]].rename(columns={"position": "grid"})
    return out.drop_duplicates("driver_number").reset_index(drop=True)


def positions_gained(grid: pd.Series, finish: pd.Series) -> pd.Series:
    """Posições ganhas (``+``) ou perdidas (``-``): largada - chegada.

    Nulo quando falta a largada (ex.: largou do box) ou a chegada (abandono).
    """
    start = pd.to_numeric(grid, errors="coerce").astype("Int64")
    end = pd.to_numeric(finish, errors="coerce").astype("Int64")
    return (start - end).astype("Int64")


def classification_with_grid(
    results: pd.DataFrame,
    drivers: pd.DataFrame,
    grid: pd.DataFrame,
    session_key: int,
) -> pd.DataFrame:
    """Classificação da corrida com a largada (``grid``) e as posições ganhas."""
    table = race_classification(results, drivers, session_key)
    table = table.merge(grid, on="driver_number", how="left")
    table["grid"] = table["grid"].astype("Int64")
    table["gained"] = positions_gained(table["grid"], table["position"])
    return table


def race_highlights(
    classification: pd.DataFrame, fastest: pd.DataFrame | None = None
) -> RaceHighlights:
    """Volta mais rápida, quem mais ganhou posições e número de abandonos."""
    best = None if fastest is None or fastest.empty else fastest.iloc[0]
    gains = classification.loc[classification["gained"].notna()]
    gainer = None
    if not gains.empty and int(gains["gained"].max()) > 0:
        gainer = gains.sort_values(
            ["gained", "position"], ascending=[False, True]
        ).iloc[0]
    return RaceHighlights(
        fastest_name=None if best is None else str(best["name"]),
        fastest_acronym=None if best is None else str(best["acronym"]),
        fastest_time=None if best is None else float(best["lap_duration"]),
        fastest_lap=None if best is None else int(best["lap_number"]),
        top_gainer_name=None if gainer is None else str(gainer["name"]),
        top_gain=None if gainer is None else int(gainer["gained"]),
        retirements=int(classification["dnf"].fillna(False).astype(bool).sum()),
    )


def _sessions_until(sessions: pd.DataFrame, round_number: int) -> pd.DataFrame:
    rounds = classified_sessions(sessions)
    keys = rounds.loc[rounds["round"] <= round_number, "session_key"]
    return sessions.loc[sessions["session_key"].isin(list(keys))]


def championship_after(
    results: pd.DataFrame,
    sessions: pd.DataFrame,
    drivers: pd.DataFrame,
    round_number: int,
    top: int = CHAMPIONSHIP_TOP,
) -> pd.DataFrame:
    """Top ``top`` do campeonato após a rodada, com a variação de posição.

    ``change`` = posição antes da rodada - posição depois (positivo = subiu);
    nulo na primeira rodada ou para quem ainda não pontuava.
    """
    after = driver_standings(
        results, _sessions_until(sessions, round_number), drivers, POINTS_KINDS
    )
    if round_number > 1:
        before = driver_standings(
            results, _sessions_until(sessions, round_number - 1), drivers, POINTS_KINDS
        )
        previous = dict(zip(before["name"], before["position"], strict=True))
    else:
        previous = {}
    table = after.head(top).copy()
    table["previous"] = pd.array(
        [previous.get(n) for n in table["name"]], dtype="Int64"
    )
    table["change"] = (table["previous"] - table["position"]).astype("Int64")
    columns = ["position", "acronym", "name", "team", "colour", "points"]
    return table[[*columns, "previous", "change"]].reset_index(drop=True)
