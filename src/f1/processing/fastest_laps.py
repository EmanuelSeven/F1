"""Voltas mais rápidas por circuito (funções puras sobre DataFrames silver).

Um circuito corresponde a um Grande Prêmio (meeting) da temporada; as voltas
consideradas são as das sessões dos tipos escolhidos já encerradas.
"""

from collections.abc import Collection, Sequence
from datetime import datetime

import pandas as pd

from f1.domain.models import SessionKind
from f1.processing.standings import (
    FALLBACK_COLOUR,
    RACE,
    classified_sessions,
    driver_identity,
    driver_info,
)

TOP_LAPS = 5


def _session_end(sessions: pd.DataFrame) -> pd.Series:
    """Fim de cada sessão (``date_end``, ou ``date_start`` se faltar), em UTC."""
    end = sessions["date_end"].fillna(sessions["date_start"])
    return pd.Series(
        pd.to_datetime(end, utc=True).to_numpy(),
        index=sessions["session_key"].astype(int),
    )


def circuit_sessions(
    sessions: pd.DataFrame,
    meeting_key: int,
    kinds: Sequence[SessionKind],
    now: datetime,
) -> list[int]:
    """Sessões encerradas do circuito ``meeting_key`` dos tipos ``kinds``."""
    df = classified_sessions(sessions)
    mask = (df["meeting_key"] == meeting_key) & df["kind"].isin(
        [k.value for k in kinds]
    )
    ends = _session_end(sessions)
    keys = [int(k) for k in df.loc[mask, "session_key"]]
    return [k for k in keys if pd.notna(ends.get(k)) and ends[k] <= pd.Timestamp(now)]


def latest_grand_prix(sessions: pd.DataFrame, now: datetime) -> int | None:
    """Meeting da corrida mais recente já iniciada (``None`` se nenhuma)."""
    df = classified_sessions(sessions)
    races = df.loc[df["kind"] == RACE]
    started = pd.to_datetime(races["date_start"], utc=True) <= pd.Timestamp(now)
    done = races.loc[started.fillna(False)]
    return None if done.empty else int(done["meeting_key"].iloc[-1])


def fastest_laps(  # noqa: PLR0913 - dados + opções de exibição explícitas
    laps: pd.DataFrame,
    drivers: pd.DataFrame,
    sessions: pd.DataFrame,
    *,
    session_keys: Collection[int],
    top: int = TOP_LAPS,
    one_per_driver: bool = False,
    allowed: Collection[int] | None = None,
) -> pd.DataFrame:
    """As ``top`` voltas mais rápidas das sessões ``session_keys``.

    Ignora voltas sem tempo e voltas de saída do box. Com ``one_per_driver``,
    fica só a melhor volta de cada piloto; ``allowed`` restringe os pilotos.
    """
    keys = [int(k) for k in session_keys]
    df = laps.loc[laps["session_key"].isin(keys) & laps["lap_duration"].notna()]
    df = df.loc[~df["is_pit_out_lap"].fillna(False).astype(bool)]
    if allowed is not None:
        df = df.loc[df["driver_number"].isin(list(allowed))]
    info = driver_info(drivers)
    info["identity"] = driver_identity(info)
    df = df.merge(info, on=["session_key", "driver_number"], how="left")
    df = df.merge(
        classified_sessions(sessions)[["session_key", "session_name", "kind"]],
        on="session_key",
        how="left",
    )
    df["acronym"] = df["acronym"].fillna(df["driver_number"].astype(str))
    df["identity"] = df["identity"].fillna(df["driver_number"].astype(str))
    df["team"] = df["team"].fillna("—")
    df["colour"] = df["colour"].fillna(FALLBACK_COLOUR)
    df = df.sort_values(["lap_duration", "date_start"], kind="stable")
    if one_per_driver:
        df = df.drop_duplicates("identity", keep="first")
    df = df.head(top).reset_index(drop=True)
    df.insert(0, "position", range(1, len(df) + 1))
    best = float(df["lap_duration"].iloc[0]) if not df.empty else 0.0
    df["gap"] = df["lap_duration"].astype(float) - best
    columns = ["position", "driver_number", "acronym", "name", "team", "colour"]
    extra = ["lap_duration", "gap", "lap_number", "session_key", "session_name", "kind"]
    return df[[*columns, *extra]]
