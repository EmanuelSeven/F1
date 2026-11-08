import pandas as pd
import pytest

from f1.dashboard.views import charts
from f1.dashboard.views.theme import COMPOUND_COLOURS, base_layout, kpi_card
from f1.domain.endpoints import Endpoint
from f1.processing.normalize import normalize
from f1.processing.standings import (
    driver_standings,
    lap_times,
    session_weather,
    tyre_stints,
)
from tests.conftest import load_fixture

RACE = 9165


@pytest.fixture
def frames():
    return {e: normalize(e, load_fixture(e)) for e in Endpoint}


def test_points_bar_orders_leader_first_with_team_colours(frames):
    standings = driver_standings(
        frames[Endpoint.SESSION_RESULT],
        frames[Endpoint.SESSIONS],
        frames[Endpoint.DRIVERS],
    )
    fig = charts.points_bar(standings)
    bar = fig.data[0]

    assert list(bar.y) == ["SAI", "VER"]
    assert list(bar.text) == ["25", "10"]
    assert list(bar.marker.color) == ["#F91536", "#3671C6"]
    assert "Vitórias" in bar.hovertemplate
    assert "Pódios" in bar.hovertemplate
    assert fig.layout.yaxis.autorange == "reversed"


def test_lap_times_chart_one_line_per_driver(frames):
    laps = lap_times(frames[Endpoint.LAPS], frames[Endpoint.DRIVERS], RACE)
    fig = charts.lap_times_chart(laps)

    assert [t.name for t in fig.data] == ["VER", "SAI"]
    assert fig.data[0].line.color == "#3671C6"


def test_lap_times_chart_dots_teammates():
    laps = pd.DataFrame(
        {
            "acronym": ["VER", "PER"],
            "colour": ["#3671C6", "#3671C6"],
            "lap_number": [2, 2],
            "lap_duration": [95.0, 95.5],
        }
    )
    fig = charts.lap_times_chart(laps)
    assert [t.line.dash for t in fig.data] == ["solid", "dot"]


def test_tyre_strategy_chart_colours_by_compound(frames):
    stints = tyre_stints(
        frames[Endpoint.STINTS], frames[Endpoint.DRIVERS], RACE, ["SAI", "VER"]
    )
    fig = charts.tyre_strategy_chart(stints)

    by_name = {t.name: t for t in fig.data}
    assert set(by_name) == {"Médio", "Duro"}
    assert by_name["Duro"].marker.color == COMPOUND_COLOURS["HARD"]
    assert list(fig.layout.yaxis.categoryarray) == ["SAI", "VER"]
    medium = by_name["Médio"]
    assert list(medium.base) == [0, 40]  # SAI desde a volta 1, VER desde a 41


def test_weather_chart_air_and_track(frames):
    weather = session_weather(frames[Endpoint.WEATHER], RACE)
    fig = charts.weather_chart(weather)
    assert [t.name for t in fig.data] == ["Pista", "Ar"]


def test_theme_helpers():
    html = kpi_card("Corridas", "24", "Grandes <Prêmios>")
    assert 'class="kpi-value">24<' in html
    assert "&lt;Prêmios&gt;" in html  # texto escapado
    layout = base_layout(300, showlegend=False)
    assert (layout["height"], layout["showlegend"]) == (300, False)
    assert layout["paper_bgcolor"] == "rgba(0,0,0,0)"
