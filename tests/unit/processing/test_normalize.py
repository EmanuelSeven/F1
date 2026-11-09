import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from f1.domain.endpoints import Endpoint
from f1.processing.normalize import (
    COLUMNS,
    Col,
    MissingFieldsError,
    normalize,
    normalize_records,
)
from tests.conftest import load_fixture


@pytest.mark.parametrize("endpoint", list(Endpoint))
def test_normalize_fixture_has_declared_columns_and_dtypes(endpoint):
    df = normalize(endpoint, load_fixture(endpoint))

    assert list(df.columns) == [c.name for c in COLUMNS[endpoint]]
    assert {c: str(t) for c, t in df.dtypes.items()} == {
        c.name: c.dtype for c in COLUMNS[endpoint]
    }
    assert len(df) == len(load_fixture(endpoint))


@pytest.mark.parametrize("endpoint", list(Endpoint))
def test_normalize_empty_payload_keeps_typed_columns(endpoint):
    df = normalize(endpoint, [])

    assert df.empty
    assert [str(t) for t in df.dtypes] == [c.dtype for c in COLUMNS[endpoint]]


def test_normalize_drops_deprecated_fields():
    drivers = normalize(Endpoint.DRIVERS, load_fixture(Endpoint.DRIVERS))
    assert drivers["country_code"].tolist()[:2] == ["NED", "ESP"]  # p/ bandeira
    assert "pit_duration" not in normalize(Endpoint.PIT, load_fixture(Endpoint.PIT))


def test_normalize_session_result_takes_last_non_null_value():
    df = normalize(Endpoint.SESSION_RESULT, load_fixture(Endpoint.SESSION_RESULT))

    assert df["duration"].tolist() == [90.984, 91.613, 6278.123, 6299.564]
    assert df["gap_to_leader"].tolist() == ["0", "0.289", "0", "21.441"]


def test_normalize_laps_types_dates_and_segments():
    df = normalize(Endpoint.LAPS, load_fixture(Endpoint.LAPS))

    assert pd.isna(df.loc[0, "lap_duration"])
    assert pd.isna(df.loc[0, "date_start"])
    assert df.loc[1, "date_start"] == datetime(
        2023, 9, 16, 13, 5, 12, 300000, tzinfo=UTC
    )
    assert json.loads(df.loc[0, "segments_sector_1"]) == [None, 2049, 2049]
    assert pd.isna(df.loc[2, "segments_sector_1"])


def test_normalize_weather_rainfall_to_boolean():
    df = normalize(Endpoint.WEATHER, load_fixture(Endpoint.WEATHER))
    assert df["rainfall"].tolist() == [False, False, False, True]


def test_normalize_coerces_invalid_values_to_null():
    columns = (
        Col("i", "int"),
        Col("b", "bool"),
        Col("d", "datetime"),
        Col("s", "str"),
    )
    df = normalize_records(
        columns,
        [
            {"i": 1.5, "b": "yes", "d": "not-a-date", "s": 7},
            {"i": "3", "b": "TRUE", "d": 123, "s": None},
        ],
    )

    assert df["i"].isna().tolist() == [True, False]
    assert df["b"].tolist()[1] is True
    assert pd.isna(df.loc[0, "b"])
    assert df["d"].isna().all()
    assert df.loc[0, "s"] == "7"


def test_normalize_raises_when_required_field_missing_everywhere():
    with pytest.raises(MissingFieldsError, match="lap_number"):
        normalize(
            Endpoint.LAPS, [{"session_key": 1, "meeting_key": 1, "driver_number": 1}]
        )
