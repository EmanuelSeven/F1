"""Nacionalidade dos pilotos (código ISO 3166-1 alfa-2) para exibir bandeiras.

Fonte, em ordem:

1. ``drivers.country_code`` da OpenF1 (3 letras, padrão olímpico — ex.: ``NED``,
   ``GER``, ``MON`` — ou ISO alfa-3), convertido por ``COUNTRY_ISO2``;
2. se vier vazio (o campo está depreciado e chega vazio a partir de 2026), o
   mapeamento fixo por sigla do piloto em ``data/driver_nationalities.json``;
3. sem nenhum dos dois: ``None`` (sem bandeira).
"""

import json
import logging
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType

logger = logging.getLogger(__name__)

NATIONALITIES_FILE = "driver_nationalities.json"

# Códigos olímpicos usados pela F1 e equivalentes ISO alfa-3 → ISO alfa-2.
COUNTRY_ISO2: Mapping[str, str] = MappingProxyType(
    {
        "ARE": "ae", "UAE": "ae",
        "ARG": "ar",
        "AUS": "au",
        "AUT": "at",
        "BEL": "be",
        "BGR": "bg", "BUL": "bg",
        "BRA": "br",
        "CAN": "ca",
        "CHE": "ch", "SUI": "ch",
        "CHL": "cl", "CHI": "cl",
        "CHN": "cn",
        "COL": "co",
        "CZE": "cz",
        "DEU": "de", "GER": "de",
        "DNK": "dk", "DEN": "dk",
        "ESP": "es",
        "EST": "ee",
        "FIN": "fi",
        "FRA": "fr",
        "GBR": "gb",
        "HUN": "hu",
        "IDN": "id", "INA": "id",
        "IND": "in",
        "IRL": "ie",
        "ISR": "il",
        "ITA": "it",
        "JPN": "jp",
        "MCO": "mc", "MON": "mc",
        "MEX": "mx",
        "MYS": "my", "MAS": "my",
        "NLD": "nl", "NED": "nl",
        "NZL": "nz",
        "POL": "pl",
        "PRT": "pt", "POR": "pt",
        "RUS": "ru",
        "SAU": "sa", "KSA": "sa",
        "SWE": "se",
        "THA": "th",
        "URY": "uy", "URU": "uy",
        "USA": "us",
        "VEN": "ve",
        "ZAF": "za", "RSA": "za",
    }
)  # fmt: skip


def to_iso2(country_code: object) -> str | None:
    """``"NED"`` → ``"nl"``; código vazio ou desconhecido → ``None``."""
    if not isinstance(country_code, str):
        return None
    return COUNTRY_ISO2.get(country_code.strip().upper())


@lru_cache
def acronym_nationalities() -> Mapping[str, str]:
    """Mapeamento fixo sigla → nacionalidade (arquivo versionado no pacote)."""
    path = files("f1.processing").joinpath("data", NATIONALITIES_FILE)
    raw: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return MappingProxyType(
        {k.upper(): v.lower() for k, v in raw.items() if not k.startswith("_")}
    )


def nationality(country_code: object, acronym: object) -> str | None:
    """Nacionalidade do piloto: ``country_code`` ou, se vazio, pela sigla."""
    code = to_iso2(country_code)
    if code is not None:
        return code
    if isinstance(acronym, str):
        return acronym_nationalities().get(acronym.strip().upper())
    return None


_reported: set[tuple[str, str]] = set()


def report_unknown(acronym: object, name: object) -> None:
    """Avisa no log, uma vez por piloto, que falta a nacionalidade.

    Sinal para incluir o piloto em ``data/driver_nationalities.json``.
    """
    key = (str(acronym or "—"), str(name or "—"))
    if key in _reported:
        return
    _reported.add(key)
    logger.warning(
        "nacionalidade desconhecida: %s %s",
        *key,
        extra={"driver_acronym": key[0], "driver_name": key[1]},
    )
