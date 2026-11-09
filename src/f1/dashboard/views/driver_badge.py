"""Nacionalidade dos pilotos no dashboard: módulo único e reutilizável.

- ``nationality_of(driver)`` → ``(iso2, país em pt_BR)`` a partir de
  ``f1.processing.nationality`` (``country_code`` com fallback por sigla) e
  dos nomes de país do Babel;
- ``flag_html(iso2)`` → ``<img>`` 20x14 para cartões e textos;
- ``driver_html(driver)`` → ``"[bandeira] Nome Sobrenome"``;
- ``flag_country_image(iso2)`` → ``data:`` URI SVG (bandeira + país) para
  ``st.column_config.ImageColumn``;
- ``country_label(iso2)`` → nome do país para tooltips de gráficos;
- ``flag_png_url(iso2)`` → URL PNG do flagcdn para imagens em gráficos Plotly.

O Windows não exibe emoji de bandeira, por isso tudo usa imagens. A bandeira
SVG é baixada do flagcdn uma vez e EMBUTIDA em base64 (um SVG exibido como
imagem não carrega URLs externas), com cache em memória e em disco. Sem
nacionalidade conhecida ou sem internet, a bandeira não aparece e nada quebra.
"""

import base64
import html
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple
from xml.sax.saxutils import escape

import httpx
import pandas as pd
from babel import Locale

from f1.config.settings import get_settings
from f1.processing.nationality import nationality

logger = logging.getLogger(__name__)

FLAG_SVG_URL = "https://flagcdn.com/{code}.svg"
FLAG_PNG_URL = "https://flagcdn.com/w40/{code}.png"
DOWNLOAD_TIMEOUT_SECONDS = 5.0
LOCALE = Locale("pt", "BR")

# Exceções aos nomes do Babel, por código ISO alfa-2 em maiúsculas.
# Ex.: {"NL": "Holanda"} para usar "Holanda" em vez de "Países Baixos".
COUNTRY_NAME_OVERRIDES: Mapping[str, str] = MappingProxyType({})

IMAGE_WIDTH, IMAGE_HEIGHT = 140, 24
FLAG_WIDTH, FLAG_HEIGHT = 20, 14
TEXT_GAP = 8
TEXT_COLOUR = "#e6e6e6"
BORDER_COLOUR = "#8a8a8a"

type Downloader = Callable[[str], bytes | None]
# Linha de tabela do pandas ou registro (precisa de ``name``/``acronym`` e
# ``country`` ou ``country_code``).
type DriverLike = Mapping[str, object] | pd.Series

_memory: dict[str, str] = {}

# Célula de imagem vazia (transparente), para nacionalidade desconhecida.
EMPTY_CELL = "data:image/svg+xml;base64," + base64.b64encode(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{IMAGE_WIDTH}" '
    f'height="{IMAGE_HEIGHT}"/>'.encode()
).decode("ascii")


def country_name(code: str, overrides: Mapping[str, str] | None = None) -> str:
    """Nome do país em português do Brasil (``"gb"`` → ``"Reino Unido"``).

    Usa ``overrides`` (padrão: ``COUNTRY_NAME_OVERRIDES``) antes do Babel e cai
    no próprio código quando o país é desconhecido.
    """
    key = code.strip().upper()
    table = COUNTRY_NAME_OVERRIDES if overrides is None else overrides
    if key in table:
        return table[key]
    name = LOCALE.territories.get(key)
    return str(name) if name else key


def download_flag(code: str) -> bytes | None:
    """Baixa a bandeira SVG do flagcdn (``None`` em qualquer falha)."""
    url = FLAG_SVG_URL.format(code=code)
    try:
        response = httpx.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("flag_download_failed", extra={"code": code, "error": str(exc)})
        return None
    return response.content


def flag_base64(
    code: str, cache_dir: Path, download: Downloader | None = None
) -> str | None:
    """Bandeira em base64, com cache em memória e em disco.

    Falhas não ficam em cache: uma nova tentativa acontece na próxima chamada.
    """
    key = code.strip().lower()
    if key in _memory:
        return _memory[key]
    path = cache_dir / f"{key}.svg"
    data: bytes | None = path.read_bytes() if path.is_file() else None
    if data is None:
        data = (download or download_flag)(key)
        if data is None:
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:  # sem disco: segue só com o cache em memória
            logger.warning(
                "flag_cache_failed", extra={"path": str(path), "error": str(exc)}
            )
    encoded = base64.b64encode(data).decode("ascii")
    _memory[key] = encoded
    return encoded


def _xml_text(text: str) -> str:
    """Escapa ``&``, ``<``, ``>`` e aspas para uso em XML."""
    return escape(text, {'"': "&quot;", "'": "&apos;"})


