"""Formatação de textos e números para exibição (funções puras)."""

import math
import re
from datetime import datetime

import pandas as pd

from f1.processing.standings import SeasonKpis

_LAPS_BEHIND = re.compile(r"^\+?(\d+)\s*LAPS?$", re.IGNORECASE)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return False


def format_points(value: float) -> str:
    """``437.0`` → ``"437"``; ``12.5`` → ``"12,5"``."""
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", ".")
    return f"{value:.1f}".replace(".", ",")


def format_lap(seconds: object) -> str:
    """``92.708`` → ``"1:32.708"``."""
    if _is_missing(seconds):
        return "—"
    total = float(str(seconds))
    minutes, rest = divmod(total, 60)
    return f"{int(minutes)}:{rest:06.3f}" if minutes else f"{rest:.3f}"


def format_seconds(value: object) -> str:
    """``2.43`` → ``"2,4"``; ausente → ``"—"``."""
    if _is_missing(value):
        return "—"
    return f"{float(str(value)):.1f}".replace(".", ",")


def format_race_time(duration: object) -> str:
    """Duração total da corrida: ``5504.742`` → ``"1:31:44.742"``."""
    if _is_missing(duration):
        return "—"
    total = float(str(duration))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{seconds:06.3f}"


def format_gap(gap: object) -> str:
    """Diferença para o líder: ``21.441`` → ``"+21,441 s"``; ``"+1 LAP"`` → volta."""
    if _is_missing(gap):
        return "—"
    text = str(gap).strip()
    laps = _LAPS_BEHIND.match(text)
    if laps:
        n = int(laps.group(1))
        return f"+{n} volta" if n == 1 else f"+{n} voltas"
    try:
        seconds = float(text)
    except ValueError:
        return text
    return f"+{seconds:.3f} s".replace(".", ",")


def format_result_time(position: object, duration: object, gap: object) -> str:
    """Tempo do vencedor ou diferença dos demais."""
    if not _is_missing(position) and int(str(position)) == 1:
        return format_race_time(duration)
    return format_gap(gap)


def format_status(dnf: object, dns: object, dsq: object) -> str:
    """Situação final em português (vazio quando classificado)."""
    if dsq is True:
        return "Desclassificado"
    if dns is True:
        return "Não largou"
    if dnf is True:
        return "Abandono"
    return ""


def format_day_month(value: datetime | None) -> str:
    """Data curta ``dd/mm``."""
    return value.strftime("%d/%m") if value is not None else "—"


def format_temperature(value: float | None) -> str:
    return (
        "—"
        if value is None or math.isnan(value)
        else f"{value:.1f} °C".replace(".", ",")
    )


def summary_sentence(kpis: SeasonKpis) -> str:
    """Frase-resumo da temporada em Markdown, com destaques em negrito."""
    if kpis.leader_name is None:
        return "Ainda não há resultados de corridas nesta temporada."
    winners = kpis.distinct_winners
    races = kpis.races
    points = format_points(kpis.leader_points)
    leader = f"**{kpis.leader_name}** soma **{points}** pontos"
    who = "piloto venceu" if winners == 1 else "pilotos diferentes venceram"
    if races == 1:
        return f"{leader}; **{winners}** {who} a **1** corrida disputada."
    return f"{leader}; **{winners}** {who} as **{races}** corridas."
