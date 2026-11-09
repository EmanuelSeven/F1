from datetime import UTC, datetime

import pytest

from f1.domain.endpoints import Endpoint
from f1.domain.models import SessionKind
from f1.processing.fastest_laps import (
    TOP_LAPS,
    circuit_sessions,
    fastest_laps,
    latest_grand_prix,
)
from f1.processing.filters import grand_prix_options
from f1.processing.normalize import normalize
from tests.conftest import load_fixture

QUALI, RACE = 9161, 9165
AFTER = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def frames():
    return {e: normalize(e, load_fixture(e)) for e in Endpoint}


def _top(frames, keys, **options):
    return fastest_laps(
        frames[Endpoint.LAPS],
        frames[Endpoint.DRIVERS],
        frames[Endpoint.SESSIONS],
        session_keys=keys,
        **options,
    )


def test_fastest_laps_of_the_race(frames):
    top = _top(frames, [RACE])

    # 6 voltas da corrida, 2 sem tempo (volta 1) → 4 voltas válidas
    assert top[["position", "acronym", "lap_number"]].values.tolist() == [
        [1, "SAI", 3],
        [2, "SAI", 2],
        [3, "VER", 3],
        [4, "VER", 2],
    ]
    assert top["lap_duration"].tolist() == [100.512, 100.902, 100.911, 101.456]
    assert top["gap"].round(3).tolist() == [0.0, 0.39, 0.399, 0.944]
    assert top["session_name"].unique().tolist() == ["Race"]
    assert top["team"].tolist()[0] == "Ferrari"


def test_qualifying_laps_are_included_when_selected(frames):
    top = _top(frames, [QUALI, RACE])
    best = top.iloc[0]
    assert (best["acronym"], best["lap_duration"], best["kind"]) == (
        "SAI",
        92.708,
        "qualifying",
    )


def test_top_limit_and_one_per_driver(frames):
    assert len(_top(frames, [RACE], top=2)) == 2
    assert TOP_LAPS == 5
    per_driver = _top(frames, [RACE], one_per_driver=True)
    assert per_driver["acronym"].tolist() == ["SAI", "VER"]
    assert per_driver["position"].tolist() == [1, 2]


def test_allowed_drivers_and_pit_out_laps(frames):
    assert _top(frames, [RACE], allowed={1})["acronym"].unique().tolist() == ["VER"]

    laps = frames[Endpoint.LAPS].copy()
    out_lap = laps.index[(laps["session_key"] == RACE) & (laps["lap_number"] == 2)][0]
    laps.loc[out_lap, ["lap_duration", "is_pit_out_lap"]] = [50.0, True]
    top = fastest_laps(
        laps,
        frames[Endpoint.DRIVERS],
        frames[Endpoint.SESSIONS],
        session_keys=[RACE],
    )
    assert 50.0 not in top["lap_duration"].tolist()  # volta de saída do box


def test_fastest_laps_empty(frames):
    top = _top(frames, [])
    assert top.empty
    assert list(top.columns)[:3] == ["position", "driver_number", "acronym"]


def test_circuit_sessions_only_finished_of_selected_kinds(frames):
    sessions = frames[Endpoint.SESSIONS]
    race_only = (SessionKind.RACE,)
    both = (SessionKind.RACE, SessionKind.QUALIFYING)

    assert circuit_sessions(sessions, 1219, race_only, AFTER) == [RACE]
    assert circuit_sessions(sessions, 1219, both, AFTER) == [QUALI, RACE]
    between = datetime(2023, 9, 17, 12, 30, tzinfo=UTC)  # corrida em andamento
    assert circuit_sessions(sessions, 1219, both, between) == [QUALI]
    assert circuit_sessions(sessions, 1210, both, AFTER) == []  # GP cancelado


def test_latest_grand_prix(frames):
    sessions = frames[Endpoint.SESSIONS]
    assert latest_grand_prix(sessions, AFTER) == 1219
    assert latest_grand_prix(sessions, datetime(2023, 1, 1, tzinfo=UTC)) is None


def test_grand_prix_options_have_circuit(frames):
    gps = grand_prix_options(frames[Endpoint.SESSIONS], frames[Endpoint.MEETINGS])
    assert gps[["meeting_key", "gp", "circuit"]].values.tolist() == [
        [1219, "Singapore", "Singapore"]
    ]
