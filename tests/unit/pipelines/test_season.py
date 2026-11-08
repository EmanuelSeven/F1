from datetime import UTC, datetime

from f1.domain.endpoints import Endpoint
from f1.pipelines.season import run_season


def test_run_season_processes_finished_meetings(fake_source, stores, ctx):
    metrics = run_season(
        fake_source,
        stores,
        ctx,
        2023,
        endpoints=[Endpoint.LAPS, Endpoint.STINTS],
        now=datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert [m.pipeline for m in metrics] == ["silver.laps", "silver.stints"]
    assert metrics[0].destination == "laps/season=2023/meeting_key=1219"


def test_run_season_skips_meetings_not_finished(fake_source, stores, ctx):
    metrics = run_season(
        fake_source, stores, ctx, 2023, now=datetime(2023, 9, 16, tzinfo=UTC)
    )
    assert metrics == []
