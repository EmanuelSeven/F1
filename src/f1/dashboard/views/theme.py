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
  .podium-card {{
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-top: 4px solid var(--team, #9CA3AF);
    border-radius: 14px;
    padding: 0.9rem 1.15rem 1rem 1.15rem;
    background: rgba(255, 255, 255, 0.025);
    height: 100%;
  }}
  .podium-place {{ font-family: {SERIF}; font-size: 1.9rem; font-weight: 600; }}
  .podium-driver {{ font-size: 1.15rem; font-weight: 650; margin-top: 0.1rem; }}
  .podium-team {{ font-size: 0.85rem; font-weight: 600; margin: 0.1rem 0 0.5rem 0; }}
  .podium-time {{ font-family: {SERIF}; font-size: 1.35rem; }}
  .f1-date {{ font-size: 0.95rem; opacity: 0.7; margin: -0.2rem 0 0.2rem 0; }}
  .f1-brand {{
    font-size: 1.15rem;
    font-weight: 800;
    letter-spacing: 0.04em;
    margin: 0.2rem 0 1.1rem 0;
  }}
  .f1-brand-mark {{ color: #E10600; font-style: italic; }}
  .f1-brand-sub {{ font-weight: 500; opacity: 0.8; letter-spacing: 0.02em; }}
  .f1-sidebar-title {{
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    opacity: 0.7;
    margin: 0.4rem 0 0.3rem 0;
  }}
</style>
"""


# O Streamlit serve a página com <html lang="en">; com a interface em português,
# o navegador oferece tradução automática e traduz siglas e nomes dos gráficos
# (ex.: "LAW" → "DIREITO", exibido cortado como "REITO"). Este script declara a
# página como pt-BR e marca o documento como não traduzível.
NO_TRANSLATE_SCRIPT = """
<script>
(() => {
  const root = document.documentElement;
  root.setAttribute("lang", "pt-BR");
  root.setAttribute("translate", "no");
  root.classList.add("notranslate");
  if (!document.querySelector('meta[name="google"][content="notranslate"]')) {
    const meta = document.createElement("meta");
    meta.name = "google";
    meta.content = "notranslate";
    document.head.appendChild(meta);
  }
})();
</script>
"""


def inject_css() -> None:
    """Aplica o CSS customizado à página."""
    st.markdown(CSS, unsafe_allow_html=True)


def prevent_translation() -> None:
    """Impede a tradução automática do navegador (página já está em pt-BR)."""
    st.html(NO_TRANSLATE_SCRIPT, unsafe_allow_javascript=True)


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


AXIS_DEFAULTS: dict[str, Any] = {
    "gridcolor": GRID,
    "zeroline": False,
    # Reserva espaço para os rótulos: sem isso, rótulos longos são cortados.
    "automargin": True,
}


def base_layout(height: int, **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Layout Plotly padrão: fundo transparente, grade sutil, margens justas.

    Opções de ``xaxis``/``yaxis`` em ``overrides`` são mescladas aos padrões
    (``automargin`` continua ligado).
    """
    layout: dict[str, Any] = {
        "height": height,
        "template": "plotly_dark",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "margin": {"l": 8, "r": 24, "t": 8, "b": 8},
        "font": {"size": 13},
        "hoverlabel": {"font": {"size": 13}},
        "legend": {"orientation": "h", "y": -0.18, "x": 0},
    }
    for axis in ("xaxis", "yaxis"):
        layout[axis] = {**AXIS_DEFAULTS, **overrides.pop(axis, {})}
    layout.update(overrides)
    return layout


def podium_card(place: str, driver: str, team: str, colour: str, time: str) -> str:
    """HTML de um cartão do pódio, com a cor da equipe."""
    return (
        f'<div class="podium-card" style="--team: {escape(colour)}">'
        f'<div class="podium-place">{escape(place)}</div>'
        f'<div class="podium-driver">{escape(driver)}</div>'
        f'<div class="podium-team" style="color: {escape(colour)}">{escape(team)}</div>'
        f'<div class="podium-time">{escape(time)}</div>'
        "</div>"
    )
