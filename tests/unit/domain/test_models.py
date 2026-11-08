from datetime import UTC, datetime

import pytest

from f1.domain.models import (
    Filter,
    MeetingRef,
    Operator,
    Partition,
    SessionRef,
    as_int,
)


def test_filter_values_single_and_multi():
    assert Filter("driver_number", 1).values() == (1,)
    assert Filter("driver_number", (1, 44)).values() == (1, 44)


@pytest.mark.parametrize(
    ("field", "value", "op"),
    [
        ("", 1, Operator.EQ),
        ("speed", (), Operator.EQ),
        ("speed", (300, 310), Operator.GTE),
    ],
)
def test_filter_rejects_invalid(field, value, op):
    with pytest.raises(ValueError):
        Filter(field, value, op)


def test_partition_segments():
    assert str(Partition(2024)) == "season=2024"
    assert Partition(2024, 1229).segments() == ("season=2024", "meeting_key=1229")


def test_meeting_ref_from_record():
    meeting = MeetingRef.from_record(
        {
            "meeting_key": 1219,
            "year": 2023,
            "meeting_name": "Singapore Grand Prix",
            "date_start": "2023-09-15T09:30:00+00:00",
            "date_end": "2023-09-17T14:00:00+00:00",
        }
    )
    assert meeting.meeting_key == 1219
    assert meeting.ends_at == datetime(2023, 9, 17, 14, tzinfo=UTC)
    assert not meeting.is_cancelled
    assert meeting.is_finished(datetime(2023, 9, 18, tzinfo=UTC))
    assert not meeting.is_finished(datetime(2023, 9, 16, tzinfo=UTC))


def test_meeting_ref_falls_back_to_date_start_and_naive_dates():
    meeting = MeetingRef.from_record(
        {"meeting_key": "1", "year": 2023, "date_start": "2023-01-01T00:00:00"}
    )
    assert meeting.ends_at == datetime(2023, 1, 1, tzinfo=UTC)
    assert MeetingRef(1, 2023, "x").is_finished(datetime.now(UTC)) is False


def test_session_ref_from_record():
    session = SessionRef.from_record(
        {
            "session_key": 9165,
            "meeting_key": 1219,
            "session_name": "Race",
            "session_type": "Race",
            "is_cancelled": True,
        }
    )
    assert session == SessionRef(9165, 1219, "Race", "Race", is_cancelled=True)


@pytest.mark.parametrize("value", [None, True, [1]])
def test_as_int_rejects_non_numbers(value):
    with pytest.raises(ValueError):
        as_int({"k": value}, "k")
