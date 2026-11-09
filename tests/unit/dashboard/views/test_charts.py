import pandas as pd
import pytest

from f1.dashboard.views import charts
from f1.dashboard.views.theme import (
    AXIS_DEFAULTS,
    COMPOUND_COLOURS,
    NO_TRANSLATE_SCRIPT,
    base_layout,
    kpi_card,
)
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


def _standings(rows: list[tuple[str, float, str | None]]) -> pd.DataFrame:
    """Tabela mínima do gráfico de pontos: (sigla, pontos, país ISO-2)."""
    return pd.DataFrame(
        {
            "acronym": [r[0] for r in rows],
            "points": [r[1] for r in rows],
            "country": [r[2] for r in rows],
            "name": [r[0] for r in rows],
            "team": ["T"] * len(rows),
            "colour": ["#FFFFFF"] * len(rows),
            "wins": [0] * len(rows),
            "podiums": [0] * len(rows),
        }
    )


def test_points_bar_flag_per_driver_on_its_category(frames):
    standings = driver_standings(
        frames[Endpoint.SESSION_RESULT],
        frames[Endpoint.SESSIONS],
        frames[Endpoint.DRIVERS],
    )
    fig = charts.points_bar(standings)

    images = fig.layout.images
    assert [i.source for i in images] == [
        "https://flagcdn.com/w40/es.png",  # SAI
        "https://flagcdn.com/w40/nl.png",  # VER
    ]
    assert [i.y for i in images] == [0, 1]  # posição da categoria no eixo Y
    assert all(i.yref == "y" and i.xanchor == "right" for i in images)
    assert all(i.x < 0 for i in images)  # antes do início das barras
    assert fig.layout.yaxis.ticklabelstandoff == charts.FLAG_STANDOFF
    assert fig.layout.margin.l > charts.FLAG_STANDOFF


def test_points_bar_driver_without_country_has_no_flag():
    fig = charts.points_bar(_standings([("AAA", 10, "br"), ("ZZZ", 5, None)]))

    assert list(fig.data[0].y) == ["AAA", "ZZZ"]  # piloto continua no gráfico
    assert [(i.source, i.y) for i in fig.layout.images] == [
        ("https://flagcdn.com/w40/br.png", 0)
    ]


def test_points_bar_without_any_country_keeps_default_axis():
    fig = charts.points_bar(_standings([("ZZZ", 5, None)]))

    assert fig.layout.images == ()
    assert fig.layout.yaxis.ticklabelstandoff == 0


@pytest.mark.parametrize("show_zero", [False, True])
def test_points_bar_flags_follow_zero_points_toggle(show_zero):
    from f1.dashboard.views.season import chart_standings  # noqa: PLC0415

    standings = _standings([("VER", 25, "nl"), ("NOR", 18, "gb"), ("BOR", 0, "br")])
    rows = chart_standings(standings, show_zero=show_zero)
    fig = charts.points_bar(rows)

    expected = ["nl", "gb", "br"] if show_zero else ["nl", "gb"]
    assert [i.source.split("/")[-1][:2] for i in fig.layout.images] == expected
    assert [i.y for i in fig.layout.images] == list(range(len(expected)))


def test_rejection_trend_chart_total_first_and_readable_axes():
    def frame(rate: float, **extra: object) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "run_id": ["r1"],
                "recorded_at": [pd.Timestamp("2026-11-09 10:19:44", tz="UTC")],
                "rejected": [2],
                "records_read": [526],
                "rate": [rate],
                "aborted": [False],
                **{k: [v] for k, v in extra.items()},
            }
        )

    fig = charts.rejection_trend_chart(frame(0.004), frame(0.004, rule="a:x"))

    assert [t.name for t in fig.data] == ["Total", "a:x"]
    assert fig.layout.showlegend is True
    assert fig.layout.yaxis.range[1] == charts.MIN_RATE_AXIS  # taxas pequenas
    stops = {s.value for s in fig.layout.xaxis.tickformatstops}
    assert "%H:%M:%S" in stops  # cargas com segundos de diferença


def test_rejection_trend_chart_only_total_without_rejections():
    totals = pd.DataFrame(
        {
            "run_id": ["r1"],
            "recorded_at": [pd.Timestamp("2026-11-09", tz="UTC")],
            "rejected": [0],
            "records_read": [10],
            "rate": [0.0],
            "aborted": [False],
        }
    )
    empty = pd.DataFrame(columns=[*totals.columns, "rule"])

    fig = charts.rejection_trend_chart(totals, empty)

    assert [t.name for t in fig.data] == ["Total"]


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
            "country": ["nl", "mx"],
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


def test_axes_reserve_space_for_labels(frames):
    """Rótulos longos não podem ser cortados (ex.: "DIREITO" → "REITO")."""
    standings = driver_standings(
        frames[Endpoint.SESSION_RESULT],
        frames[Endpoint.SESSIONS],
        frames[Endpoint.DRIVERS],
    )
    fig = charts.points_bar(standings)

    assert fig.layout.yaxis.automargin is True
    assert fig.layout.yaxis.autorange == "reversed"  # override mesclado


def test_base_layout_merges_axis_overrides():
    layout = base_layout(300, yaxis={"title": "s"})
    assert layout["yaxis"] == {**AXIS_DEFAULTS, "title": "s"}
    assert layout["xaxis"]["automargin"] is True


def test_no_translate_script_marks_page_as_portuguese():
    assert 'setAttribute("lang", "pt-BR")' in NO_TRANSLATE_SCRIPT
    assert 'setAttribute("translate", "no")' in NO_TRANSLATE_SCRIPT
    assert "notranslate" in NO_TRANSLATE_SCRIPT


# --- banner (hero) ---------------------------------------------------------


def test_hero_background_embeds_svg_as_base64(tmp_path):
    import base64  # noqa: PLC0415

    from f1.dashboard.views.theme import HERO_PATH, hero_background  # noqa: PLC0415

    assert HERO_PATH.name == "hero_red.svg"
    art = tmp_path / "hero_red.svg"
    art.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    uri = hero_background(art)
    assert uri is not None and uri.startswith("data:image/svg+xml;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]).startswith(b"<svg")
    assert hero_background(tmp_path / "missing.svg") is None


def test_hero_css_keeps_art_on_the_right():
    from f1.dashboard.views.theme import CSS  # noqa: PLC0415

    hero_css = CSS[CSS.index(".f1-hero {") :]
    assert "background-size: cover;" in hero_css
    assert "background-position: right center;" in hero_css


def test_hero_html_with_and_without_background():
    from f1.dashboard.views.theme import hero_html  # noqa: PLC0415

    banner = hero_html("Fórmula 1 · Temporada 2026", "<strong>X</strong>", "data:x")
    assert banner.startswith('<div class="f1-hero"')
    assert "url('data:x')" in banner
    assert '<div class="f1-title">Fórmula 1 · Temporada 2026</div>' in banner
    assert '<div class="f1-summary"><strong>X</strong></div>' in banner

    plain = hero_html("Título <b>", None, None)
    assert plain == '<div class="f1-title">Título &lt;b&gt;</div>'  # cabeçalho normal
