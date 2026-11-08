from datetime import UTC, datetime

import pytest

from f1.config.settings import Settings
from f1.dashboard.bootstrap import (
    BOOTSTRAP_YEAR,
    run_race_details,
    run_season_bootstrap,
)
from f1.dashboard.loaders import (
    load_race_details,
    load_season_data,
    race_details_loaded,
    season_is_loaded,
)
from f1.domain.endpoints import Endpoint
from f1.domain.models import MeetingRef, SessionKind
from f1.ingestion.openf1_client import OpenF1AccessError
from tests.unit.dashboard.conftest import DeniedClient, StubClient, as_season

AFTER_SEASON = datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path, request_interval_seconds=0)


def test_season_bootstrap_loads_calendar_and_points_sessions(settings, openf1_data):
    stub = StubClient(openf1_data)

    result = run_season_bootstrap(
        settings, 2023, source_factory=lambda _: stub, now=AFTER_SEASON
    )

    assert (result.year, result.meetings, result.sessions) == (2023, 1, 1)
    assert result.records == 4  # 2 pilotos + 2 resultados da corrida
    assert season_is_loaded(settings.data_dir, 2023)
    data = load_season_data(settings.data_dir, 2023)
    assert data.results["session_key"].unique().tolist() == [9165]  # sem quali
    assert len(data.meetings) == 2
    # calendário (2) + drivers e session_result em lote (2)
    assert [c[0] for c in stub.calls] == [
        Endpoint.MEETINGS,
        Endpoint.SESSIONS,
        Endpoint.DRIVERS,
        Endpoint.SESSION_RESULT,
    ]


def test_season_bootstrap_skips_sessions_not_finished(settings, openf1_data):
    stub = StubClient(openf1_data)
    before_race = datetime(2023, 9, 17, 13, tzinfo=UTC)

    result = run_season_bootstrap(
        settings, 2023, source_factory=lambda _: stub, now=before_race
    )

    assert result.sessions == 0
    assert not season_is_loaded(settings.data_dir, 2023)


def test_season_bootstrap_defaults_to_2024(settings, openf1_data):
    stub = StubClient(as_season(openf1_data, 2024))
    result = run_season_bootstrap(settings, source_factory=lambda _: stub)

    assert result.year == BOOTSTRAP_YEAR == 2024
    assert season_is_loaded(settings.data_dir, 2024)


def test_season_bootstrap_propagates_access_error(settings):
    with pytest.raises(OpenF1AccessError):
        run_season_bootstrap(settings, source_factory=lambda _: DeniedClient({}))
    assert not season_is_loaded(settings.data_dir, BOOTSTRAP_YEAR)


def test_race_details_loads_only_the_main_race(settings, openf1_data):
    stub = StubClient(openf1_data)
    meeting = MeetingRef(1219, 2023, "Singapore Grand Prix")

    assert not race_details_loaded(settings.data_dir, 2023, 1219)
    result = run_race_details(settings, meeting, source_factory=lambda _: stub)

    assert result.records == 6 + 4 + 2 + 2  # laps, stints, pit, weather da corrida
    assert race_details_loaded(settings.data_dir, 2023, 1219)
    details = load_race_details(settings.data_dir, 2023, 1219)
    assert details.laps["session_key"].unique().tolist() == [9165]
    assert len(details.weather) == 2
    # sessões do meeting + 1 requisição por dataset, só da corrida principal
    assert [c[0] for c in stub.calls] == [
        Endpoint.SESSIONS,
        Endpoint.LAPS,
        Endpoint.STINTS,
        Endpoint.PIT,
        Endpoint.WEATHER,
    ]


def test_season_bootstrap_loads_selected_kinds(settings, openf1_data):
    stub = StubClient(openf1_data)

    result = run_season_bootstrap(
        settings,
        2023,
        source_factory=lambda _: stub,
        now=AFTER_SEASON,
        kinds=(SessionKind.RACE, SessionKind.QUALIFYING),
    )

    assert result.sessions == 2
    data = load_season_data(settings.data_dir, 2023)
    assert sorted(data.results["session_key"].unique()) == [9161, 9165]
