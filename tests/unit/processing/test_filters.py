import pytest

from f1.domain.endpoints import Endpoint
from f1.domain.models import (
    POINTS_KINDS,
    SessionKind,
    classify_session,
    primary_kinds,
)
from f1.processing.filters import (
    SeasonFilter,
    allowed_drivers,
    driver_options,
    grand_prix_options,
    season_view,
    team_options,
)
from f1.processing.normalize import normalize
from f1.processing.standings import (
    classified_sessions,
    driver_standings,
    race_winners,
    result_kinds,
    season_kpis,
)
from tests.conftest import load_fixture

QUALI, RACE_KEY, SPRINT_KEY, TESTING_KEY = 9161, 9165, 9170, 9001
FERRARI, RED_BULL = "Ferrari", "Red Bull Racing"


@pytest.fixture
def season():
    """Singapura 2023 (quali + corrida) + sprint sintética + dia de teste."""
    extra_sessions = [
        {
            "session_key": SPRINT_KEY,
            "meeting_key": 1219,
            "year": 2023,
            "session_name": "Sprint",
            "session_type": "Race",
            "date_start": "2023-09-16T08:00:00+00:00",
        },
        {
            "session_key": TESTING_KEY,
            "meeting_key": 1199,
            "year": 2023,
            "session_name": "Day 1",
            "session_type": "Practice",
            "date_start": "2023-02-23T07:00:00+00:00",
        },
    ]
    sprint_drivers = [
        {**d, "session_key": SPRINT_KEY}
        for d in load_fixture(Endpoint.DRIVERS)
        if d["session_key"] == RACE_KEY
    ]
    extra_results = [
        {
            "session_key": SPRINT_KEY,
            "meeting_key": 1219,
            "driver_number": 1,
            "position": 1,
            "points": 8.0,
        },
        {
            "session_key": SPRINT_KEY,
            "meeting_key": 1219,
            "driver_number": 55,
            "position": 2,
            "points": 7.0,
        },
    ]
    return {
        "sessions": normalize(
            Endpoint.SESSIONS, [*load_fixture(Endpoint.SESSIONS), *extra_sessions]
        ),
        "meetings": normalize(Endpoint.MEETINGS, load_fixture(Endpoint.MEETINGS)),
        "drivers": normalize(
            Endpoint.DRIVERS, [*load_fixture(Endpoint.DRIVERS), *sprint_drivers]
        ),
        "results": normalize(
            Endpoint.SESSION_RESULT,
            [*load_fixture(Endpoint.SESSION_RESULT), *extra_results],
        ),
    }


def _view(season, **filters):
    return season_view(
        season["results"],
        season["sessions"],
        season["meetings"],
        season["drivers"],
        SeasonFilter(**filters),
    )


# --- tipos de sessão ------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind_type", "expected"),
    [
        ("Race", "Race", SessionKind.RACE),
        ("Sprint", "Race", SessionKind.SPRINT),
        ("Qualifying", "Qualifying", SessionKind.QUALIFYING),
        ("Sprint Qualifying", "Qualifying", SessionKind.QUALIFYING),
        ("Practice 2", "Practice", SessionKind.PRACTICE),
        ("Day 1", "Testing", None),
    ],
)
def test_classify_session(name, kind_type, expected):
    assert classify_session(name, kind_type) == expected


def test_primary_kinds_prefers_race():
    assert primary_kinds(POINTS_KINDS) == (SessionKind.RACE,)
    assert primary_kinds((SessionKind.SPRINT, SessionKind.QUALIFYING)) == (
        SessionKind.SPRINT,
        SessionKind.QUALIFYING,
    )


def test_classified_sessions_skips_testing_and_cancelled(season):
    df = classified_sessions(season["sessions"])

    assert df["session_key"].tolist() == [SPRINT_KEY, QUALI, RACE_KEY]
    assert df["kind"].tolist() == ["sprint", "qualifying", "race"]
    assert TESTING_KEY not in df["session_key"].tolist()  # sem corrida no meeting


def test_points_follow_selected_kinds(season):
    def points(kinds):
        table = driver_standings(
            season["results"], season["sessions"], season["drivers"], kinds
        )
        return dict(zip(table["acronym"], table["points"], strict=True))

    assert points(POINTS_KINDS) == {"SAI": 32.0, "VER": 18.0}
    assert points((SessionKind.RACE,)) == {"SAI": 25.0, "VER": 10.0}
    assert points((SessionKind.SPRINT,)) == {"VER": 8.0, "SAI": 7.0}
    assert points((SessionKind.QUALIFYING,)) == {"SAI": 0.0, "VER": 0.0}


