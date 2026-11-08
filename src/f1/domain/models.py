"""Entidades de domínio, sem I/O."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

type Record = dict[str, object]
type FilterScalar = str | int | float | bool | datetime

LATEST = "latest"


class Operator(StrEnum):
    EQ = "="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="


@dataclass(frozen=True)
class Filter:
    """Filtro de consulta: ``field`` ``op`` ``value``.

    Uma tupla em ``value`` representa múltiplos valores (somente com ``=``).
    """

    field: str
    value: FilterScalar | tuple[FilterScalar, ...]
    op: Operator = Operator.EQ

    def __post_init__(self) -> None:
        if not self.field:
            raise ValueError("filter field must not be empty")
        if isinstance(self.value, tuple):
            if not self.value:
                raise ValueError("multi-value filter needs at least one value")
            if self.op is not Operator.EQ:
                raise ValueError("multi-value filters only support '='")

    def values(self) -> tuple[FilterScalar, ...]:
        return self.value if isinstance(self.value, tuple) else (self.value,)


@dataclass(frozen=True)
class Partition:
    season: int
    meeting_key: int | None = None

    def segments(self) -> tuple[str, ...]:
        parts = [f"season={self.season}"]
        if self.meeting_key is not None:
            parts.append(f"meeting_key={self.meeting_key}")
        return tuple(parts)

    def __str__(self) -> str:
        return "/".join(self.segments())


@dataclass(frozen=True)
class MeetingRef:
    meeting_key: int
    year: int
    name: str
    ends_at: datetime | None = None
    is_cancelled: bool = False

    def is_finished(self, now: datetime) -> bool:
        return self.ends_at is not None and self.ends_at <= now

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "MeetingRef":
        return cls(
            meeting_key=as_int(record, "meeting_key"),
            year=as_int(record, "year"),
            name=str(record.get("meeting_name") or ""),
            ends_at=_as_datetime(record.get("date_end") or record.get("date_start")),
            is_cancelled=record.get("is_cancelled") is True,
        )


@dataclass(frozen=True)
class SessionRef:
    session_key: int
    meeting_key: int
    session_name: str
    session_type: str
    is_cancelled: bool = False

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "SessionRef":
        return cls(
            session_key=as_int(record, "session_key"),
            meeting_key=as_int(record, "meeting_key"),
            session_name=str(record.get("session_name") or ""),
            session_type=str(record.get("session_type") or ""),
            is_cancelled=record.get("is_cancelled") is True,
        )


def as_int(record: Mapping[str, object], field: str) -> int:
    """Lê um campo inteiro obrigatório de um registro bruto."""
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"field {field!r} must be an integer, got {value!r}")
    return int(value)


def _as_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
