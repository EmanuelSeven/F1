from datetime import UTC, datetime

import pytest

from f1.utils.dates import parse_utc


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2023-09-16T13:03:35.200000+00:00", datetime(2023, 9, 16, 13, 3, 35, 200000)),
        ("2023-09-16T15:03:35+02:00", datetime(2023, 9, 16, 13, 3, 35)),
        ("2023-09-16T13:03:35Z", datetime(2023, 9, 16, 13, 3, 35)),
        ("2023-09-16T13:03:35", datetime(2023, 9, 16, 13, 3, 35)),
    ],
)
def test_parse_utc_normalizes_to_utc(value, expected):
    assert parse_utc(value) == expected.replace(tzinfo=UTC)
    assert parse_utc(value).tzinfo == UTC


def test_parse_utc_rejects_invalid():
    with pytest.raises(ValueError):
        parse_utc("not-a-date")