def test_wins_use_primary_kinds(season):
    sprint_only = driver_standings(
        season["results"], season["sessions"], season["drivers"], (SessionKind.SPRINT,)
    )
    assert sprint_only.set_index("acronym")["wins"].to_dict() == {"VER": 1, "SAI": 0}


def test_winners_for_qualifying_are_pole_sitters(season):
    poles = race_winners(
        season["results"],
        season["sessions"],
        season["meetings"],
        season["drivers"],
        (SessionKind.QUALIFYING,),
    )
    assert poles[["session_key", "acronym", "kind"]].values.tolist() == [
        [QUALI, "SAI", "qualifying"]
    ]


def test_result_kinds(season):
    assert result_kinds(season["results"], season["sessions"]) == {
        SessionKind.RACE,
        SessionKind.SPRINT,
        SessionKind.QUALIFYING,
    }


# --- equipe e piloto ------------------------------------------------------


def test_allowed_drivers_combines_team_and_driver_with_and(season):
    drivers = season["drivers"]
    assert allowed_drivers(drivers, SeasonFilter()) is None
    assert allowed_drivers(drivers, SeasonFilter(teams=(FERRARI,))) == {55}
    assert allowed_drivers(drivers, SeasonFilter(drivers=(1,))) == {1}
    assert (
        allowed_drivers(drivers, SeasonFilter(teams=(FERRARI,), drivers=(1,))) == set()
    )


def test_team_and_driver_options_depend_on_teams(season):
    assert team_options(season["drivers"]) == [FERRARI, RED_BULL]
    everyone = driver_options(season["drivers"], season["sessions"])
    assert everyone["acronym"].tolist() == ["SAI", "VER"]
    ferrari = driver_options(season["drivers"], season["sessions"], [FERRARI])
    assert ferrari[["driver_number", "acronym", "name"]].values.tolist() == [
        [55, "SAI", "Carlos Sainz"]
    ]


def test_grand_prix_options_only_weekends_with_race(season):
    gps = grand_prix_options(season["sessions"], season["meetings"])
    assert gps[["meeting_key", "label"]].values.tolist() == [[1219, "1 · Singapore"]]


# --- visão filtrada -------------------------------------------------------


def test_view_without_filters_matches_season(season):
    view = _view(season)

    assert view.standings["acronym"].tolist() == ["SAI", "VER"]
    assert view.winners["acronym"].tolist() == ["SAI"]
    assert view.kpis.filtered is False
    assert (view.kpis.races, view.kpis.sprints, view.kpis.distinct_winners) == (1, 1, 1)


def test_team_filter_shows_only_its_drivers(season):
    view = _view(season, teams=(FERRARI,))

    assert view.standings["acronym"].tolist() == ["SAI"]
    assert view.standings["position"].tolist() == [1]  # posição no campeonato
    assert view.winners["acronym"].tolist() == ["SAI"]
    kpis = view.kpis
    assert (kpis.filtered, kpis.leader_acronym, kpis.leader_points) == (
        True,
        "SAI",
        32.0,
    )
    assert (kpis.distinct_winners, kpis.events_won, kpis.events) == (1, 1, 1)


def test_driver_filter_without_wins(season):
    view = _view(season, drivers=(1,))

    assert view.standings["acronym"].tolist() == ["VER"]
    assert view.winners.empty
    assert len(view.all_winners) == 1
    assert (view.kpis.distinct_winners, view.kpis.events_won) == (0, 0)
    assert view.kpis.leader_acronym == "VER"


def test_grand_prix_filter_highlights_without_filtering(season):
    view = _view(season, meeting_key=1219)

    assert len(view.winners) == 1
    assert view.highlighted_rows == [0]
    focus = view.focus_row()
    assert focus is not None and int(focus["session_key"]) == RACE_KEY

    other = _view(season, meeting_key=999)
    assert other.highlighted_rows == []
    assert other.focus_row() is None


def test_grand_prix_focus_survives_driver_filter(season):
    view = _view(season, meeting_key=1219, drivers=(1,))
    assert view.highlighted_rows == []  # vencedor não está na seleção
    assert view.focus_row() is not None  # mas os detalhes do GP continuam


