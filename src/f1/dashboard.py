"""Dashboard - Fórmula 1``.

Execução: ``poetry run streamlit run src/f1/dashboard.py``.

Roteador multipage: configura a página, aplica o tema e registra as páginas
"Temporada" (principal) e "Data Lake". O conteúdo de cada página fica em
``f1.dashboard.views``; leitura e agregação em ``f1.dashboard.loaders`` e
``f1.processing.standings``.

Como o pacote ``f1/dashboard/`` tem o mesmo nome de módulo, este arquivo é
executado pelo caminho (não por import) e é checado pelo MyPy em uma etapa
própria (``mypy src/f1/dashboard.py``).
"""

import streamlit as st

from f1.config.settings import get_settings
from f1.dashboard.views.lake import render_lake
from f1.dashboard.views.laps import render_laps
from f1.dashboard.views.season import render_season
from f1.dashboard.views.sidebar import (
    LAKE_PAGE,
    LAPS_PAGE,
    SEASON_PAGE,
    PageFilters,
    render_sidebar_filters,
    render_sidebar_footer,
)
from f1.dashboard.views.theme import inject_css, prevent_translation

SEASON_TITLE = "Temporada"
LAPS_TITLE = "Voltas"
LAKE_TITLE = "Data Lake"
PAGE_FILTERS: dict[str, PageFilters] = {
    SEASON_TITLE: SEASON_PAGE,
    LAPS_TITLE: LAPS_PAGE,
    LAKE_TITLE: LAKE_PAGE,
}


def main() -> None:
    st.set_page_config(
        page_title="Fórmula 1 — Dashboard", page_icon="🏁", layout="wide"
    )
    inject_css()
    prevent_translation()
    pages = [
        st.Page(
            render_season,
            title=SEASON_TITLE,
            icon="🏁",
            url_path="temporada",
            default=True,
        ),
        st.Page(render_laps, title=LAPS_TITLE, icon="⏱️", url_path="voltas"),
        st.Page(render_lake, title=LAKE_TITLE, icon="🗄️", url_path="data-lake"),
    ]
    navigation = st.navigation(pages, position="top")
    data_dir = get_settings().data_dir
    # Barra lateral comum; cada página declara quais filtros usa.
    render_sidebar_filters(data_dir, PAGE_FILTERS[navigation.title])
    navigation.run()
    render_sidebar_footer(data_dir)


if __name__ == "__main__":
    main()
