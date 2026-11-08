"""Tabelas do dashboard: equipe com quadradinho colorido e linhas em destaque."""

from collections.abc import Sequence

import pandas as pd
import streamlit as st

ROW_HEIGHT = 35
SQUARE = "■"
TEAM_COLUMN = "Equipe"
HIGHLIGHT_STYLE = "background-color: rgba(225, 6, 0, 0.22)"


def team_label(team: object) -> str:
    """Equipe com o quadradinho de cor: ``"■ Red Bull Racing"``."""
    return f"{SQUARE} {team}"


def table_styles(
    display: pd.DataFrame, colours: Sequence[str], highlight: Sequence[int] = ()
) -> pd.DataFrame:
    """CSS por célula: cor da equipe na coluna ``Equipe`` e linhas em destaque."""
    styles = pd.DataFrame("", index=display.index, columns=display.columns)
    if TEAM_COLUMN in styles.columns:
        styles[TEAM_COLUMN] = [f"color: {c}" for c in colours]
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
    max_rows: int = 25,
    column_config: dict[str, object] | None = None,
) -> list[int]:
    """Tabela com a equipe colorida; retorna as linhas selecionadas.

    O ``st.dataframe`` só aceita estilo por célula, por isso a célula ``Equipe``
    inteira (quadradinho + nome) recebe a cor.
    """
    styles = table_styles(display, colours, highlight)
    styled = display.style.apply(lambda _df: styles, axis=None)
    height = ROW_HEIGHT * (min(len(display), max_rows) + 1) + 3
    options: dict[str, object] = {
        "hide_index": True,
        "width": "stretch",
        "height": height,
        "key": key,
        "column_config": dict(column_config or {}),
    }
    if not selectable:
        st.dataframe(styled, **options)  # type: ignore[call-overload]
        return []
    event = st.dataframe(  # type: ignore[call-overload]
        styled, on_select="rerun", selection_mode="single-row", **options
    )
    selection = getattr(event, "selection", None)
    return [int(r) for r in getattr(selection, "rows", [])]
