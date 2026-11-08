from datetime import UTC, datetime

from f1.domain.models import LATEST, Filter, Operator
from f1.ingestion.query import build_query, format_value


def test_build_query_equality():
    assert build_query([Filter("session_key", 9161)]) == "session_key=9161"


def test_build_query_comparison_operators_are_encoded():
    query = build_query(
        [Filter("speed", 315, Operator.GTE), Filter("lap_number", 8, Operator.LT)]
    )
    assert query == "speed%3E%3D315&lap_number%3C8"


def test_build_query_repeats_multi_values():
    assert build_query([Filter("driver_number", (4, 81))]) == (
        "driver_number=4&driver_number=81"
    )


def test_build_query_encodes_spaces_and_latest():
    query = build_query(
        [Filter("session_name", "Sprint Qualifying"), Filter("session_key", LATEST)]
    )
    assert query == "session_name=Sprint%20Qualifying&session_key=latest"


def test_format_value_booleans_and_dates():
    assert format_value(True) == "true"
    assert format_value(False) == "false"
    assert format_value(datetime(2023, 9, 1, tzinfo=UTC)) == "2023-09-01T00:00:00+00:00"


def test_build_query_empty():
    assert build_query([]) == ""
