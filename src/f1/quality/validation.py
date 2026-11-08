"""Validação de DataFrames com Pandera, separando válidos e rejeitados."""

from dataclasses import dataclass

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from f1.domain.models import REJECT_REASON


@dataclass(frozen=True)
class ValidationResult:
    valid: pd.DataFrame
    rejected: pd.DataFrame  # mesmas colunas + ``_reject_reason``

    @property
    def total(self) -> int:
        return len(self.valid) + len(self.rejected)

    @property
    def rejection_rate(self) -> float:
        return len(self.rejected) / self.total if self.total else 0.0


class DataQualityError(Exception):
    """Taxa de rejeição acima do limite aceitável."""

    def __init__(self, message: str, result: ValidationResult) -> None:
        super().__init__(message)
        self.result = result


def validate(
    df: pd.DataFrame, schema: pa.DataFrameSchema, max_rejection_rate: float
) -> ValidationResult:
    """Valida ``df``; linhas inválidas vão para ``rejected`` com o motivo.

    Raises:
        SchemaErrors: violação de schema (coluna ausente/extra, tipo) — sem
            índice de linha, interrompe a pipeline imediatamente.
        DataQualityError: taxa de rejeição acima de ``max_rejection_rate``.
    """
    try:
        valid = schema.validate(df, lazy=True)
        return ValidationResult(valid=valid, rejected=_with_reasons(df.iloc[0:0], {}))
    except SchemaErrors as exc:
        failures = exc.failure_cases
        if failures["index"].isna().any():
            raise
    reasons = _reasons_by_row(failures)
    mask = df.index.isin(list(reasons))
    result = ValidationResult(
        valid=df.loc[~mask], rejected=_with_reasons(df.loc[mask], reasons)
    )
    if result.rejection_rate > max_rejection_rate:
        raise DataQualityError(
            f"{schema.name}: rejection rate {result.rejection_rate:.1%} above "
            f"{max_rejection_rate:.0%}",
            result,
        )
    return result


def _reasons_by_row(failures: pd.DataFrame) -> dict[int, str]:
    reasons: dict[int, set[str]] = {}
    for row in failures.to_dict("records"):
        column = (
            row["column"] if isinstance(row["column"], str) else row["schema_context"]
        )
        reasons.setdefault(int(row["index"]), set()).add(f"{column}:{row['check']}")
    return {idx: "; ".join(sorted(items)) for idx, items in reasons.items()}


def _with_reasons(df: pd.DataFrame, reasons: dict[int, str]) -> pd.DataFrame:
    out = df.copy()
    out[REJECT_REASON] = pd.Series(
        [reasons.get(int(idx)) for idx in df.index], index=df.index, dtype="string"
    )
    return out
