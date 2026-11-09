"""Formatação de textos e números para exibição (funções puras)."""

import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from f1.domain.models import POINTS_KINDS, SessionKind
from f1.processing.standings import SeasonKpis

_LAPS_BEHIND = re.compile(r"^\+?(\d+)\s*LAPS?$", re.IGNORECASE)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return False


def format_count(value: int) -> str:
    """Inteiro com separador de milhar pt-BR: ``1234`` → ``"1.234"``."""
    return f"{value:,}".replace(",", ".")


def format_points(value: float) -> str:
    """``437.0`` → ``"437"``; ``12.5`` → ``"12,5"``."""
    if float(value).is_integer():
        return format_count(int(value))
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


KIND_LABELS: dict[SessionKind, str] = {
    SessionKind.RACE: "Corrida",
    SessionKind.SPRINT: "Sprint",
    SessionKind.QUALIFYING: "Classificação",
    SessionKind.PRACTICE: "Treino livre",
}
_PLURALS: dict[SessionKind, tuple[str, str]] = {
    SessionKind.RACE: ("corrida", "corridas"),
    SessionKind.SPRINT: ("sprint", "sprints"),
    SessionKind.QUALIFYING: ("classificação", "classificações"),
    SessionKind.PRACTICE: ("sessão de treino", "sessões de treino"),
}
_SESSION_NAMES: dict[str, str] = {
    "Race": "Corrida",
    "Sprint": "Sprint",
    "Qualifying": "Classificação",
    "Sprint Qualifying": "Classificação sprint",
    "Sprint Shootout": "Classificação sprint",
    "Practice 1": "Treino livre 1",
    "Practice 2": "Treino livre 2",
    "Practice 3": "Treino livre 3",
}


def session_label(session_name: object) -> str:
    """Nome da sessão em português (``"Practice 1"`` → ``"Treino livre 1"``)."""
    name = str(session_name)
    return _SESSION_NAMES.get(name, name)


def events_noun(primary: tuple[SessionKind, ...], count: int) -> str:
    """Substantivo para as sessões principais (``corridas``, ``sprints``...)."""
    singular, plural = (
        _PLURALS[primary[0]] if len(primary) == 1 else ("sessão", "sessões")
    )
    return singular if count == 1 else plural


def points_caption(points_kinds: tuple[SessionKind, ...]) -> str:
    """Legenda do KPI "Pontos do líder" conforme os tipos selecionados."""
    if set(points_kinds) == set(POINTS_KINDS):
        return "Corridas + sprints"
    if points_kinds == (SessionKind.RACE,):
        return "Só corridas"
    if points_kinds == (SessionKind.SPRINT,):
        return "Só sprints"
    return "Os tipos selecionados não valem pontos"


def points_subtitle(points_kinds: tuple[SessionKind, ...]) -> str:
    """Subtítulo do gráfico "Pontos por piloto"."""
    origin = {
        frozenset(POINTS_KINDS): "corridas e sprints",
        frozenset({SessionKind.RACE}): "corridas",
        frozenset({SessionKind.SPRINT}): "sprints",
    }.get(frozenset(points_kinds), "corridas e sprints")
    return f"Soma dos pontos de {origin} (inclui o ponto da volta mais rápida)."


def winners_caption(kpis: SeasonKpis) -> str:
    """Legenda do KPI "Vencedores diferentes"."""
    if kpis.primary == (SessionKind.RACE,):
        text = "Em corridas, sem contar sprints"
    else:
        text = "Em " + events_noun(kpis.primary, 2)
    return f"{text} · pilotos filtrados" if kpis.filtered else text


def summary_sentence(kpis: SeasonKpis) -> str:
    """Frase-resumo da seleção em Markdown, com destaques em negrito."""
    count = kpis.events or kpis.races
    winners = kpis.distinct_winners
    noun = events_noun(kpis.primary, count)
    points = format_points(kpis.leader_points)
    if kpis.filtered:
        return _filtered_sentence(kpis, count, noun, points)
    if kpis.leader_name is not None and kpis.in_progress:
        return _in_progress_sentence(kpis, points)
    if kpis.leader_name is not None:
        leader = f"**{kpis.leader_name}** soma **{points}** pontos"
        who = "piloto venceu" if winners == 1 else "pilotos diferentes venceram"
        if count == 1:
            return f"{leader}; **{winners}** {who} a **1** {noun} disputada."
        return f"{leader}; **{winners}** {who} as **{count}** {noun}."
    if count:
        who = "piloto terminou" if winners == 1 else "pilotos diferentes terminaram"
        return f"**{winners}** {who} em 1º nas **{count}** {noun} disputadas."
    return "Ainda não há resultados de corridas nesta temporada."


