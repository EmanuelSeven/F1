"""Página "Data Lake": estado das camadas bronze, silver e quarentena."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from f1 import __version__
from f1.config.settings import get_settings
from f1.dashboard.loaders import (
    PlatformSummary,
    datasets_table,
    is_lake_empty,
    layers_table,
    rejection_totals,
    rejection_trend,
)
from f1.dashboard.views import charts
from f1.dashboard.views.data import lake_summary, rejection_history


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


ALL_PARTITIONS = "Todas"
PLOT_CONFIG = {"displayModeBar": False}


def default_dataset(history: pd.DataFrame) -> str:
    """Dataset com mais rejeições no histórico (o primeiro, em caso de empate)."""
    totals = history.groupby("dataset")["rejected"].sum().sort_index()
    return str(totals.idxmax())


def render_rejection_history(data_dir: Path) -> None:
    st.subheader("Histórico de rejeições")
    st.caption(
        "Taxa de registros rejeitados em cada carga: total e por regra violada. "
        "A quarentena guarda só a última carga; este histórico guarda todas."
    )
    history = rejection_history(data_dir)
    if history.empty:
        st.info("Nenhuma carga registrada no histórico ainda.")
        return

    datasets = sorted(history["dataset"].unique())
    dataset_col, partition_col = st.columns(2)
    dataset = dataset_col.selectbox(
        "Dataset",
        datasets,
        index=datasets.index(default_dataset(history)),
        key="rejections_dataset",
    )
    keys = history.loc[history["dataset"] == dataset, "meeting_key"].dropna()
    options: list[str | int] = [ALL_PARTITIONS, *sorted(int(k) for k in keys.unique())]
    choice = partition_col.selectbox(
        "Meeting",
        options,
        key=f"rejections_meeting_{dataset}",
        disabled=len(options) == 1,
        help="Filtre um meeting para separar reprocessamentos de partições novas.",
    )
    meeting_key = None if choice == ALL_PARTITIONS else int(choice)

    totals = rejection_totals(history, dataset, meeting_key)
    trend = rejection_trend(history, dataset, meeting_key)
    if trend.empty:
        st.success(f"Nenhuma rejeição em {len(totals)} carga(s) de `{dataset}`.")
    st.plotly_chart(
        charts.rejection_trend_chart(totals, trend),
        config=PLOT_CONFIG,
        key=f"rejections_{dataset}_{choice}",
        alt=f"Taxa de rejeição ao longo das cargas de {dataset}, total e por regra",
    )


def render_lake() -> None:
    """Conteúdo da página "Data Lake"."""
    st.title("F1 — Data Lake OpenF1")
    st.caption(f"Versão {__version__} · bronze → silver → quarentena")

    data_dir = get_settings().data_dir
    if st.button("Recarregar dados"):
        lake_summary.clear()
        rejection_history.clear()
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
    render_rejection_history(data_dir)
