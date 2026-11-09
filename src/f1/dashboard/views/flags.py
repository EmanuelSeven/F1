"""Nacionalidade como imagem: bandeira + nome do país em português.

O Windows não exibe emoji de bandeira, então cada célula é uma imagem SVG
(``data:`` URI) gerada aqui. Um SVG exibido como imagem não carrega URLs
externas; por isso a bandeira é baixada do flagcdn uma vez e embutida em
base64. Bandeiras baixadas ficam em cache na memória e em disco; sem internet,
a célula mostra só o nome do país.
"""

import base64
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from xml.sax.saxutils import escape

import httpx
from babel import Locale

logger = logging.getLogger(__name__)

FLAG_SVG_URL = "https://flagcdn.com/{code}.svg"
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

_memory: dict[str, str] = {}


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


def nationality_image(
    code: str | None, cache_dir: Path, download: Downloader | None = None
) -> str | None:
    """``data:`` URI da célula "Nacionalidade" (``None`` sem nacionalidade)."""
    if not code:
        return None
    svg = nationality_svg(country_name(code), flag_base64(code, cache_dir, download))
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
