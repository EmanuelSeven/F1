import pytest

from f1.domain.endpoints import (
    CALENDAR_ENDPOINTS,
    DATASET_SPECS,
    SESSION_ENDPOINTS,
    Endpoint,
    PartitionLevel,
    parse_endpoints,
    spec_for,
)


def test_every_endpoint_has_a_spec():
    assert set(DATASET_SPECS) == set(Endpoint)


def test_calendar_and_session_endpoints_split():
    assert CALENDAR_ENDPOINTS == (Endpoint.MEETINGS, Endpoint.SESSIONS)
    assert len(SESSION_ENDPOINTS) == 6
    assert all(
        spec_for(e).partition_level is PartitionLevel.MEETING for e in SESSION_ENDPOINTS
    )


def test_spec_for_laps():
    spec = spec_for(Endpoint.LAPS)
    assert spec.dataset == "laps"
    assert spec.business_key == ("session_key", "driver_number", "lap_number")


def test_parse_endpoints_accepts_endpoint_and_dataset_names():
    assert parse_endpoints(["laps", " PIT_STOPS ", "pit", "session_result"]) == (
        Endpoint.LAPS,
        Endpoint.PIT,
        Endpoint.SESSION_RESULT,
    )


def test_parse_endpoints_rejects_unknown():
    with pytest.raises(ValueError, match="car_data"):
        parse_endpoints(["car_data"])
