"""Tabelas do dashboard: equipe com quadradinho colorido e linhas em destaque."""

from collections.abc import Iterable, Mapping, Sequence

import pandas as pd
import streamlit as st

from f1.dashboard.views.driver_badge import EMPTY_CELL, flag_country_image

ROW_HEIGHT = 35
SQUARE = "■"
TEAM_COLUMN = "Equipe"
HIGHLIGHT_STYLE = "background-color: rgba(225, 6, 0, 0.22)"
NATIONALITY_COLUMN = "Nacionalidade"  # logo após o piloto


def team_label(team: object) -> str:
    """Equipe com o quadradinho de cor: ``"■ Red Bull Racing"``."""
    return f"{SQUARE} {team}"


def table_styles(
    display: pd.DataFrame,
    colours: Sequence[str],
    highlight: Sequence[int] = (),
    column_styles: Mapping[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """CSS por célula: cor da equipe na coluna ``Equipe`` e linhas em destaque."""
    styles = pd.DataFrame("", index=display.index, columns=display.columns)
    if TEAM_COLUMN in styles.columns:
        styles[TEAM_COLUMN] = [f"color: {c}" for c in colours]
    for column, css in (column_styles or {}).items():
        styles[column] = list(css)
    for row in highlight:
        styles.iloc[row] = [
            f"{css}; {HIGHLIGHT_STYLE}" if css else HIGHLIGHT_STYLE
            for css in styles.iloc[row]
        ]
    return styles


def render_table(  # noqa: PLR0913 - opções de exibição explícitas
    display: pd.DataFrame,
    colours: Sequence[str],
    *,
    key: str,
    selectable: bool = False,
    highlight: Sequence[int] = (),
    column_styles: Mapping[str, Sequence[str]] | None = None,
    max_rows: int = 25,
    column_config: dict[str, object] | None = None,
) -> list[int]:
    """Tabela com a equipe colorida; retorna as linhas selecionadas.

    O ``st.dataframe`` só aceita estilo por célula, por isso a célula ``Equipe``
    inteira (quadradinho + nome) recebe a cor.
    """
    styles = table_styles(display, colours, highlight, column_styles)
    styled = display.style.apply(lambda _df: styles, axis=None)
    height = ROW_HEIGHT * (min(len(display), max_rows) + 1) + 3
    options: dict[str, object] = {
        "hide_index": True,
        "width": "stretch",
        "height": height,
        "key": key,
        "column_config": _column_config(display, column_config),
    }
    if not selectable:
        st.dataframe(styled, **options)  # type: ignore[call-overload]
        return []
    event = st.dataframe(  # type: ignore[call-overload]
        styled, on_select="rerun", selection_mode="single-row", **options
    )
    selection = getattr(event, "selection", None)
    return [int(r) for r in getattr(selection, "rows", [])]


def nationality_cells(countries: Iterable[object]) -> list[str]:
    """Células da coluna "Nacionalidade" (bandeira embutida + país).

    Nacionalidade desconhecida vira uma imagem transparente: a célula fica
    vazia (o Streamlit escreveria "None" para um valor nulo).
    """
    return [
        flag_country_image(c if isinstance(c, str) else None) or EMPTY_CELL
        for c in countries
    ]


def _column_config(
    display: pd.DataFrame, extra: Mapping[str, object] | None
) -> dict[str, object]:
    config: dict[str, object] = {}
    if NATIONALITY_COLUMN in display.columns:
        config[NATIONALITY_COLUMN] = st.column_config.ImageColumn(
            NATIONALITY_COLUMN, width="medium"
        )
    config.update(extra or {})
    return config
