from datetime import UTC, datetime

import pandas as pd
import pytest

from f1.domain.endpoints import Endpoint
from f1.processing.normalize import normalize
from f1.processing.standings import (
    FALLBACK_COLOUR,
    driver_acronyms,
    driver_directory,
    driver_standings,
    lap_times,
    pit_stops,
    points_sessions,
    race_classification,
    race_winners,
    season_kpis,
    session_weather,
    team_colour,
    tyre_stints,
    weather_summary,
)
from tests.conftest import load_fixture

RACE = 9165
SPRINT = 9170


def _frame(endpoint: Endpoint, extra: list[dict] | None = None) -> pd.DataFrame:
    return normalize(endpoint, [*load_fixture(endpoint), *(extra or [])])


@pytest.fixture
def season():
    """Fixtures de Singapura 2023 + uma sprint sintética no mesmo fim de semana."""
    sprint_session = {
        "session_key": SPRINT,
        "meeting_key": 1219,
        "year": 2023,
        "session_name": "Sprint",
        "session_type": "Race",
        "date_start": "2023-09-16T08:00:00+00:00",
        "is_cancelled": False,
    }
    sprint_drivers = [
        {**d, "session_key": SPRINT}
        for d in load_fixture(Endpoint.DRIVERS)
        if d["session_key"] == RACE
    ]
    sprint_results = [
        {
            "session_key": SPRINT,
            "meeting_key": 1219,
            "driver_number": 1,
            "position": 1,
            "points": 8.0,
        },
        {
            "session_key": SPRINT,
            "meeting_key": 1219,
            "driver_number": 55,
            "position": 2,
            "points": 7.0,
        },
    ]
    return {
        "sessions": _frame(Endpoint.SESSIONS, [sprint_session]),
        "meetings": _frame(Endpoint.MEETINGS),
        "drivers": _frame(Endpoint.DRIVERS, sprint_drivers),
        "results": _frame(Endpoint.SESSION_RESULT, sprint_results),
    }


def test_team_colour():
    assert team_colour("3671c6") == "#3671C6"
    assert team_colour(None) == FALLBACK_COLOUR
    assert team_colour("abc") == FALLBACK_COLOUR


def test_points_sessions_orders_and_numbers_rounds(season):
    sessions = points_sessions(season["sessions"])

    # quali e corrida cancelada ficam de fora; sprint herda a rodada do GP
    assert sessions["session_key"].tolist() == [SPRINT, RACE]
    assert sessions["kind"].tolist() == ["sprint", "race"]
    assert sessions["round"].tolist() == [1, 1]


def test_driver_directory_uses_latest_session(season):
    directory = driver_directory(season["drivers"], season["sessions"])

    sainz = directory.set_index("driver_number").loc[55]
    assert (sainz["acronym"], sainz["name"], sainz["team"]) == (
        "SAI",
        "Carlos Sainz",
        "Ferrari",
    )
    assert sainz["colour"] == "#F91536"


def test_driver_standings_sums_races_and_sprints(season):
    standings = driver_standings(
        season["results"], season["sessions"], season["drivers"]
    )

    assert standings["acronym"].tolist() == ["SAI", "VER"]
    assert standings["points"].tolist() == [32.0, 18.0]  # 25+7 e 10+8
    assert standings["wins"].tolist() == [1, 0]  # vitória em sprint não conta
    assert standings["podiums"].tolist() == [1, 0]
    assert standings["position"].tolist() == [1, 2]


def test_race_winners_only_main_races(season):
    winners = race_winners(
        season["results"], season["sessions"], season["meetings"], season["drivers"]
    )

    assert len(winners) == 1
    row = winners.iloc[0]
    assert (row["round"], row["gp"], row["acronym"], row["team"]) == (
        1,
        "Singapore",
        "SAI",
        "Ferrari",
    )
    assert row["date_start"] == datetime(2023, 9, 17, 12, tzinfo=UTC)


def test_season_kpis(season):
    standings = driver_standings(
        season["results"], season["sessions"], season["drivers"]
    )
    kpis = season_kpis(season["results"], season["sessions"], standings)

    assert (kpis.races, kpis.sprints, kpis.distinct_winners) == (1, 1, 1)
    assert (kpis.leader_name, kpis.leader_acronym, kpis.leader_points) == (
        "Carlos Sainz",
        "SAI",
        32.0,
    )


def test_season_kpis_without_results():
    sessions = normalize(Endpoint.SESSIONS, [])
    results = normalize(Endpoint.SESSION_RESULT, [])
    standings = driver_standings(results, sessions, normalize(Endpoint.DRIVERS, []))
    kpis = season_kpis(results, sessions, standings)

    assert standings.empty
    assert kpis.leader_name is None
    assert kpis.races == 0


