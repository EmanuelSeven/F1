import pandas as pd
import pytest
from pandera.errors import SchemaErrors

from f1.domain.endpoints import Endpoint
from f1.processing.normalize import COLUMNS, normalize
from f1.quality.schemas import SCHEMAS, schema_for
from tests.conftest import load_fixture


@pytest.mark.parametrize("endpoint", list(Endpoint))
def test_schema_matches_normalizer_columns(endpoint):
    schema = SCHEMAS[endpoint]
    columns = COLUMNS[endpoint]

    assert list(schema.columns) == [c.name for c in columns]
    for col in columns:
        assert schema.columns[col.name].nullable is not col.required


@pytest.mark.parametrize("endpoint", list(Endpoint))
def test_fixtures_are_valid(endpoint):
    df = normalize(endpoint, load_fixture(endpoint))
    schema_for(endpoint).validate(df, lazy=True)


@pytest.mark.parametrize("endpoint", list(Endpoint))
def test_empty_frames_are_valid(endpoint):
    schema_for(endpoint).validate(normalize(endpoint, []), lazy=True)


def _laps() -> pd.DataFrame:
    return normalize(Endpoint.LAPS, load_fixture(Endpoint.LAPS))


def _failed_checks(df: pd.DataFrame, endpoint: Endpoint) -> set[str]:
    with pytest.raises(SchemaErrors) as exc:
        schema_for(endpoint).validate(df, lazy=True)
    return set(exc.value.failure_cases["check"].astype(str))


def test_laps_schema_rejects_duplicate_business_key():
    df = pd.concat([_laps(), _laps().iloc[[1]]], ignore_index=True)
    assert "multiple_fields_uniqueness" in _failed_checks(df, Endpoint.LAPS)


def test_laps_schema_rejects_out_of_range_values():
    df = _laps()
    df.loc[1, "lap_number"] = 0
    df.loc[2, "lap_duration"] = 900.0
    checks = _failed_checks(df, Endpoint.LAPS)
    assert any(c.startswith("in_range") for c in checks)


def test_stints_schema_checks_compound_and_lap_order():
    df = normalize(Endpoint.STINTS, load_fixture(Endpoint.STINTS))
    df.loc[0, "compound"] = "SUPERSOFT"
    df.loc[1, "lap_end"] = 10
    checks = _failed_checks(df, Endpoint.STINTS)
    assert "isin" in " ".join(checks)
    assert "lap_end_gte_lap_start" in checks


def test_schema_rejects_extra_column():
    df = _laps().assign(extra=1)
    assert "column_in_schema" in _failed_checks(df, Endpoint.LAPS)


# --- pit_stops: bandeira vermelha (regressão México 2026) ------------------


def _pit(lane: float | None, lap: int = 44, driver: int = 30) -> dict:
    return {
        "session_key": 11404,
        "meeting_key": 1298,
        "driver_number": driver,
        "lap_number": lap,
        "date": "2026-11-01T21:43:05+00:00",
        "lane_duration": lane,
        "stop_duration": None,
        "pit_duration": lane,
    }


def test_pit_lane_time_under_red_flag_is_valid():
    """Regressão: 19 de 67 passagens (28,4%) com ~37 min de bandeira vermelha."""
    df = normalize(Endpoint.PIT, [_pit(2191.6), _pit(2315.8, lap=45, driver=16)])
    schema_for(Endpoint.PIT).validate(df, lazy=True)


@pytest.mark.parametrize("lane", [99_999.0, 0.0, -5.0])
def test_absurd_pit_lane_time_is_rejected(lane):
    df = normalize(Endpoint.PIT, [_pit(lane)])
    with pytest.raises(SchemaErrors) as exc:
        schema_for(Endpoint.PIT).validate(df, lazy=True)
    assert set(exc.value.failure_cases["column"]) == {"lane_duration"}


def test_mexico_2026_red_flag_passes_the_quality_gate():
    from f1.quality.validation import validate  # noqa: PLC0415

    normal = [_pit(22.0 + i, lap=10 + i, driver=i + 1) for i in range(48)]
    red_flag = [_pit(2172.9 + i, lap=44, driver=50 + i) for i in range(19)]
    df = normalize(Endpoint.PIT, normal + red_flag)

    result = validate(df, schema_for(Endpoint.PIT), max_rejection_rate=0.05)
    assert (len(result.valid), len(result.rejected)) == (67, 0)
