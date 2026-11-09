"""Módulo driver_badge: nacionalidade dos pilotos em todo o dashboard."""

import base64
import xml.etree.ElementTree as ET

import pytest

from f1.dashboard.views import driver_badge as flags
from f1.dashboard.views.driver_badge import (
    Nationality,
    country_label,
    country_name,
    driver_html,
    flag_base64,
    flag_country_image,
    flag_html,
    nationality_of,
    nationality_svg,
)

SVG_NS = "{http://www.w3.org/2000/svg}"
FLAG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3 2"/>'


def _parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)  # noqa: S314 - SVG gerado pelo próprio código


def _decode(uri: str) -> str:
    assert uri.startswith("data:image/svg+xml;base64,")
    return base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")


# --- tradução com Babel e exceções -----------------------------------------


@pytest.mark.parametrize(
    ("code", "name"),
    [
        ("gb", "Reino Unido"),
        ("nl", "Países Baixos"),
        ("mc", "Mônaco"),
        ("NZ", "Nova Zelândia"),
        ("us", "Estados Unidos"),
    ],
)
def test_country_name_in_brazilian_portuguese(code, name):
    assert country_name(code) == name


def test_country_name_overrides():
    assert country_name("nl", {"NL": "Holanda"}) == "Holanda"
    assert country_name("gb", {"NL": "Holanda"}) == "Reino Unido"


def test_default_overrides_can_be_changed(monkeypatch):
    monkeypatch.setattr(flags, "COUNTRY_NAME_OVERRIDES", {"NL": "Holanda"})
    assert country_name("nl") == "Holanda"


def test_country_name_unknown_falls_back_to_code():
    assert country_name("xx") == "XX"


# --- geração do SVG --------------------------------------------------------


def test_svg_with_embedded_flag():
    flag = base64.b64encode(FLAG).decode("ascii")
    root = _parse(nationality_svg("Reino Unido", flag))

    assert (root.get("width"), root.get("height")) == ("140", "24")
    image = root.find(f"{SVG_NS}image")
    assert image is not None
    assert image.get("href") == f"data:image/svg+xml;base64,{flag}"  # embutida
    assert (image.get("width"), image.get("height"), image.get("x")) == (
        "20",
        "14",
        "0",
    )
    border = root.findall(f"{SVG_NS}rect")[-1]
    assert border.get("rx") == "2" and border.get("stroke") == "#8a8a8a"
    text = root.find(f"{SVG_NS}text")
    assert text is not None and text.text == "Reino Unido"
    assert text.get("x") == "28"  # 20 da bandeira + 8 de espaço
    assert text.get("fill") == "#e6e6e6"
    assert text.get("font-size") == "12"
    assert "sans-serif" in text.get("font-family", "")
    assert text.get("dominant-baseline") == "central"


def test_svg_escapes_special_characters():
    svg = nationality_svg('Trinidad & Tobago <"x">', None)
    assert "&amp;" in svg and "&lt;" in svg and "&quot;" in svg
    assert _parse(svg).find(f"{SVG_NS}text").text == 'Trinidad & Tobago <"x">'


def test_svg_without_flag_shows_only_the_name():
    root = _parse(nationality_svg("Brasil", None))
    assert root.find(f"{SVG_NS}image") is None
    assert root.find(f"{SVG_NS}text").get("x") == "0"


# --- download, cache e fallback ------------------------------------------


def test_flag_is_downloaded_once_and_cached(tmp_path):
    calls: list[str] = []

    def download(code: str) -> bytes:
        calls.append(code)
        return FLAG

    first = flag_base64("GB", tmp_path, download)
    assert base64.b64decode(first) == FLAG
    assert (tmp_path / "gb.svg").read_bytes() == FLAG  # cache em disco
    assert flag_base64("gb", tmp_path, download) == first  # cache em memória
    flags._memory.clear()
    assert flag_base64("gb", tmp_path, download) == first  # lido do disco
    assert calls == ["gb"]


def test_failed_download_is_not_cached(tmp_path):
    assert flag_base64("fr", tmp_path, lambda _code: None) is None
    assert not (tmp_path / "fr.svg").exists()
    assert flag_base64("fr", tmp_path, lambda _code: FLAG) is not None  # nova tentativa


