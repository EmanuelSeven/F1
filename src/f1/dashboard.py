"""Dashboard Streamlit do data lake ``f1``.

Execução: ``poetry run streamlit run src/f1/dashboard.py``.

Este arquivo contém apenas apresentação; leitura e agregação ficam em
``f1.dashboard.loaders``. Como o pacote ``f1/dashboard/`` tem o mesmo nome de
módulo, este arquivo é executado pelo caminho (não por import) e é checado pelo
MyPy em uma etapa própria (``mypy src/f1/dashboard.py``).
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

from f1 import __version__
from f1.config.settings import get_settings
from f1.dashboard.loaders import (
    PlatformSummary,
    datasets_table,
    layers_table,
    load_platform_summary,
)

CACHE_TTL_SECONDS = 60


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Lendo o data lake...")
def _cached_summary(data_dir: Path) -> PlatformSummary:
    return load_platform_summary(data_dir)


def _format_datetime(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S UTC") if value else "—"


def render_metrics(summary: PlatformSummary) -> None:
    st.subheader("Métricas gerais")
    files, processed, rejected = st.columns(3)
    files.metric("Arquivos na bronze", f"{summary.bronze_files:,}")
    processed.metric("Registros processados", f"{summary.records_processed:,}")
    rejected.metric("Registros rejeitados", f"{summary.records_rejected:,}")

    run_id, last_run = st.columns(2)
    run_id.metric("Último run_id", summary.last_run.run_id if summary.last_run else "—")
    last_run.metric(
        "Última execução",
        _format_datetime(summary.last_run.ingested_at if summary.last_run else None),
    )


def render_layers(summary: PlatformSummary) -> None:
    st.subheader("Estado das camadas")
    st.dataframe(layers_table(summary), hide_index=True, width="stretch")


def render_datasets(summary: PlatformSummary) -> None:
    st.subheader("Datasets silver")
    st.dataframe(datasets_table(summary), hide_index=True, width="stretch")


def main() -> None:
    st.set_page_config(page_title="F1 — Data Lake", page_icon="🏁", layout="wide")
    st.title("F1 — Data Lake OpenF1")
    st.caption(f"Versão {__version__} · bronze → silver → quarentena")

    data_dir = get_settings().data_dir
    if st.button("Recarregar dados"):
        _cached_summary.clear()
    summary = _cached_summary(data_dir)

    if not any(layer.exists for layer in summary.layers):
        st.info(
            f"Nenhum dado encontrado em `{data_dir}`. "
            "Execute, por exemplo, `poetry run python -m f1 calendar --year 2024`."
        )
    render_metrics(summary)
    render_layers(summary)
    render_datasets(summary)


if __name__ == "__main__":
    main()
