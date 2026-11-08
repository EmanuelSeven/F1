"""Schemas Pandera dos datasets silver (um por endpoint)."""

from collections.abc import Mapping
from types import MappingProxyType

import pandera.pandas as pa

from f1.domain.endpoints import Endpoint, spec_for

COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN", "TEST_UNKNOWN")
HEX_COLOUR = r"^[0-9A-Fa-f]{6}$"
DATETIME = "datetime64[ns, UTC]"


def _int(*checks: pa.Check) -> pa.Column:
    return pa.Column("Int64", checks=list(checks), nullable=False)


def _opt(dtype: str, *checks: pa.Check) -> pa.Column:
    return pa.Column(dtype, checks=list(checks), nullable=True)


def _req(dtype: str, *checks: pa.Check) -> pa.Column:
    return pa.Column(dtype, checks=list(checks), nullable=False)


def _range(low: float, high: float, *, include_min: bool = True) -> pa.Check:
    return pa.Check.in_range(low, high, include_min=include_min)


def _positive_key() -> pa.Column:
    return _int(pa.Check.ge(1))


def _schema(
    endpoint: Endpoint,
    columns: dict[str, pa.Column],
    checks: list[pa.Check] | None = None,
) -> pa.DataFrameSchema:
    spec = spec_for(endpoint)
    return pa.DataFrameSchema(
        columns=columns,
        checks=checks,
        unique=list(spec.business_key),
        report_duplicates="all",
        strict=True,
        coerce=False,
        ordered=True,
        name=spec.dataset,
    )


def _session_keys() -> dict[str, pa.Column]:
    return {
        "session_key": _positive_key(),
        "meeting_key": _positive_key(),
        "driver_number": _int(_range(1, 99)),
    }


_YEAR = _int(_range(2018, 2100))

_lap_end_after_start = pa.Check(
    lambda df: (
        df["lap_end"].isna()
        | df["lap_start"].isna()
        | (df["lap_end"] >= df["lap_start"])
    ),
    name="lap_end_gte_lap_start",
)

SCHEMAS: Mapping[Endpoint, pa.DataFrameSchema] = MappingProxyType(
    {
        Endpoint.MEETINGS: _schema(
            Endpoint.MEETINGS,
            {
                "meeting_key": _positive_key(),
                "year": _YEAR,
                "meeting_name": _req("string", pa.Check.str_length(min_value=1)),
                "meeting_official_name": _opt("string"),
                "circuit_key": _opt("Int64"),
                "circuit_short_name": _opt("string"),
                "country_code": _opt("string"),
                "country_name": _opt("string"),
                "location": _opt("string"),
                "gmt_offset": _opt("string"),
                "date_start": _req(DATETIME),
                "date_end": _opt(DATETIME),
                "is_cancelled": _opt("boolean"),
            },
        ),
        Endpoint.SESSIONS: _schema(
            Endpoint.SESSIONS,
            {
                "session_key": _positive_key(),
                "meeting_key": _positive_key(),
                "year": _YEAR,
                "session_name": _req("string", pa.Check.str_length(min_value=1)),
                "session_type": _req("string", pa.Check.str_length(min_value=1)),
                "date_start": _req(DATETIME),
                "date_end": _opt(DATETIME),
                "circuit_key": _opt("Int64"),
                "circuit_short_name": _opt("string"),
                "country_name": _opt("string"),
                "location": _opt("string"),
                "gmt_offset": _opt("string"),
                "is_cancelled": _opt("boolean"),
            },
        ),
        Endpoint.DRIVERS: _schema(
            Endpoint.DRIVERS,
            {
                **_session_keys(),
                "name_acronym": _opt("string", pa.Check.str_length(3, 3)),
                "broadcast_name": _opt("string"),
                "full_name": _opt("string"),
                "first_name": _opt("string"),
                "last_name": _opt("string"),
                "team_name": _opt("string"),
                "team_colour": _opt("string", pa.Check.str_matches(HEX_COLOUR)),
                "headshot_url": _opt("string"),
            },
        ),
        Endpoint.SESSION_RESULT: _schema(
            Endpoint.SESSION_RESULT,
            {
                **_session_keys(),
                "position": _opt("Int64", _range(1, 30)),
                "number_of_laps": _opt("Int64", pa.Check.ge(0)),
                "points": _opt("Float64", _range(0, 50)),
                "duration": _opt("Float64", _range(0, 20_000, include_min=False)),
                "gap_to_leader": _opt("string"),
                "dnf": _opt("boolean"),
                "dns": _opt("boolean"),
                "dsq": _opt("boolean"),
            },
        ),
        Endpoint.LAPS: _schema(
            Endpoint.LAPS,
            {
                **_session_keys(),
                "lap_number": _int(_range(1, 100)),
                "date_start": _opt(DATETIME),
                "lap_duration": _opt("Float64", _range(0, 600, include_min=False)),
                "duration_sector_1": _opt("Float64", _range(0, 600, include_min=False)),
                "duration_sector_2": _opt("Float64", _range(0, 600, include_min=False)),
                "duration_sector_3": _opt("Float64", _range(0, 600, include_min=False)),
                "i1_speed": _opt("Int64", _range(0, 400)),
                "i2_speed": _opt("Int64", _range(0, 400)),
                "st_speed": _opt("Int64", _range(0, 400)),
                "is_pit_out_lap": _opt("boolean"),
                "segments_sector_1": _opt("string"),
                "segments_sector_2": _opt("string"),
                "segments_sector_3": _opt("string"),
            },
        ),
        Endpoint.STINTS: _schema(
            Endpoint.STINTS,
            {
                **_session_keys(),
                "stint_number": _int(_range(1, 20)),
                "compound": _opt("string", pa.Check.isin(COMPOUNDS)),
                "lap_start": _opt("Int64", pa.Check.ge(1)),
                "lap_end": _opt("Int64", pa.Check.ge(1)),
                "tyre_age_at_start": _opt("Int64", pa.Check.ge(0)),
            },
            checks=[_lap_end_after_start],
        ),
        Endpoint.PIT: _schema(
            Endpoint.PIT,
            {
                **_session_keys(),
                "lap_number": _int(_range(1, 100)),
                "date": _req(DATETIME),
                "lane_duration": _opt("Float64", _range(0, 600, include_min=False)),
                "stop_duration": _opt("Float64", _range(0, 120, include_min=False)),
            },
        ),
        Endpoint.STARTING_GRID: _schema(
            Endpoint.STARTING_GRID,
            {
                **_session_keys(),
                "position": _opt("Int64", _range(1, 30)),
                "lap_duration": _opt("Float64", _range(0, 600, include_min=False)),
            },
        ),
        Endpoint.WEATHER: _schema(
            Endpoint.WEATHER,
            {
                "session_key": _positive_key(),
                "meeting_key": _positive_key(),
                "date": _req(DATETIME),
                "air_temperature": _opt("Float64", _range(-10, 60)),
                "track_temperature": _opt("Float64", _range(-10, 80)),
                "humidity": _opt("Float64", _range(0, 100)),
                "pressure": _opt("Float64", _range(800, 1100)),
                "wind_speed": _opt("Float64", _range(0, 50)),
                "wind_direction": _opt("Int64", _range(0, 360)),
                "rainfall": _opt("boolean"),
            },
        ),
    }
)


def schema_for(endpoint: Endpoint) -> pa.DataFrameSchema:
    return SCHEMAS[endpoint]
