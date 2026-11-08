"""Textos que dependem dos filtros e funções puras da barra lateral/página."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from f1.dashboard.views.formatting import (
    events_noun,
    points_caption,
    points_subtitle,
    session_label,
    summary_sentence,
    winners_caption,
)
from f1.dashboard.views.season import (
    HIGHLIGHT_STYLE,
    selection_key,
    table_styles,
    winners_display,
)
from f1.dashboard.views.sidebar import (
    initial_year,
    season_options,
    selected_kinds,
)
from f1.domain.models import SessionKind
from f1.processing.filters import SeasonFilter
from f1.processing.standings import SeasonKpis

R, S, Q, P = (
    SessionKind.RACE,
    SessionKind.SPRINT,
    SessionKind.QUALIFYING,
    SessionKind.PRACTICE,
)
OPTIONS = season_options(datetime(2026, 5, 1, tzinfo=UTC))


def _kpis(**overrides) -> SeasonKpis:
    values = {
        "races": 24,
        "sprints": 6,
        "distinct_winners": 2,
        "leader_name": "Charles Leclerc",
        "leader_acronym": "LEC",
        "leader_points": 356.0,
        "events": 24,
        "events_won": 3,
        "filtered": True,
    }
    return SeasonKpis(**{**values, **overrides})


# --- frase-resumo --------------------------------------------------------


def test_summary_with_team_filter():
    assert summary_sentence(_kpis()) == (
        "**Charles Leclerc** lidera a seleção com **356** pontos; "
        "**2** pilotos da seleção venceram **3** de **24** corridas."
    )


def test_summary_with_filter_and_no_wins():
    text = summary_sentence(_kpis(distinct_winners=0, events_won=0))
    assert text.endswith("nenhum piloto da seleção venceu entre as **24** corridas.")


def test_summary_with_filter_and_no_points_kinds():
    text = summary_sentence(
        _kpis(
            leader_name=None,
            primary=(Q,),
            points_kinds=(),
            distinct_winners=1,
            events_won=2,
        )
    )
    assert text == "**1** piloto da seleção venceu **2** de **24** classificações."


def test_summary_for_qualifying_without_filter():
    text = summary_sentence(
        _kpis(
            leader_name=None,
            filtered=False,
            primary=(Q,),
            points_kinds=(),
            distinct_winners=5,
        )
    )
    assert text == (
        "**5** pilotos diferentes terminaram em 1º nas **24** classificações "
        "disputadas."
    )


def test_summary_for_sprints_only():
    text = summary_sentence(
        _kpis(
            filtered=False,
            primary=(S,),
            points_kinds=(S,),
            events=6,
            distinct_winners=4,
            leader_points=50.0,
        )
    )
    assert text.endswith("**4** pilotos diferentes venceram as **6** sprints.")


# --- legendas -------------------------------------------------------------


@pytest.mark.parametrize(
    ("kinds", "caption"),
    [
        ((R, S), "Corridas + sprints"),
        ((R,), "Só corridas"),
        ((S,), "Só sprints"),
        ((), "Os tipos selecionados não valem pontos"),
    ],
)
def test_points_caption(kinds, caption):
    assert points_caption(kinds) == caption


def test_points_subtitle_and_winners_caption():
    assert points_subtitle((R, S)).startswith("Soma dos pontos de corridas e sprints")
    assert points_subtitle((S,)).startswith("Soma dos pontos de sprints")
    assert winners_caption(_kpis(filtered=False)) == "Em corridas, sem contar sprints"
    assert winners_caption(_kpis()) == (
        "Em corridas, sem contar sprints · pilotos filtrados"
    )
    assert winners_caption(_kpis(filtered=False, primary=(Q, P))) == "Em sessões"


def test_session_label_and_nouns():
    assert session_label("Practice 1") == "Treino livre 1"
    assert session_label("Sprint Shootout") == "Classificação sprint"
    assert session_label("Day 1") == "Day 1"
    assert events_noun((R,), 1) == "corrida"
    assert events_noun((P,), 3) == "sessões de treino"
    assert events_noun((R, Q), 2) == "sessões"


# --- barra lateral --------------------------------------------------------


def test_season_options_and_initial_year():
    assert OPTIONS == [2026, 2025, 2024, 2023]
    assert initial_year(OPTIONS, "2023") == 2023
    assert initial_year(OPTIONS, None) == 2024
    assert initial_year(OPTIONS, "abc") == 2024
    assert initial_year(OPTIONS, "1999") == 2024
    assert initial_year([2023], None) == 2023


def test_selected_kinds_canonical_order():
    assert selected_kinds(["practice", "race"]) == (R, P)
    assert selected_kinds([]) == ()


# --- tabela de vencedores -----------------------------------------------


def _winners() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "round": [1, 1],
            "gp": ["Bahrain", "Bahrain"],
            "session_name": ["Sprint", "Qualifying"],
            "date_start": [datetime(2024, 3, 1, tzinfo=UTC)] * 2,
            "acronym": ["VER", "LEC"],
            "team": ["Red Bull Racing", "Ferrari"],
        }
    )


def test_winners_display_adds_session_column_when_needed():
    plain = winners_display(_winners())
    assert list(plain.columns) == ["Rod.", "GP", "Data", "Vencedor", "Equipe"]
    by_session = winners_display(_winners(), with_session=True)
    assert by_session["Sessão"].tolist() == ["Sprint", "Classificação"]
    assert by_session["Equipe"].tolist() == ["■ Red Bull Racing", "■ Ferrari"]


def test_table_styles_colour_team_and_highlight_row():
    display = winners_display(_winners())
    styles = table_styles(display, ["#3671C6", "#E8002D"], highlight=[1])

    assert styles.loc[0, "Equipe"] == "color: #3671C6"
    assert styles.loc[0, "GP"] == ""
    assert styles.loc[1, "GP"] == HIGHLIGHT_STYLE
    assert styles.loc[1, "Equipe"] == f"color: #E8002D; {HIGHLIGHT_STYLE}"


def test_selection_key_changes_with_filters():
    base = selection_key(2024, SeasonFilter())
    assert base != selection_key(2024, SeasonFilter(teams=("Red Bull Racing",)))
    assert base != selection_key(2024, SeasonFilter(kinds=(Q,)))
    assert base == selection_key(2024, SeasonFilter(meeting_key=1229))  # só destaca
