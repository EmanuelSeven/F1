"""Filtros da análise da temporada (funções puras).

Semântica:

- ``kinds``: tipos de sessão analisados. Pontos somam os tipos escolhidos;
  vencedores, vitórias e pódios usam os tipos principais (``primary_kinds``).
- ``meeting_key``: Grande Prêmio em destaque. Não filtra a agregação; serve
  para destacar a linha na tabela e abrir os detalhes daquele GP.
- ``teams`` e ``drivers``: restringem os pilotos considerados (E lógico). Um
  piloto entra no filtro de equipe se correu por ela em alguma sessão do ano.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import pandas as pd

from f1.domain.models import POINTS_KINDS, SessionKind
from f1.processing.standings import (
    RACE,
    SeasonKpis,
    classified_sessions,
    driver_directory,
    driver_numbers,
    driver_standings,
    race_schedule,
    race_winners,
    season_kpis,
)


@dataclass(frozen=True)
class SeasonFilter:
    kinds: tuple[SessionKind, ...] = POINTS_KINDS
    meeting_key: int | None = None
    teams: tuple[str, ...] = ()
    drivers: tuple[int, ...] = ()

    @property
    def restricts_drivers(self) -> bool:
        return bool(self.teams or self.drivers)


@dataclass(frozen=True)
class SeasonView:
    """Resultado da análise filtrada."""

    filter: SeasonFilter
    standings: pd.DataFrame
    winners: pd.DataFrame  # vencedores dos pilotos da seleção
    all_winners: pd.DataFrame  # vencedores de todos os pilotos
    kpis: SeasonKpis = field(repr=False)

    @property
    def highlighted_rows(self) -> list[int]:
        """Posições, em ``winners``, das linhas do GP em destaque."""
        if self.filter.meeting_key is None:
            return []
        mask = self.winners["meeting_key"] == self.filter.meeting_key
        return [int(i) for i in mask[mask].index]

    def focus_row(self) -> pd.Series | None:
        """Sessão do GP em destaque (corrida principal, se houver)."""
        if self.filter.meeting_key is None:
            return None
        rows = self.all_winners.loc[
            self.all_winners["meeting_key"] == self.filter.meeting_key
        ]
        return None if rows.empty else rows.iloc[0]


def allowed_drivers(drivers: pd.DataFrame, filt: SeasonFilter) -> set[int] | None:
    """Números de carro dos pilotos da seleção (``None`` = todos).

    Inclui todos os números usados por cada piloto selecionado.
    """
    if not filt.restricts_drivers:
        return None
    same_driver = driver_numbers(drivers)
    pool = set(same_driver)
    if filt.teams:
        in_teams = drivers["team_name"].isin(list(filt.teams))
        team_numbers = drivers.loc[in_teams, "driver_number"].dropna().astype(int)
        pool &= {m for n in team_numbers for m in same_driver.get(int(n), {int(n)})}
    if filt.drivers:
        pool &= {m for n in filt.drivers for m in same_driver.get(n, {n})}
    return pool


def team_options(drivers: pd.DataFrame) -> list[str]:
    """Equipes da temporada, em ordem alfabética."""
    return sorted(set(drivers["team_name"].dropna().astype(str)))


def driver_options(
    drivers: pd.DataFrame, sessions: pd.DataFrame, teams: Sequence[str] = ()
) -> pd.DataFrame:
    """Pilotos da temporada (opcionalmente só das ``teams``), por sigla."""
    directory = driver_directory(drivers, sessions)
    if teams:
        in_teams = drivers["team_name"].isin(list(teams))
        numbers = set(drivers.loc[in_teams, "driver_number"].dropna().astype(int))
        directory = directory.loc[
            [bool(numbers & set(ns)) for ns in directory["driver_numbers"]]
        ]
    columns = ["driver_number", "acronym", "name"]
    return directory.sort_values("acronym")[columns].reset_index(drop=True)


def grand_prix_options(sessions: pd.DataFrame, meetings: pd.DataFrame) -> pd.DataFrame:
    """Grandes Prêmios do ano (com corrida), em ordem de rodada."""
    races = classified_sessions(sessions)
    races = races.loc[races["kind"] == RACE, ["meeting_key", "round"]]
    df = races.merge(
        meetings[["meeting_key", "meeting_name", "country_name"]],
        on="meeting_key",
        how="left",
    )
    name = df["meeting_name"].fillna(df["country_name"]).fillna("—").astype(str)
    df["gp"] = name.str.replace(r"\s*Grand Prix$", "", regex=True)
    df["label"] = [
        f"{int(r)} · {g}" for r, g in zip(df["round"], df["gp"], strict=True)
    ]
    return df[["meeting_key", "round", "gp", "label"]].reset_index(drop=True)


def season_view(  # noqa: PLR0913 - datasets + filtro + relógio injetável
    results: pd.DataFrame,
    sessions: pd.DataFrame,
    meetings: pd.DataFrame,
    drivers: pd.DataFrame,
    filt: SeasonFilter,
    *,
    now: datetime | None = None,
) -> SeasonView:
    """Classificação, vencedores e KPIs da seleção."""
    allowed = allowed_drivers(drivers, filt)
    standings = driver_standings(results, sessions, drivers, filt.kinds)
    all_winners = race_winners(results, sessions, meetings, drivers, filt.kinds)
    winners = all_winners
    if allowed is not None:
        standings = standings.loc[
            [bool(allowed & set(ns)) for ns in standings["driver_numbers"]]
        ]
        winners = all_winners.loc[all_winners["driver_number"].isin(allowed)]
    standings = standings.reset_index(drop=True)
    winners = winners.reset_index(drop=True)
    kpis = season_kpis(results, sessions, standings, filt.kinds, allowed)
    schedule = race_schedule(sessions, now or datetime.now(UTC))
    kpis = replace(
        kpis, scheduled_races=schedule.scheduled, upcoming_races=schedule.upcoming
    )
    return SeasonView(
        filter=filt,
        standings=standings,
        winners=winners,
        all_winners=all_winners,
        kpis=kpis,
    )
