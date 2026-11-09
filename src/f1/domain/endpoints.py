"""Endpoints da OpenF1 cobertos pelo projeto e metadados dos datasets silver."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Endpoint(StrEnum):
    MEETINGS = "meetings"
    SESSIONS = "sessions"
    DRIVERS = "drivers"
    SESSION_RESULT = "session_result"
    LAPS = "laps"
    STINTS = "stints"
    PIT = "pit"
    WEATHER = "weather"
    STARTING_GRID = "starting_grid"


class PartitionLevel(StrEnum):
    SEASON = "season"
    MEETING = "meeting"


@dataclass(frozen=True)
class DatasetSpec:
    endpoint: Endpoint
    dataset: str
    business_key: tuple[str, ...]
    partition_level: PartitionLevel
    # Buscado por sessão (padrão) ou uma vez por meeting (ex.: grade de
    # largada, que a OpenF1 associa à sessão de classificação).
    per_session: bool = True


def _spec(
    endpoint: Endpoint,
    dataset: str,
    key: tuple[str, ...],
    level: PartitionLevel,
    *,
    per_session: bool = True,
) -> tuple[Endpoint, DatasetSpec]:
    return endpoint, DatasetSpec(endpoint, dataset, key, level, per_session)


_SESSION_KEY = ("session_key", "driver_number")

DATASET_SPECS: Mapping[Endpoint, DatasetSpec] = MappingProxyType(
    dict(
        [
            _spec(
                Endpoint.MEETINGS, "meetings", ("meeting_key",), PartitionLevel.SEASON
            ),
            _spec(
                Endpoint.SESSIONS, "sessions", ("session_key",), PartitionLevel.SEASON
            ),
            _spec(Endpoint.DRIVERS, "drivers", _SESSION_KEY, PartitionLevel.MEETING),
            _spec(
                Endpoint.SESSION_RESULT,
                "session_results",
                _SESSION_KEY,
                PartitionLevel.MEETING,
            ),
            _spec(
                Endpoint.LAPS,
                "laps",
                (*_SESSION_KEY, "lap_number"),
                PartitionLevel.MEETING,
            ),
            _spec(
                Endpoint.STINTS,
                "stints",
                (*_SESSION_KEY, "stint_number"),
                PartitionLevel.MEETING,
            ),
            _spec(
                Endpoint.PIT,
                "pit_stops",
                (*_SESSION_KEY, "lap_number"),
                PartitionLevel.MEETING,
            ),
            _spec(
                Endpoint.WEATHER,
                "weather",
                ("session_key", "date"),
                PartitionLevel.MEETING,
            ),
            _spec(
                Endpoint.STARTING_GRID,
                "starting_grid",
                ("session_key", "driver_number"),
                PartitionLevel.MEETING,
                per_session=False,
            ),
        ]
    )
)

CALENDAR_ENDPOINTS: tuple[Endpoint, ...] = tuple(
    e for e, s in DATASET_SPECS.items() if s.partition_level is PartitionLevel.SEASON
)
SESSION_ENDPOINTS: tuple[Endpoint, ...] = tuple(
    e
    for e, s in DATASET_SPECS.items()
    if s.partition_level is PartitionLevel.MEETING and s.per_session
)
MEETING_ENDPOINTS: tuple[Endpoint, ...] = tuple(
    e
    for e, s in DATASET_SPECS.items()
    if s.partition_level is PartitionLevel.MEETING and not s.per_session
)


def spec_for(endpoint: Endpoint) -> DatasetSpec:
    """Retorna os metadados do dataset silver de um endpoint."""
    return DATASET_SPECS[endpoint]


def parse_endpoints(names: Iterable[str]) -> tuple[Endpoint, ...]:
    """Converte nomes de endpoint ou de dataset silver em ``Endpoint``.

    Raises:
        ValueError: se algum nome for desconhecido.
    """
    lookup = {e.value: e for e in Endpoint} | {
        s.dataset: e for e, s in DATASET_SPECS.items()
    }
    result: list[Endpoint] = []
    for raw in names:
        name = raw.strip().lower()
        if name not in lookup:
            raise ValueError(f"unknown dataset: {raw!r}")
        if lookup[name] not in result:
            result.append(lookup[name])
    return tuple(result)
