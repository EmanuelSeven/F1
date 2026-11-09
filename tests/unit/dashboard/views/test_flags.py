"""Coluna "Nacionalidade": SVG com bandeira embutida + nome em português."""

import base64
import xml.etree.ElementTree as ET

import pytest

from f1.dashboard.views import flags
from f1.dashboard.views.flags import (
    country_name,
    flag_base64,
    nationality_image,
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
    with_flag = _decode(nationality_image("gb", tmp_path, lambda _code: FLAG))
    assert "<image" in with_flag and ">Reino Unido</text>" in with_flag

    offline = _decode(nationality_image("br", tmp_path, lambda _code: None))
    assert "<image" not in offline and ">Brasil</text>" in offline

    assert nationality_image(None, tmp_path) is None
    assert nationality_image("", tmp_path) is None


def test_download_flag_handles_network_errors(monkeypatch):
    import httpx  # noqa: PLC0415

    def boom(*_args, **_kwargs):
        raise httpx.ConnectError("sem internet")

    monkeypatch.undo()  # volta o download real (o fixture autouse o substitui)
    monkeypatch.setattr(flags.httpx, "get", boom)
    assert flags.download_flag.__module__ == "f1.dashboard.views.flags"
    assert flags.download_flag("gb") is None
