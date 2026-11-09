"""Página "Data Lake": estado das camadas bronze, silver e quarentena."""

from datetime import UTC, datetime

import streamlit as st

from f1 import __version__
from f1.config.settings import get_settings
from f1.dashboard.loaders import (
    PlatformSummary,
    datasets_table,
    is_lake_empty,
    layers_table,
)
from f1.dashboard.views.data import lake_summary


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


def render_lake() -> None:
    """Conteúdo da página "Data Lake"."""
    st.title("F1 — Data Lake OpenF1")
    st.caption(f"Versão {__version__} · bronze → silver → quarentena")

    data_dir = get_settings().data_dir
    if st.button("Recarregar dados"):
        lake_summary.clear()
    summary = lake_summary(data_dir)

    if is_lake_empty(data_dir):
        st.info(
            f"Nenhum dado encontrado em `{data_dir}`. Abra a página **Temporada** "
            "para carregar a temporada automaticamente, ou execute "
            f"`poetry run python -m f1 calendar --year {datetime.now(UTC).year}`."
        )
    render_metrics(summary)
    render_layers(summary)
    render_datasets(summary)
