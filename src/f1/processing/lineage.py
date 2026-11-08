"""Colunas técnicas de linhagem (``_run_id``, ``_ingested_at``, ``_source``)."""

from datetime import UTC, datetime

import pandas as pd

from f1.domain.models import INGESTED_AT, RUN_ID, SOURCE


def add_lineage_columns(
    df: pd.DataFrame,
    run_id: str,
    source: str,
    ingested_at: datetime | None = None,
) -> pd.DataFrame:
    """Retorna uma cópia de ``df`` com as colunas de linhagem (UTC)."""
    timestamp = (ingested_at or datetime.now(UTC)).astimezone(UTC)
    size = len(df)
    out = df.copy()
    out[RUN_ID] = pd.Series([run_id] * size, index=df.index, dtype="string")
    out[INGESTED_AT] = pd.Series(
        [timestamp] * size, index=df.index, dtype="datetime64[ns, UTC]"
    )
    out[SOURCE] = pd.Series([source] * size, index=df.index, dtype="string")
    return out