def test_race_classification_orders_unclassified_last(season):
    results = pd.concat(
        [
            season["results"],
            normalize(
                Endpoint.SESSION_RESULT,
                [
                    {
                        "session_key": RACE,
                        "meeting_key": 1219,
                        "driver_number": 44,
                        "position": None,
                        "number_of_laps": 10,
                        "dnf": True,
                    }
                ],
            ),
        ],
        ignore_index=True,
    )
    table = race_classification(results, season["drivers"], RACE)

    assert table["acronym"].tolist() == ["SAI", "VER", "44"]
    assert table["colour"].iloc[2] == FALLBACK_COLOUR


def test_lap_times_excludes_slow_and_out_laps(season):
    laps = _frame(Endpoint.LAPS)
    slow = laps.iloc[[4]].assign(lap_number=4, lap_duration=180.0)
    laps = pd.concat([laps, slow], ignore_index=True)

    clean = lap_times(laps, season["drivers"], RACE)
    everything = lap_times(laps, season["drivers"], RACE, exclude_slow=False)

    assert set(clean["lap_number"]) == {2, 3}  # sem volta 1 e sem a volta lenta
    assert 180.0 in everything["lap_duration"].tolist()
    assert clean["acronym"].unique().tolist() == ["VER", "SAI"]


def test_tyre_stints_respects_order(season):
    stints = tyre_stints(_frame(Endpoint.STINTS), season["drivers"], RACE, ["SAI"])

    assert stints["acronym"].tolist() == ["SAI", "SAI", "VER", "VER"]
    assert stints["laps"].tolist() == [20, 42, 40, 22]


def test_pit_stops_sorted_by_lap(season):
    stops = pit_stops(_frame(Endpoint.PIT), season["drivers"], RACE)

    assert stops["acronym"].tolist() == ["SAI", "VER"]
    assert stops["lap_number"].tolist() == [20, 40]


def test_weather_summary():
    weather = session_weather(_frame(Endpoint.WEATHER), RACE)
    summary = weather_summary(weather)

    assert len(weather) == 2
    assert summary.track_avg == 34.8
    assert (summary.track_min, summary.track_max) == (34.7, 34.9)
    assert summary.rained is True


def test_weather_summary_empty():
    summary = weather_summary(normalize(Endpoint.WEATHER, []))
    assert summary.air_avg is None
    assert summary.rained is False


def _drivers(**overrides) -> pd.DataFrame:
    record = {
        "session_key": RACE,
        "meeting_key": 1219,
        "driver_number": 30,
        "name_acronym": "LAW",
        "first_name": "Liam",
        "last_name": "Lawson",
        "full_name": "Liam LAWSON",
        "broadcast_name": "L LAWSON",
        "team_name": "RB",
        "team_colour": "6692FF",
    }
    return normalize(Endpoint.DRIVERS, [{**record, **overrides}])


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "LAW"),
        ({"name_acronym": " law "}, "LAW"),  # normaliza espaços e caixa
        ({"name_acronym": None}, "LAW"),  # sem sigla: sobrenome
        ({"name_acronym": ""}, "LAW"),
        ({"name_acronym": None, "last_name": None}, "30"),  # último recurso
    ],
)
def test_driver_acronyms(overrides, expected):
    assert driver_acronyms(_drivers(**overrides)).tolist() == [expected]


def test_lawson_keeps_law_acronym_in_standings(season):
    """Regressão: no gráfico aparecia "REITO" no lugar de LAW (Liam Lawson).

    A sigla vem de ``name_acronym`` (LAW); "REITO" era "DIREITO" — tradução
    automática de "LAW" pelo navegador — cortado pela margem do eixo.
    """
    drivers = pd.concat([season["drivers"], _drivers()], ignore_index=True)
    results = pd.concat(
        [
            season["results"],
            normalize(
                Endpoint.SESSION_RESULT,
                [
                    {
                        "session_key": RACE,
                        "meeting_key": 1219,
                        "driver_number": 30,
                        "position": 9,
                        "points": 4.0,
                    }
                ],
            ),
        ],
        ignore_index=True,
    )
    standings = driver_standings(results, season["sessions"], drivers)
    lawson = standings.set_index("driver_number").loc[30]

    assert (lawson["acronym"], lawson["name"], lawson["points"]) == (
        "LAW",
        "Liam Lawson",
        4.0,
    )
    assert standings["acronym"].str.fullmatch(r"[A-Z]{3}").all()
