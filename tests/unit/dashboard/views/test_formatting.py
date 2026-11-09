from datetime import UTC, datetime

import pandas as pd
import pytest

from f1.dashboard.views.formatting import (
    format_day_month,
    format_gap,
    format_lap,
    format_points,
    format_race_time,
    format_result_time,
    format_seconds,
    format_status,
    format_temperature,
    summary_sentence,
)
from f1.processing.standings import SeasonKpis


@pytest.mark.parametrize(
    ("value", "expected"), [(437.0, "437"), (12.5, "12,5"), (1234.0, "1.234")]
)
def test_format_points(value, expected):
    assert format_points(value) == expected


def test_format_lap_and_race_time():
    assert format_lap(92.708) == "1:32.708"
    assert format_lap(42.1) == "42.100"
    assert format_lap(pd.NA) == "—"
    assert format_race_time(5504.742) == "1:31:44.742"
    assert format_race_time(None) == "—"


@pytest.mark.parametrize(
    ("gap", "expected"),
    [
        (21.441, "+21,441 s"),
        ("+1 LAP", "+1 volta"),
        ("+2 LAPS", "+2 voltas"),
        ("DNF", "DNF"),
        (None, "—"),
    ],
)
def test_format_gap(gap, expected):
    assert format_gap(gap) == expected


def test_format_result_time_winner_vs_others():
    assert format_result_time(1, 5504.742, 0) == "1:31:44.742"
    assert format_result_time(2, None, "22.457") == "+22,457 s"
    assert format_result_time(pd.NA, None, None) == "—"


def test_format_status_seconds_dates_and_temperature():
    assert format_status(True, False, False) == "Abandono"
    assert format_status(False, True, False) == "Não largou"
    assert format_status(False, False, True) == "Desclassificado"
    assert format_status(False, False, False) == ""
    assert format_seconds(2.43) == "2,4"
    assert format_seconds(pd.NA) == "—"
    assert format_day_month(datetime(2026, 3, 2, tzinfo=UTC)) == "02/03"
    assert format_day_month(None) == "—"
    assert format_temperature(23.66) == "23,7 °C"
    assert format_temperature(None) == "—"


def _kpis(**overrides) -> SeasonKpis:
    values = {
        "races": 24,
        "sprints": 6,
        "distinct_winners": 7,
        "leader_name": "Max Verstappen",
        "leader_acronym": "VER",
        "leader_points": 437.0,
    }
    return SeasonKpis(**{**values, **overrides})


def test_summary_sentence():
    assert summary_sentence(_kpis()) == (
        "**Max Verstappen** soma **437** pontos; **7** pilotos diferentes "
        "venceram as **24** corridas."
    )
    assert summary_sentence(_kpis(races=1, distinct_winners=1)) == (
        "**Max Verstappen** soma **437** pontos; **1** piloto venceu a **1** "
        "corrida disputada."
    )
    empty = _kpis(leader_name=None, races=0, distinct_winners=0)
    assert "Ainda não há" in summary_sentence(empty)
