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