def nationality_svg(name: str, flag: str | None) -> str:
    """SVG ~140x24, fundo transparente: bandeira (20x14) + nome do país.

    ``flag`` é a bandeira SVG em base64 (``None``: só o nome).
    """
    middle = IMAGE_HEIGHT / 2
    text_x = FLAG_WIDTH + TEXT_GAP if flag else 0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{IMAGE_WIDTH}" '
        f'height="{IMAGE_HEIGHT}" viewBox="0 0 {IMAGE_WIDTH} {IMAGE_HEIGHT}">'
    ]
    if flag:
        top = (IMAGE_HEIGHT - FLAG_HEIGHT) / 2
        parts += [
            f'<defs><clipPath id="r"><rect x="0" y="{top}" width="{FLAG_WIDTH}" '
            f'height="{FLAG_HEIGHT}" rx="2"/></clipPath></defs>',
            f'<image href="data:image/svg+xml;base64,{flag}" x="0" y="{top}" '
            f'width="{FLAG_WIDTH}" height="{FLAG_HEIGHT}" '
            'preserveAspectRatio="xMidYMid slice" clip-path="url(#r)"/>',
            f'<rect x="0.25" y="{top + 0.25}" width="{FLAG_WIDTH - 0.5}" '
            f'height="{FLAG_HEIGHT - 0.5}" rx="2" fill="none" '
            f'stroke="{BORDER_COLOUR}" stroke-opacity="0.6" stroke-width="0.5"/>',
        ]
    parts += [
        f'<text x="{text_x}" y="{middle}" dominant-baseline="central" '
        f'fill="{TEXT_COLOUR}" font-size="12" '
        'font-family="Segoe UI, Helvetica, Arial, sans-serif">'
        f"{_xml_text(name)}</text>",
        "</svg>",
    ]
    return "".join(parts)


def flag_country_image(
    code: str | None,
    cache_dir: Path | None = None,
    download: Downloader | None = None,
) -> str | None:
    """``data:`` URI da célula "Nacionalidade" (``None`` sem nacionalidade).

    Sem bandeira disponível (ex.: sem internet), mostra só o nome do país.
    """
    if not code:
        return None
    flag = flag_base64(code, cache_dir or flags_cache_dir(), download)
    svg = nationality_svg(country_name(code), flag)
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


class Nationality(NamedTuple):
    iso2: str
    country: str


def flags_cache_dir() -> Path:
    """Cache em disco das bandeiras baixadas (fora das camadas do lake)."""
    return get_settings().data_dir / "cache" / "flags"


def _iso2(value: object) -> str | None:
    if isinstance(value, str) and len(value.strip()) == 2:  # noqa: PLR2004 - ISO alfa-2
        return value.strip().lower()
    return None


def nationality_of(driver: DriverLike) -> Nationality | None:
    """Nacionalidade de um piloto (linha de tabela ou registro da OpenF1).

    Usa ``country`` (ISO alfa-2 já calculado pelas agregações) ou, na falta
    dele, ``country_code`` com fallback por sigla (``acronym``/``name_acronym``).
    """
    code = _iso2(driver.get("country"))
    if code is None:
        acronym = driver.get("acronym") or driver.get("name_acronym")
        code = _iso2(nationality(driver.get("country_code"), acronym))
    return None if code is None else Nationality(code, country_name(code))


def flag_png_url(code: object) -> str | None:
    """URL da bandeira PNG (40 px) no flagcdn (``None`` sem nacionalidade).

    Para gráficos Plotly (``layout.images``): o navegador baixa a imagem; sem
    internet, a bandeira só não aparece.
    """
    iso2 = _iso2(code)
    return None if iso2 is None else FLAG_PNG_URL.format(code=iso2)


def country_label(code: object) -> str:
    """Nome do país em português (``"—"`` sem nacionalidade), para tooltips."""
    iso2 = _iso2(code)
    return "—" if iso2 is None else country_name(iso2)


def flag_html(
    code: object, cache_dir: Path | None = None, download: Downloader | None = None
) -> str:
    """``<img>`` 20x14 da bandeira (vazio se não houver bandeira)."""
    iso2 = _iso2(code)
    if iso2 is None:
        return ""
    flag = flag_base64(iso2, cache_dir or flags_cache_dir(), download)
    if flag is None:
        return ""
    country = html.escape(country_name(iso2))
    return (
        f'<img class="f1-flag" src="data:image/svg+xml;base64,{flag}" '
        f'width="{FLAG_WIDTH}" height="{FLAG_HEIGHT}" alt="{country}" '
        f'title="{country}" style="border-radius: 2px; object-fit: cover; '
        f"box-shadow: 0 0 0 0.5px {BORDER_COLOUR}; vertical-align: -2px; "
        'margin-right: 6px">'
    )


def driver_html(
    driver: DriverLike,
    cache_dir: Path | None = None,
    download: Downloader | None = None,
) -> str:
    """``"[bandeira] Nome Sobrenome"`` em HTML (nome escapado)."""
    name = html.escape(str(driver.get("name") or driver.get("acronym") or "—"))
    nat = nationality_of(driver)
    flag = "" if nat is None else flag_html(nat.iso2, cache_dir, download)
    return f"{flag}{name}"
