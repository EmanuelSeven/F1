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
from f1.dashboard.views.latest import render_latest
from f1.dashboard.views.season import render_season
from f1.dashboard.views.sidebar import (
    LAKE_PAGE,
    LAPS_PAGE,
    LATEST_PAGE,
    SEASON_PAGE,
    PageFilters,
    render_sidebar_filters,
    render_sidebar_footer,
)
from f1.dashboard.views.theme import inject_css, prevent_translation
from f1.dashboard.visits import session_page_views

LATEST_TITLE = "Última corrida"
SEASON_TITLE = "Temporada"
LAPS_TITLE = "Voltas"
LAKE_TITLE = "Data Lake"
PAGE_FILTERS: dict[str, PageFilters] = {
    LATEST_TITLE: LATEST_PAGE,
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
            render_latest,
            title=LATEST_TITLE,
            icon="🏁",
            url_path="ultima-corrida",
            default=True,
        ),
        st.Page(render_season, title=SEASON_TITLE, icon="🏆", url_path="temporada"),
        st.Page(render_laps, title=LAPS_TITLE, icon="⏱️", url_path="voltas"),
        st.Page(render_lake, title=LAKE_TITLE, icon="🗄️", url_path="data-lake"),
    ]
    # A navegação é desenhada na barra lateral (acima dos filtros) pela própria
    # barra lateral; aqui ela só registra as páginas.
    navigation = st.navigation(pages, position="hidden")
    settings = get_settings()
    data_dir = settings.data_dir
    # Barra lateral comum; cada página declara quais filtros usa.
    render_sidebar_filters(data_dir, PAGE_FILTERS[navigation.title], pages)
    navigation.run()
    # Depois da página: a requisição ao contador não atrasa o conteúdo.
    render_sidebar_footer(data_dir, session_page_views(settings))


if __name__ == "__main__":
    main()
