"""Montagem da query string da OpenF1.

O ``params`` do httpx não expressa operadores como ``speed>=315``, por isso a
query é montada aqui, com URL-encoding de cada parte.
"""

from collections.abc import Sequence
from datetime import datetime
from urllib.parse import quote

from f1.domain.models import Filter, FilterScalar, Operator


def format_value(value: FilterScalar) -> str:
    """Converte um valor de filtro para o formato aceito pela API."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def build_query(filters: Sequence[Filter]) -> str:
    """Monta a query string (sem ``?``) a partir dos filtros, na ordem dada."""
    parts: list[str] = []
    for item in filters:
        field = quote(item.field, safe="_")
        separator = "=" if item.op is Operator.EQ else quote(item.op.value, safe="")
        parts.extend(
            f"{field}{separator}{quote(format_value(value), safe='')}"
            for value in item.values()
        )
    return "&".join(parts)
