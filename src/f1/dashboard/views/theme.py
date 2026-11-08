"""Tema visual: CSS customizado, cores e layout padrão dos gráficos."""

from html import escape
from typing import Any

import streamlit as st

SERIF = "'Iowan Old Style', 'Palatino Linotype', Georgia, 'Times New Roman', serif"
GRID = "rgba(255, 255, 255, 0.07)"
MUTED = "#9CA3AF"

COMPOUND_COLOURS: dict[str, str] = {
    "SOFT": "#DA291C",
    "MEDIUM": "#FFD12E",
    "HARD": "#F0F0EC",
    "INTERMEDIATE": "#43B02A",
    "WET": "#0067AD",
    "UNKNOWN": "#6B7280",
    "TEST_UNKNOWN": "#6B7280",
}
COMPOUND_LABELS: dict[str, str] = {
    "SOFT": "Macio",
    "MEDIUM": "Médio",
    "HARD": "Duro",
    "INTERMEDIATE": "Intermediário",
    "WET": "Chuva",
    "UNKNOWN": "Desconhecido",
    "TEST_UNKNOWN": "Desconhecido",
}

CSS = f"""
<style>
  .f1-title {{
    font-family: {SERIF};
    font-weight: 600;
    font-size: 2.6rem;
    line-height: 1.1;
    letter-spacing: -0.01em;
    margin: 0.2rem 0 0.4rem 0;
  }}
  .f1-summary {{
    font-size: 1.12rem;
    opacity: 0.88;
    margin: 0 0 1.4rem 0;
  }}
  .f1-summary strong {{ opacity: 1; font-weight: 650; }}
  .f1-section {{
    font-family: {SERIF};
    font-size: 1.7rem;
    font-weight: 600;
    margin: 1.8rem 0 0.6rem 0;
    padding-bottom: 0.35rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }}
  .f1-subtitle {{ font-size: 0.86rem; opacity: 0.65; margin: -0.2rem 0 0.6rem 0; }}
  .kpi-card {{
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 14px;
    padding: 1.05rem 1.25rem 1.1rem 1.25rem;
    background: rgba(255, 255, 255, 0.025);
    height: 100%;
  }}
  .kpi-label {{
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    opacity: 0.7;
  }}
  .kpi-value {{
    font-family: {SERIF};
    font-size: 2.6rem;
    font-weight: 600;
    line-height: 1.1;
    margin: 0.35rem 0 0.25rem 0;
  }}
  .kpi-caption {{ font-size: 0.8rem; opacity: 0.58; }}
</style>
"""


def inject_css() -> None:
    """Aplica o CSS customizado à página."""
    st.markdown(CSS, unsafe_allow_html=True)


def kpi_card(label: str, value: str, caption: str) -> str:
    """HTML de um cartão de KPI (valor grande + legenda pequena)."""
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-label">{escape(label)}</div>'
        f'<div class="kpi-value">{escape(value)}</div>'
        f'<div class="kpi-caption">{escape(caption)}</div>'
        "</div>"
    )


def section(title: str, subtitle: str | None = None) -> None:
    """Título de seção (serifado) com subtítulo opcional."""
    st.markdown(
        f'<div class="f1-section">{escape(title)}</div>', unsafe_allow_html=True
    )
    if subtitle:
        subtitle_html = f'<div class="f1-subtitle">{escape(subtitle)}</div>'
        st.markdown(subtitle_html, unsafe_allow_html=True)


def base_layout(height: int, **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Layout Plotly padrão: fundo transparente, grade sutil, sem margens largas."""
    layout: dict[str, Any] = {
        "height": height,
        "template": "plotly_dark",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "margin": {"l": 8, "r": 24, "t": 8, "b": 8},
        "font": {"size": 13},
        "hoverlabel": {"font": {"size": 13}},
        "xaxis": {"gridcolor": GRID, "zeroline": False},
        "yaxis": {"gridcolor": GRID, "zeroline": False},
        "legend": {"orientation": "h", "y": -0.18, "x": 0},
    }
    layout.update(overrides)
    return layout
