from f1.domain.endpoints import Endpoint
from f1.domain.models import Filter, Partition
from f1.pipelines.calendar import load_calendar, run_calendar


def test_run_calendar_writes_bronze_and_silver(fake_source, stores, ctx, tmp_path):
    meetings = run_calendar(fake_source, stores, ctx, 2023)

    assert [m.meeting_key for m in meetings] == [1219]  # 1210 cancelado
    assert (tmp_path / "bronze/meetings/season=2023/raw.json").exists()

    silver_meetings = stores.silver.read_partition("meetings", Partition(2023))
    assert silver_meetings["meeting_key"].tolist() == [1219, 1210]
    assert silver_meetings["_run_id"].unique().tolist() == ["run-test"]
    sessions = stores.silver.read_partition("sessions", Partition(2023))
    assert len(sessions) == 3
    assert fake_source.calls[0] == (Endpoint.MEETINGS, (Filter("year", 2023),))


def test_load_calendar_returns_active_meetings_and_sessions(fake_source, stores, ctx):
    calendar = load_calendar(fake_source, stores, ctx, 2023)

    assert calendar.year == 2023
    assert [m.meeting_key for m in calendar.meetings] == [1219]
    assert [s.session_key for s in calendar.sessions] == [9161, 9165]  # 9099 cancelada
    assert calendar.sessions[1].is_race