def _progress(kpis: SeasonKpis) -> str:
    noun = "corrida" if kpis.scheduled_races == 1 else "corridas"
    return f"após **{kpis.races}** de **{kpis.scheduled_races}** {noun}"


def _in_progress_sentence(kpis: SeasonKpis, points: str) -> str:
    """Temporada em andamento: ``{líder} lidera com {pts} pontos após X de Y``."""
    winners = kpis.distinct_winners
    who = "piloto venceu" if winners == 1 else "pilotos diferentes venceram"
    return (
        f"**{kpis.leader_name}** lidera com **{points}** pontos {_progress(kpis)}; "
        f"**{winners}** {who}."
    )


def races_card(kpis: SeasonKpis) -> tuple[str, str]:
    """Valor e legenda do cartão "Corridas" (``feitas/total`` se em andamento)."""
    if kpis.in_progress:
        return f"{kpis.races}/{kpis.scheduled_races}", "Realizadas / previstas"
    return str(kpis.races), "Grandes Prêmios da temporada"


def _filtered_sentence(kpis: SeasonKpis, count: int, noun: str, points: str) -> str:
    winners = kpis.distinct_winners
    if winners == 0:
        tail = f"nenhum piloto da seleção venceu entre as **{count}** {noun}"
    else:
        who = (
            "piloto da seleção venceu"
            if winners == 1
            else "pilotos da seleção venceram"
        )
        tail = f"**{winners}** {who} **{kpis.events_won}** de **{count}** {noun}"
    if kpis.leader_name is None:
        return tail[0].upper() + tail[1:] + "."
    progress = f" {_progress(kpis)}" if kpis.in_progress else ""
    leader = f"**{kpis.leader_name}** lidera a seleção com **{points}** pontos"
    return f"{leader}{progress}; {tail}."


GAINED_COLOUR = "#22C55E"
LOST_COLOUR = "#EF4444"


def format_change(change: object) -> str:
    """Variação de posições: ``3`` → ``"▲ 3"``, ``-2`` → ``"▼ 2"``, ``0`` → ``"="``."""
    if _is_missing(change):
        return "—"
    value = int(str(change))
    if value > 0:
        return f"▲ {value}"
    if value < 0:
        return f"▼ {-value}"
    return "="


def change_style(change: object) -> str:
    """CSS da variação: verde quando ganhou, vermelho quando perdeu."""
    if _is_missing(change) or int(str(change)) == 0:
        return ""
    return f"color: {GAINED_COLOUR if int(str(change)) > 0 else LOST_COLOUR}"


def format_gap_laps(gap: object) -> str:
    """Diferença com voltas no padrão da F1: ``"+1 LAP"``, ``"+2 LAPS"``."""
    if _is_missing(gap):
        return "—"
    laps = _LAPS_BEHIND.match(str(gap).strip())
    if laps:
        n = int(laps.group(1))
        return f"+{n} LAP" if n == 1 else f"+{n} LAPS"
    return format_gap(gap)


def format_finish(position: object, duration: object, gap: object) -> str:
    """Tempo do vencedor ou diferença dos demais (com ``+N LAP``)."""
    if not _is_missing(position) and int(str(position)) == 1:
        return format_race_time(duration)
    return format_gap_laps(gap)


def status_code(dnf: object, dns: object, dsq: object) -> str:
    """Situação no padrão da F1: ``DSQ``, ``DNS``, ``DNF`` ou vazio."""
    if dsq is True:
        return "DSQ"
    if dns is True:
        return "DNS"
    if dnf is True:
        return "DNF"
    return ""


BRASILIA = ZoneInfo("America/Sao_Paulo")


def format_brasilia(value: datetime | None) -> str:
    """``2026-11-08 23:13 UTC`` → ``"08/11/2026 20:13 (Brasília)"``."""
    if value is None:
        return "—"
    return value.astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M") + " (Brasília)"