def test_nationality_image_with_and_without_flag(tmp_path):
    with_flag = _decode(flag_country_image("gb", tmp_path, lambda _code: FLAG))
    assert "<image" in with_flag and ">Reino Unido</text>" in with_flag

    offline = _decode(flag_country_image("br", tmp_path, lambda _code: None))
    assert "<image" not in offline and ">Brasil</text>" in offline

    assert flag_country_image(None, tmp_path) is None
    assert flag_country_image("", tmp_path) is None


def test_download_flag_handles_network_errors(monkeypatch):
    import httpx  # noqa: PLC0415

    def boom(*_args, **_kwargs):
        raise httpx.ConnectError("sem internet")

    monkeypatch.undo()  # volta o download real (o fixture autouse o substitui)
    monkeypatch.setattr(flags.httpx, "get", boom)
    assert flags.download_flag.__module__ == "f1.dashboard.views.driver_badge"
    assert flags.download_flag("gb") is None


# --- nacionalidade de um piloto --------------------------------------------


@pytest.mark.parametrize(
    ("driver", "expected"),
    [
        ({"country": "gb"}, ("gb", "Reino Unido")),  # já calculado
        ({"country_code": "NED", "acronym": "VER"}, ("nl", "Países Baixos")),
        ({"country_code": None, "acronym": "LEC"}, ("mc", "Mônaco")),  # sigla
        ({"country_code": "", "name_acronym": "ANT"}, ("it", "Itália")),
        ({"country": None, "acronym": "NOR"}, ("gb", "Reino Unido")),
    ],
)
def test_nationality_of(driver, expected):
    assert nationality_of(driver) == Nationality(*expected)


@pytest.mark.parametrize(
    "driver", [{"acronym": "CAM"}, {}, {"country": "gbr"}, {"country": float("nan")}]
)
def test_nationality_of_unknown_is_none(driver):
    assert nationality_of(driver) is None


def test_nationality_of_accepts_a_table_row():
    import pandas as pd  # noqa: PLC0415

    row = pd.Series({"name": "Lando Norris", "acronym": "NOR", "country": "gb"})
    assert nationality_of(row) == ("gb", "Reino Unido")


def test_country_label():
    assert country_label("br") == "Brasil"
    assert country_label(None) == "—"


# --- HTML para cartões e textos ---------------------------------------------


def test_flag_html_is_a_small_embedded_image(tmp_path):
    tag = flag_html("gb", tmp_path, lambda _code: FLAG)

    assert tag.startswith('<img class="f1-flag" src="data:image/svg+xml;base64,')
    assert 'width="20" height="14"' in tag
    assert "border-radius: 2px" in tag and "box-shadow: 0 0 0 0.5px" in tag
    assert 'alt="Reino Unido"' in tag
    assert "flagcdn.com" not in tag  # embutida (funciona com o cache, sem rede)


def test_flag_html_without_flag_is_empty(tmp_path):
    assert flag_html("gb", tmp_path, lambda _code: None) == ""  # sem internet
    assert flag_html(None, tmp_path) == ""
    assert flag_html("xyz", tmp_path) == ""


def test_driver_html(tmp_path):
    driver = {"name": "Lando Norris", "acronym": "NOR", "country": "gb"}
    html = driver_html(driver, tmp_path, lambda _code: FLAG)
    assert html.startswith('<img class="f1-flag"')
    assert html.endswith("Lando Norris")

    flags._memory.clear()
    offline = driver_html(driver, tmp_path / "x", lambda _code: None)
    assert offline == "Lando Norris"  # sem bandeira, sem quebrar

    unknown = driver_html({"name": "A <b>&</b>", "acronym": "CAM"}, tmp_path)
    assert unknown == "A &lt;b&gt;&amp;&lt;/b&gt;"  # nome escapado, sem bandeira


def test_flag_country_image_uses_default_cache_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(flags, "flags_cache_dir", lambda: tmp_path)
    uri = flag_country_image("gb", download=lambda _code: FLAG)
    assert "<image" in _decode(uri)
    assert (tmp_path / "gb.svg").is_file()
