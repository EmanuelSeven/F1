import pandas as pd
import pytest
from pandera.errors import SchemaErrors

from f1.domain.endpoints import Endpoint
from f1.processing.normalize import normalize
from f1.quality.schemas import schema_for
from f1.quality.validation import DataQualityError, ValidationResult, validate
from tests.conftest import load_fixture

SCHEMA = schema_for(Endpoint.LAPS)


def _laps(copies: int = 1) -> pd.DataFrame:
    base = normalize(Endpoint.LAPS, load_fixture(Endpoint.LAPS))
    frames = []
    for i in range(copies):
        frame = base.copy()
        frame["session_key"] = frame["session_key"] + i * 10_000
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def test_validate_all_valid():
    result = validate(_laps(), SCHEMA, max_rejection_rate=0.05)

    assert len(result.valid) == 8
    assert result.rejected.empty
    assert "_reject_reason" in result.rejected.columns
    assert result.rejection_rate == 0.0


def test_validate_routes_invalid_rows_with_reason():
    df = _laps(copies=3)  # 24 linhas
    df.loc[5, "lap_number"] = 0

    result = validate(df, SCHEMA, max_rejection_rate=0.05)

    assert len(result.valid) == 23
    assert result.rejected.index.tolist() == [5]
    assert result.rejected.loc[5, "_reject_reason"].startswith("lap_number:in_range")


def test_validate_combines_reasons_and_duplicates():
    df = pd.concat([_laps(), _laps().iloc[[1]]], ignore_index=True)
    df.loc[1, "st_speed"] = 999

    result = validate(df, SCHEMA, max_rejection_rate=1.0)

    assert sorted(result.rejected.index) == [1, 8]
    reason = result.rejected.loc[1, "_reject_reason"]
    assert "multiple_fields_uniqueness" in reason
    assert "st_speed:in_range" in reason


def test_validate_raises_above_rejection_rate_with_result():
    df = _laps()
    df.loc[0, "lap_number"] = 0

    with pytest.raises(DataQualityError, match=r"laps: rejection rate 12.5%") as exc:
        validate(df, SCHEMA, max_rejection_rate=0.05)
    assert len(exc.value.result.rejected) == 1


def test_validate_schema_violation_raises_immediately():
    with pytest.raises(SchemaErrors):
        validate(_laps().drop(columns=["st_speed"]), SCHEMA, max_rejection_rate=1.0)


@pytest.mark.parametrize(
    ("pressure", "valid"),
    [
        (781.4, True),  # Cidade do México, ~2.240 m (GP 2026)
        (930.0, True),  # Interlagos, ~760 m
        (1013.0, True),  # nível do mar
        (650.0, False),  # abaixo de qualquer circuito
        (1200.0, False),
    ],
)
def test_weather_pressure_accepts_altitude_circuits(pressure, valid):
    weather = normalize(Endpoint.WEATHER, load_fixture(Endpoint.WEATHER))
    weather["pressure"] = pressure

    result = validate(weather, schema_for(Endpoint.WEATHER), max_rejection_rate=1.0)

    assert result.rejected.empty is valid


def test_validation_result_empty_rate():
    empty = pd.DataFrame()
    assert ValidationResult(empty, empty).rejection_rate == 0.0