def test_kpis_without_points_kinds(season):
    standings = driver_standings(
        season["results"],
        season["sessions"],
        season["drivers"],
        (SessionKind.QUALIFYING,),
    )
    kpis = season_kpis(
        season["results"], season["sessions"], standings, (SessionKind.QUALIFYING,)
    )
    assert kpis.leader_name is None
    assert kpis.points_kinds == ()
    assert kpis.primary == (SessionKind.QUALIFYING,)
    assert (kpis.events, kpis.distinct_winners) == (1, 1)


def test_season_filter_flags():
    assert not SeasonFilter().restricts_drivers
    assert SeasonFilter(teams=(FERRARI,)).restricts_drivers
    assert SeasonFilter(drivers=(1,)).restricts_drivers
    assert SeasonFilter().kinds == POINTS_KINDS


def _bearman_season():
    """Bearman 2024: #38 pela Ferrari (Jeddah) e #50 pela Haas (Baku)."""

    def session(key, meeting, start):
        return {
            "session_key": key,
            "meeting_key": meeting,
            "year": 2024,
            "session_name": "Race",
            "session_type": "Race",
            "date_start": start,
        }

    def driver(key, number, team, colour):
        return {
            "session_key": key,
            "meeting_key": key,
            "driver_number": number,
            "name_acronym": "BEA",
            "first_name": "Oliver",
            "last_name": "Bearman",
            "team_name": team,
            "team_colour": colour,
        }

    def result(key, number, position, points):
        return {
            "session_key": key,
            "meeting_key": key,
            "driver_number": number,
            "position": position,
            "points": points,
        }

    return {
        "sessions": normalize(
            Endpoint.SESSIONS,
            [
                session(1, 1, "2024-03-09T17:00:00+00:00"),
                session(2, 2, "2024-09-15T11:00:00+00:00"),
            ],
        ),
        "meetings": normalize(
            Endpoint.MEETINGS,
            [
                {
                    "meeting_key": 1,
                    "year": 2024,
                    "meeting_name": "Saudi Arabian Grand Prix",
                    "date_start": "2024-03-07T00:00:00+00:00",
                },
                {
                    "meeting_key": 2,
                    "year": 2024,
                    "meeting_name": "Azerbaijan Grand Prix",
                    "date_start": "2024-09-13T00:00:00+00:00",
                },
            ],
        ),
        "drivers": normalize(
            Endpoint.DRIVERS,
            [
                driver(1, 38, FERRARI, "E8002D"),
                driver(2, 50, "Haas F1 Team", "B6BABD"),
                {
                    "session_key": 1,
                    "meeting_key": 1,
                    "driver_number": 1,
                    "name_acronym": "VER",
                    "first_name": "Max",
                    "last_name": "Verstappen",
                    "team_name": RED_BULL,
                },
            ],
        ),
        "results": normalize(
            Endpoint.SESSION_RESULT,
            [
                result(1, 38, 7, 6.0),
                result(2, 50, 10, 1.0),
                result(1, 1, 1, 25.0),
            ],
        ),
    }


def test_driver_with_two_numbers_is_a_single_row():
    """Regressão: "BEA" aparecia duas vezes (números #38 e #50 em 2024)."""
    data = _bearman_season()
    view = _view(data)
    bearman = view.standings.loc[view.standings["acronym"] == "BEA"]

    assert len(bearman) == 1
    row = bearman.iloc[0]
    assert (row["points"], row["team"], row["driver_number"]) == (
        7.0,
        "Haas F1 Team",  # equipe mais recente
        50,
    )
    assert row["driver_numbers"] == (38, 50)
    options = driver_options(data["drivers"], data["sessions"])
    assert options["acronym"].tolist() == ["BEA", "VER"]


def test_team_filter_includes_driver_who_changed_number():
    data = _bearman_season()

    ferrari = _view(data, teams=(FERRARI,))
    assert ferrari.standings["acronym"].tolist() == ["BEA"]
    assert ferrari.standings["points"].tolist() == [7.0]  # temporada inteira
    assert allowed_drivers(data["drivers"], SeasonFilter(drivers=(50,))) == {38, 50}
    picked = driver_options(data["drivers"], data["sessions"], [FERRARI])
    assert picked["acronym"].tolist() == ["BEA"]
