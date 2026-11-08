"""Conversão de datas ISO 8601 para UTC."""

from datetime import UTC, datetime


def parse_utc(value: str) -> datetime:
    """Converte uma string ISO 8601 em ``datetime`` com fuso UTC.

    Valores sem fuso horário são interpretados como UTC.
    """
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
