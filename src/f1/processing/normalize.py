"""Normalização: registros brutos da API → DataFrame tipado por dataset.

Cada dataset declara suas colunas (nome, tipo e obrigatoriedade). Campos não
declarados, incluindo os depreciados (``country_code`` em drivers e
``pit_duration`` em pit), são descartados.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

import pandas as pd

from f1.domain.endpoints import Endpoint
from f1.domain.models import Record
from f1.utils.dates import parse_utc

type ColumnKind = Literal[
    "int", "float", "str", "bool", "datetime", "json", "last_float", "last_str"
]

DTYPES: Mapping[ColumnKind, str] = MappingProxyType(
    {
        "int": "Int64",
        "float": "Float64",
        "str": "string",
        "bool": "boolean",
        "datetime": "datetime64[ns, UTC]",
        "json": "string",
        "last_float": "Float64",
        "last_str": "string",
    }
)


@dataclass(frozen=True)
class Col:
    name: str
    kind: ColumnKind
    required: bool = False

    @property
    def dtype(self) -> str:
        return DTYPES[self.kind]


class MissingFieldsError(ValueError):
    """Campos obrigatórios ausentes em todo o payload (violação de schema)."""


def _keys(*names: str) -> tuple[Col, ...]:
    return tuple(Col(name, "int", required=True) for name in names)


def _cols(kind: ColumnKind, *names: str) -> tuple[Col, ...]:
    return tuple(Col(name, kind) for name in names)


COLUMNS: Mapping[Endpoint, tuple[Col, ...]] = MappingProxyType(
    {
        Endpoint.MEETINGS: (
            *_keys("meeting_key", "year"),
            Col("meeting_name", "str", required=True),
            *_cols("str", "meeting_official_name"),
            Col("circuit_key", "int"),
            *_cols(
                "str",
                "circuit_short_name",
                "country_code",
                "country_name",
                "location",
                "gmt_offset",
            ),
            Col("date_start", "datetime", required=True),
            Col("date_end", "datetime"),
            Col("is_cancelled", "bool"),
        ),
        Endpoint.SESSIONS: (
            *_keys("session_key", "meeting_key", "year"),
            Col("session_name", "str", required=True),
            Col("session_type", "str", required=True),
            Col("date_start", "datetime", required=True),
            Col("date_end", "datetime"),
            Col("circuit_key", "int"),
            *_cols("str", "circuit_short_name", "country_name", "location"),
            Col("gmt_offset", "str"),
            Col("is_cancelled", "bool"),
        ),
        Endpoint.DRIVERS: (
            *_keys("session_key", "meeting_key", "driver_number"),
            *_cols(
                "str",
                "name_acronym",
                "broadcast_name",
                "full_name",
                "first_name",
                "last_name",
                "team_name",
                "team_colour",
                "headshot_url",
            ),
        ),
        Endpoint.SESSION_RESULT: (
            *_keys("session_key", "meeting_key", "driver_number"),
            *_cols("int", "position", "number_of_laps"),
            Col("duration", "last_float"),
            Col("gap_to_leader", "last_str"),
            *_cols("bool", "dnf", "dns", "dsq"),
        ),
        Endpoint.LAPS: (
            *_keys("session_key", "meeting_key", "driver_number", "lap_number"),
            Col("date_start", "datetime"),
            *_cols(
                "float",
                "lap_duration",
                "duration_sector_1",
                "duration_sector_2",
                "duration_sector_3",
            ),
            *_cols("int", "i1_speed", "i2_speed", "st_speed"),
            Col("is_pit_out_lap", "bool"),
            *_cols(
                "json", "segments_sector_1", "segments_sector_2", "segments_sector_3"
            ),
        ),
        Endpoint.STINTS: (
            *_keys("session_key", "meeting_key", "driver_number", "stint_number"),
            Col("compound", "str"),
            *_cols("int", "lap_start", "lap_end", "tyre_age_at_start"),
        ),
        Endpoint.PIT: (
            *_keys("session_key", "meeting_key", "driver_number", "lap_number"),
            Col("date", "datetime", required=True),
            *_cols("float", "lane_duration", "stop_duration"),
        ),
        Endpoint.WEATHER: (
            *_keys("session_key", "meeting_key"),
            Col("date", "datetime", required=True),
            *_cols(
                "float",
                "air_temperature",
                "track_temperature",
                "humidity",
                "pressure",
                "wind_speed",
            ),
            Col("wind_direction", "int"),
            Col("rainfall", "bool"),
        ),
    }
)


def normalize(endpoint: Endpoint, records: Sequence[Record]) -> pd.DataFrame:
    """Normaliza os registros de um endpoint (função pura)."""
    return normalize_records(COLUMNS[endpoint], records)


def normalize_records(
    columns: Sequence[Col], records: Sequence[Record]
) -> pd.DataFrame:
    """Seleciona, ordena e tipa as colunas declaradas."""
    present = set().union(*(r.keys() for r in records)) if records else set()
    missing = [
        c.name for c in columns if c.required and records and c.name not in present
    ]
    if missing:
        raise MissingFieldsError(f"required fields missing from payload: {missing}")
    index = pd.RangeIndex(len(records))
    data = {
        col.name: _CASTERS[col.kind](
            pd.Series([r.get(col.name) for r in records], index=index, dtype=object)
        )
        for col in columns
    }
    return pd.DataFrame(data, index=index)


def _apply(series: pd.Series, func: Callable[[object], object]) -> pd.Series:
    """Aplica ``func`` elemento a elemento mantendo dtype ``object``.

    ``Series.map`` infere o dtype do resultado (ex.: ``0`` vira ``0.0``).
    """
    return pd.Series([func(v) for v in series], index=series.index, dtype=object)


def _last(value: object) -> object:
    if isinstance(value, list):
        return next((v for v in reversed(value) if v is not None), None)
    return value


def _to_int(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.where(numeric % 1 == 0).astype("Int64")


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Float64")


def _to_str(series: pd.Series) -> pd.Series:
    return _apply(series, lambda v: None if v is None else str(v)).astype("string")


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return None


def _to_bool(series: pd.Series) -> pd.Series:
    return _apply(series, _bool_value).astype("boolean")


def _datetime_value(value: object) -> object:
    if not isinstance(value, str):
        return None
    try:
        return parse_utc(value)
    except ValueError:
        return None


def _to_datetime(series: pd.Series) -> pd.Series:
    parsed = _apply(series, _datetime_value)
    return pd.to_datetime(parsed, utc=True).astype("datetime64[ns, UTC]")


def _to_json(series: pd.Series) -> pd.Series:
    return _apply(series, lambda v: None if v is None else json.dumps(v)).astype(
        "string"
    )


_CASTERS: Mapping[ColumnKind, Callable[[pd.Series], pd.Series]] = MappingProxyType(
    {
        "int": _to_int,
        "float": _to_float,
        "str": _to_str,
        "bool": _to_bool,
        "datetime": _to_datetime,
        "json": _to_json,
        "last_float": lambda s: _to_float(_apply(s, _last)),
        "last_str": lambda s: _to_str(_apply(s, _last)),
    }
)
