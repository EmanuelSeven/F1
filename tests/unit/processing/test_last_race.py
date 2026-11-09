from datetime import UTC, datetime

import pandas as pd
import pytest

from f1.domain.endpoints import Endpoint
from f1.processing.fastest_laps import fastest_laps
from f1.processing.last_race import (
    championship_after,
    choose_last_race,
    classification_with_grid,
    completed_races,
    default_season,
    has_completed_race,
    positions_gained,
    race_grid,
    race_highlights,
)
from f1.processing.normalize import normalize
from tests.conftest import load_fixture

QUALI, RACE = 9161, 9165
NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def frames():
    return {e: normalize(e, load_fixture(e)) for e in Endpoint}


def _session(key, meeting, name="Race", kind="Race", start="2023-10-08T13:00:00"):
    return {
        "session_key": key,
        "meeting_key": meeting,
        "year": 2023,
        "session_name": name,
        "session_type": kind,
        "date_start": f"{start}+00:00",
        "date_end": f"{start}+00:00",
    }


def _with_sessions(frames, *records):
    extra = normalize(Endpoint.SESSIONS, list(records))
    return pd.concat([frames[Endpoint.SESSIONS], extra], ignore_index=True)


# --- escolha da última corrida ---------------------------------------------


def test_latest_completed_race_with_results(frames):
    choice = choose_last_race(
        frames[Endpoint.SESSIONS], frames[Endpoint.SESSION_RESULT], NOW
    )

    assert int(choice.shown["session_key"]) == RACE
    assert int(choice.latest["session_key"]) == RACE
    assert not choice.results_pending
    assert int(choice.shown["round"]) == 1


def test_race_without_results_falls_back_to_previous(frames):
    """A corrida mais recente acabou de terminar e ainda não tem resultados."""
    sessions = _with_sessions(frames, _session(9300, 1300))

    choice = choose_last_race(sessions, frames[Endpoint.SESSION_RESULT], NOW)

    assert int(choice.latest["session_key"]) == 9300
    assert int(choice.shown["session_key"]) == RACE  # a anterior
    assert choice.results_pending


def test_future_and_unfinished_races_are_ignored(frames):
    running = datetime(2023, 9, 17, 13, tzinfo=UTC)  # corrida de Singapura em curso
    future = _session(9400, 1400, start="2099-05-03T13:00:00")
    sessions = _with_sessions(frames, future)

    assert completed_races(sessions, running).empty
    choice = choose_last_race(sessions, frames[Endpoint.SESSION_RESULT], running)
    assert (choice.shown, choice.latest, choice.results_pending) == (None, None, False)

    after = choose_last_race(sessions, frames[Endpoint.SESSION_RESULT], NOW)
    assert int(after.latest["session_key"]) == RACE  # 2099 ainda não aconteceu


def test_results_without_classified_drivers_do_not_count(frames):
    sessions = _with_sessions(frames, _session(9300, 1300))
    empty_results = normalize(
        Endpoint.SESSION_RESULT,
        [
            {
                "session_key": 9300,
                "meeting_key": 1300,
                "driver_number": 1,
                "position": None,
                "dnf": True,
            }
        ],
    )
    results = pd.concat([frames[Endpoint.SESSION_RESULT], empty_results])

    choice = choose_last_race(sessions, results, NOW)
    assert choice.results_pending
    assert int(choice.shown["session_key"]) == RACE


def test_no_completed_race_at_all():
    sessions = normalize(Endpoint.SESSIONS, [])
    results = normalize(Endpoint.SESSION_RESULT, [])
    choice = choose_last_race(sessions, results, NOW)
    assert choice.shown is None and not choice.results_pending


# --- posições ganhas --------------------------------------------------------


@pytest.mark.parametrize(
    ("grid", "finish", "gained"),
    [
        (21, 2, 19),  # Verstappen, Interlagos 2026
        (1, 1, 0),
        (2, 5, -3),
        (None, 4, None),  # largou do box / sem grade
        (10, None, None),  # abandono
    ],
)
def test_positions_gained(grid, finish, gained):
    result = positions_gained(
        pd.Series([grid], dtype="Int64"), pd.Series([finish], dtype="Int64")
    ).iloc[0]
    assert (pd.isna(result) and gained is None) or result == gained


def test_race_grid_uses_main_qualifying_not_sprint(frames):
    sessions = _with_sessions(
        frames, _session(9160, 1219, "Sprint Qualifying", "Qualifying")
    )
    sprint_grid = normalize(
        Endpoint.STARTING_GRID,
        [{"session_key": 9160, "meeting_key": 1219, "driver_number": 1, "position": 1}],
    )
    grid = pd.concat([frames[Endpoint.STARTING_GRID], sprint_grid])

    table = race_grid(grid, sessions, 1219)
    assert dict(zip(table["driver_number"], table["grid"], strict=True)) == {
        55: 1,
        1: 11,
    }


def test_classification_with_grid_and_highlights(frames):
    grid = race_grid(frames[Endpoint.STARTING_GRID], frames[Endpoint.SESSIONS], 1219)
    table = classification_with_grid(
        frames[Endpoint.SESSION_RESULT], frames[Endpoint.DRIVERS], grid, RACE
    )

    assert table[["acronym", "grid", "position", "gained"]].values.tolist() == [
        ["SAI", 1, 1, 0],
        ["VER", 11, 5, 6],
    ]
    fastest = fastest_laps(
        frames[Endpoint.LAPS],
        frames[Endpoint.DRIVERS],
        frames[Endpoint.SESSIONS],
        session_keys=[RACE],
        top=1,
    )
    facts = race_highlights(table, fastest)
    assert (facts.fastest_acronym, facts.fastest_time, facts.fastest_lap) == (
        "SAI",
        100.512,
        3,
    )
    assert (facts.top_gainer_name, facts.top_gain) == ("Max Verstappen", 6)
    assert facts.retirements == 0


