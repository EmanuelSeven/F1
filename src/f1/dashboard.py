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

from f1.dashboard.views.lake import render_lake
from f1.dashboard.views.season import render_season
from f1.dashboard.views.theme import inject_css, prevent_translation


def main() -> None:
    st.set_page_config(
        page_title="Fórmula 1 — Dashboard", page_icon="🏁", layout="wide"
    )
    inject_css()
    prevent_translation()
    pages = [
        st.Page(
            render_season,
            title="Temporada",
            icon="🏁",
            url_path="temporada",
            default=True,
        ),
        st.Page(render_lake, title="Data Lake", icon="🗄️", url_path="data-lake"),
    ]
    st.navigation(pages, position="top").run()


if __name__ == "__main__":
    main()
