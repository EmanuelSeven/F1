"""Gráficos Plotly do dashboard (DataFrame → Figure, sem Streamlit)."""

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from f1.dashboard.views.driver_badge import country_label, flag_png_url
from f1.dashboard.views.formatting import format_lap, format_points
from f1.dashboard.views.theme import (
    COMPOUND_COLOURS,
    COMPOUND_LABELS,
    MUTED,
    base_layout,
)

BAR_HEIGHT = 26
# Bandeiras do eixo Y (gráfico de pontos): altura em unidades de categoria
# (1 = uma barra), caixa em fração da largura do gráfico e espaço, em pixels,
# entre a sigla e o eixo para a bandeira caber.
FLAG_SIZE_Y = 0.62
FLAG_BOX_X = 0.07
FLAG_GAP_X = 0.008
FLAG_STANDOFF = 36


def flag_images(acronyms: pd.Series, countries: pd.Series) -> list[dict[str, Any]]:
    """Uma bandeira PNG por piloto com país, na altura da sua barra.

    O eixo Y é categórico: a categoria ``i`` fica na posição ``i`` (ordem de
    primeira aparição). A imagem fica à esquerda do início das barras, entre a
    sigla e a barra. Piloto sem país conhecido fica sem bandeira.
    """
    positions = {a: i for i, a in enumerate(dict.fromkeys(acronyms))}
    images: list[dict[str, Any]] = []
    for acronym, country in zip(acronyms, countries, strict=True):
        url = flag_png_url(country)
        if url is None:
            continue
        images.append(
            {
                "source": url,
                "xref": "paper",
                "yref": "y",
                "x": -FLAG_GAP_X,
                "y": positions[acronym],
                "sizex": FLAG_BOX_X,
                "sizey": FLAG_SIZE_Y,
                "xanchor": "right",
                "yanchor": "middle",
                "sizing": "contain",
                "layer": "above",
            }
        )
    return images


def points_bar(standings: pd.DataFrame) -> go.Figure:
    """Barras horizontais de pontos por piloto, líder no topo, cor da equipe.

    A bandeira do país aparece entre a sigla e o início da barra.
    """
    customdata = (
        standings[["name", "team", "wins", "podiums"]]
        .assign(country=[country_label(c) for c in standings["country"]])
        .to_numpy()
    )
    fig = go.Figure(
        go.Bar(
            x=standings["points"],
            y=standings["acronym"],
            orientation="h",
            marker={"color": standings["colour"].tolist(), "line": {"width": 0}},
            text=[format_points(p) for p in standings["points"]],
            textposition="outside",
            cliponaxis=False,
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
                "País: %{customdata[4]}<br>"
                "Pontos: %{x}<br>Vitórias: %{customdata[2]}<br>"
                "Pódios: %{customdata[3]}<extra></extra>"
            ),
        )
    )
    height = max(320, BAR_HEIGHT * len(standings) + 40)
    max_points = float(standings["points"].max()) if not standings.empty else 1.0
    images = flag_images(standings["acronym"], standings["country"])
    standoff = FLAG_STANDOFF if images else 0
    fig.update_layout(
        **base_layout(
            height,
            bargap=0.28,
            showlegend=False,
            images=images,
            margin={"l": 8 + standoff, "r": 24, "t": 8, "b": 8},
            xaxis={"visible": False, "range": [0, max_points * 1.12]},
            yaxis={
                "autorange": "reversed",
                "type": "category",
                "tickfont": {"size": 12},
                "gridcolor": "rgba(0,0,0,0)",
                "ticklabelstandoff": standoff,
            },
        )
    )
    return fig