def test_highlights_without_laps_gains_and_with_retirements(frames):
    table = classification_with_grid(
        frames[Endpoint.SESSION_RESULT],
        frames[Endpoint.DRIVERS],
        pd.DataFrame({"driver_number": [], "grid": []}),
        RACE,
    )
    table.loc[1, "dnf"] = True
    facts = race_highlights(table, None)
    assert facts.fastest_name is None
    assert facts.top_gain is None
    assert facts.retirements == 1


# --- campeonato após a corrida ---------------------------------------------


def _two_rounds():
    sessions = normalize(
        Endpoint.SESSIONS,
        [
            _session(1, 10, start="2026-03-02T15:00:00"),
            _session(2, 20, start="2026-03-09T17:00:00"),
        ],
    )
    drivers = normalize(
        Endpoint.DRIVERS,
        [
            {
                "session_key": s,
                "meeting_key": s * 10,
                "driver_number": n,
                "name_acronym": a,
                "first_name": f,
                "last_name": last,
                "team_name": t,
            }
            for s in (1, 2)
            for n, a, f, last, t in (
                (1, "VER", "Max", "Verstappen", "Red Bull Racing"),
                (16, "LEC", "Charles", "Leclerc", "Ferrari"),
                (4, "NOR", "Lando", "Norris", "McLaren"),
            )
        ],
    )
    results = normalize(
        Endpoint.SESSION_RESULT,
        [
            {
                "session_key": 1,
                "meeting_key": 10,
                "driver_number": 1,
                "position": 1,
                "points": 25.0,
            },
            {
                "session_key": 1,
                "meeting_key": 10,
                "driver_number": 16,
                "position": 2,
                "points": 18.0,
            },
            {
                "session_key": 1,
                "meeting_key": 10,
                "driver_number": 4,
                "position": 3,
                "points": 15.0,
            },
            {
                "session_key": 2,
                "meeting_key": 20,
                "driver_number": 4,
                "position": 1,
                "points": 25.0,
            },
            {
                "session_key": 2,
                "meeting_key": 20,
                "driver_number": 16,
                "position": 2,
                "points": 18.0,
            },
            {
                "session_key": 2,
                "meeting_key": 20,
                "driver_number": 1,
                "position": 9,
                "points": 2.0,
            },
        ],
    )
    return results, sessions, drivers


def test_championship_after_shows_position_change():
    results, sessions, drivers = _two_rounds()

    after_two = championship_after(results, sessions, drivers, 2)
    assert after_two[["acronym", "points", "previous", "change"]].values.tolist() == [
        ["NOR", 40.0, 3, 2],  # subiu 2
        ["LEC", 36.0, 2, 0],
        ["VER", 27.0, 1, -2],  # caiu 2
    ]

    after_one = championship_after(results, sessions, drivers, 1)
    assert after_one["acronym"].tolist() == ["VER", "LEC", "NOR"]
    assert after_one["change"].isna().all()  # primeira rodada: sem comparação


def test_championship_after_top_limit():
    results, sessions, drivers = _two_rounds()
    assert len(championship_after(results, sessions, drivers, 2, top=2)) == 2


# --- ano padrão do filtro "Temporada" -------------------------------------

YEARS_2027 = [2027, 2026, 2025, 2024, 2023]


def _season_calendar(year: int, race_day: str) -> pd.DataFrame:
    return normalize(
        Endpoint.SESSIONS,
        [_session(int(f"{year}01"), year, start=f"{race_day}T13:00:00")],
    )


def test_default_season_before_first_race_of_the_year():
    """Hoje é 10/03/2027 e a 1ª corrida de 2027 é em 14/03 → padrão 2026."""
    today = datetime(2027, 3, 10, tzinfo=UTC)
    calendars = {
        2027: _season_calendar(2027, "2027-03-14"),
        2026: _season_calendar(2026, "2026-03-08"),
    }

    def completed(year: int) -> bool:
        sessions = calendars.get(year)
        return sessions is not None and has_completed_race(sessions, today)

    assert default_season(YEARS_2027, completed) == 2026


def test_default_season_after_first_race_of_the_year():
    """Hoje é 20/03/2027: a corrida de 14/03 já aconteceu → padrão 2027."""
    today = datetime(2027, 3, 20, tzinfo=UTC)
    calendar = _season_calendar(2027, "2027-03-14")
    assert (
        default_season(
            YEARS_2027, lambda y: y == 2027 and has_completed_race(calendar, today)
        )
        == 2027
    )


def test_default_season_when_query_fails_is_current_year():
    def unavailable(_year: int) -> bool:
        raise ConnectionError("OpenF1 fora do ar")

    assert default_season(YEARS_2027, unavailable) == 2027


def test_default_season_without_any_race_is_current_year():
    assert default_season(YEARS_2027, lambda _y: False) == 2027


def test_has_completed_race_ignores_unfinished_and_cancelled():
    calendar = _season_calendar(2027, "2027-03-14")
    assert not has_completed_race(calendar, datetime(2027, 3, 14, 12, tzinfo=UTC))
    assert has_completed_race(calendar, datetime(2027, 3, 15, tzinfo=UTC))
    cancelled = calendar.assign(is_cancelled=pd.array([True], dtype="boolean"))
    assert not has_completed_race(cancelled, datetime(2027, 3, 15, tzinfo=UTC))