def lap_times_chart(laps: pd.DataFrame) -> go.Figure:
    """Tempo por volta de cada piloto; companheiros de equipe em linha pontilhada."""
    fig = go.Figure()
    seen_colours: set[str] = set()
    for acronym, rows in laps.groupby("acronym", sort=False):
        colour = str(rows["colour"].iloc[0])
        country = country_label(rows["country"].iloc[0])
        dash = "dot" if colour in seen_colours else "solid"
        seen_colours.add(colour)
        fig.add_trace(
            go.Scatter(
                x=rows["lap_number"],
                y=rows["lap_duration"],
                mode="lines",
                name=str(acronym),
                line={"color": colour, "width": 2, "dash": dash},
                text=[format_lap(v) for v in rows["lap_duration"]],
                hovertemplate=(
                    f"<b>{acronym}</b> ({country}) · volta %{{x}}<br>"
                    "%{text}<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        **base_layout(
            420,
            xaxis={"title": "Volta", "gridcolor": "rgba(255,255,255,0.07)"},
            yaxis={"title": "Tempo (s)", "gridcolor": "rgba(255,255,255,0.07)"},
            hovermode="closest",
        )
    )
    return fig


def tyre_strategy_chart(stints: pd.DataFrame) -> go.Figure:
    """Linha do tempo de pneus: um traço por composto, da volta inicial à final."""
    order = list(dict.fromkeys(stints["acronym"]))
    fig = go.Figure()
    for compound, rows in stints.groupby("compound", sort=False):
        name = str(compound)
        fig.add_trace(
            go.Bar(
                x=rows["laps"],
                base=rows["lap_start"] - 1,
                y=rows["acronym"],
                orientation="h",
                name=COMPOUND_LABELS.get(name, name.title()),
                marker={
                    "color": COMPOUND_COLOURS.get(name, MUTED),
                    "line": {"color": "#0F1115", "width": 1.5},
                },
                customdata=rows[["lap_start", "lap_end", "tyre_age_at_start"]]
                .assign(country=[country_label(c) for c in rows["country"]])
                .to_numpy(),
                hovertemplate=(
                    "<b>%{y}</b> (%{customdata[3]}) · "
                    + COMPOUND_LABELS.get(name, name.title())
                    + "<br>Voltas %{customdata[0]} a %{customdata[1]}"
                    "<br>Idade inicial: %{customdata[2]} voltas<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        **base_layout(
            max(320, BAR_HEIGHT * len(order) + 80),
            barmode="overlay",
            bargap=0.3,
            xaxis={"title": "Volta", "gridcolor": "rgba(255,255,255,0.07)"},
            yaxis={
                "type": "category",
                "categoryorder": "array",
                "categoryarray": order,
                "autorange": "reversed",
                "gridcolor": "rgba(0,0,0,0)",
            },
        )
    )
    return fig


def weather_chart(weather: pd.DataFrame) -> go.Figure:
    """Temperatura do ar e da pista ao longo da corrida."""
    fig = go.Figure()
    series = (
        ("track_temperature", "Pista", "#F97316"),
        ("air_temperature", "Ar", "#38BDF8"),
    )
    for column, label, colour in series:
        fig.add_trace(
            go.Scatter(
                x=weather["date"],
                y=weather[column],
                mode="lines",
                name=label,
                line={"color": colour, "width": 2},
                hovertemplate=(
                    f"{label}: %{{y:.1f}} °C<br>%{{x|%H:%M}} UTC<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        **base_layout(
            320,
            yaxis={"title": "°C", "gridcolor": "rgba(255,255,255,0.07)"},
            xaxis={"title": "Horário (UTC)", "gridcolor": "rgba(255,255,255,0.07)"},
        )
    )
    return fig


TOTAL_LABEL = "Total"
TOTAL_COLOUR = "#E6E6E6"
MIN_RATE_AXIS = 0.05  # com taxas ~0%, o eixo vai até 5% e a linha fica legível


def _rate_trace(rows: pd.DataFrame, name: str, line: dict[str, Any]) -> go.Scatter:
    symbols = ["x" if a else "circle" for a in rows["aborted"]]
    return go.Scatter(
        x=rows["recorded_at"],
        y=rows["rate"],
        mode="lines+markers",
        name=name,
        marker={"symbol": symbols, "size": 8},
        line=line,
        customdata=rows[["run_id", "rejected", "records_read"]]
        .assign(status=["abortada" if a else "publicada" for a in rows["aborted"]])
        .to_numpy(),
        hovertemplate=(
            f"<b>{name}</b><br>"
            "%{y:.1%} (%{customdata[1]} de %{customdata[2]} registros)<br>"
            "Carga %{customdata[3]} · run_id %{customdata[0]}<br>"
            "%{x|%d/%m/%Y %H:%M} UTC<extra></extra>"
        ),
    )


def rejection_trend_chart(totals: pd.DataFrame, trend: pd.DataFrame) -> go.Figure:
    """Taxa de rejeição por carga: linha "Total" e uma linha por regra violada.

    A linha total aparece desde a primeira carga, mesmo sem rejeições (0%).
    Cargas abortadas (taxa acima do limite) aparecem com marcador ``x``.
    """
    fig = go.Figure(
        _rate_trace(totals, TOTAL_LABEL, {"width": 3, "color": TOTAL_COLOUR})
    )
    for rule, rows in trend.groupby("rule", sort=True):
        fig.add_trace(_rate_trace(rows, str(rule), {"width": 2}))
    highest = max(
        (float(df["rate"].max()) for df in (totals, trend) if not df.empty),
        default=0.0,
    )
    top = max(MIN_RATE_AXIS, highest * 1.15)
    fig.update_layout(
        **base_layout(
            380,
            xaxis={"title": "Carga (UTC)", "tickformat": "%d/%m<br>%H:%M"},
            yaxis={
                "title": "Taxa de rejeição",
                "tickformat": ".0%",
                # Folga abaixo de 0%: a linha em zero não fica colada no eixo.
                "range": [-top * 0.04, top],
            },
            hovermode="closest",
            showlegend=True,  # "Total" aparece na legenda mesmo sozinho
            legend={"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom"},
            margin={"l": 8, "r": 24, "t": 36, "b": 8},
        )
    )
    return fig


def _gap_text(gap: float) -> str:
    """``0.39`` → ``"+0,390"`` (diferença para a volta mais rápida)."""
    return f"+{gap:.3f}".replace(".", ",")


def fastest_laps_chart(top: pd.DataFrame) -> go.Figure:
    """Voltas mais rápidas: um ponto por volta no seu tempo, cor da equipe.

    Pontos (e não barras) porque as diferenças são de décimos: barras partindo
    do zero esconderiam a diferença, e barras truncadas a exagerariam.
    """
    labels = [
        f"{int(p)}º {a}" for p, a in zip(top["position"], top["acronym"], strict=True)
    ]
    text = [
        format_lap(t) if g == 0 else f"{format_lap(t)}  {_gap_text(g)}"
        for t, g in zip(top["lap_duration"], top["gap"], strict=True)
    ]
    customdata = (
        top[["name", "team", "session_name", "lap_number"]]
        .assign(country=[country_label(c) for c in top["country"]])
        .to_numpy()
    )
    fig = go.Figure(
        go.Scatter(
            x=top["lap_duration"],
            y=labels,
            mode="markers+text",
            marker={"color": top["colour"].tolist(), "size": 18, "line": {"width": 0}},
            text=text,
            textposition="middle right",
            cliponaxis=False,
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
                "País: %{customdata[4]}<br>"
                "%{customdata[2]}, volta %{customdata[3]}<extra></extra>"
            ),
        )
    )
    low = float(top["lap_duration"].min()) if not top.empty else 0.0
    high = float(top["lap_duration"].max()) if not top.empty else 1.0
    pad = max(0.25, (high - low) * 0.3)
    fig.update_layout(
        **base_layout(
            max(260, 54 * len(top) + 60),
            showlegend=False,
            xaxis={"title": "Tempo de volta (s)", "range": [low - pad, high + pad * 3]},
            yaxis={
                "autorange": "reversed",
                "type": "category",
                "gridcolor": "rgba(0,0,0,0)",
            },
        )
    )
    return fig
