import pytest

from f1.domain.endpoints import Endpoint
from f1.processing.nationality import (
    COUNTRY_ISO2,
    acronym_nationalities,
    flag_url,
    nationality,
    to_iso2,
)
from f1.processing.normalize import normalize
from f1.processing.standings import driver_info

# --- conversão de 3 para 2 letras ------------------------------------------


@pytest.mark.parametrize(
    ("code", "iso2"),
    [
        ("GBR", "gb"),
        ("NED", "nl"),  # olímpico (usado pela OpenF1)
        ("NLD", "nl"),  # ISO alfa-3
        ("MON", "mc"),
        ("MCO", "mc"),
        ("GER", "de"),
        ("DEU", "de"),
        ("SUI", "ch"),
        ("THA", "th"),
        (" esp ", "es"),  # espaços e caixa
        ("USA", "us"),
    ],
)
def test_to_iso2_converts_known_codes(code, iso2):
    assert to_iso2(code) == iso2


@pytest.mark.parametrize("code", [None, "", "XYZ", "GB", 123, float("nan")])
def test_to_iso2_unknown_or_empty_is_none(code):
    assert to_iso2(code) is None


def test_country_table_is_consistent():
    assert all(len(k) == 3 and k.isupper() for k in COUNTRY_ISO2)
    assert all(len(v) == 2 and v.islower() for v in COUNTRY_ISO2.values())


# --- fallback por sigla (arquivo versionado) -------------------------------


def test_acronym_file_covers_examples_and_is_well_formed():
    mapping = acronym_nationalities()
    examples = {"NOR": "gb", "VER": "nl", "ANT": "it", "RUS": "gb", "HAM": "gb"}
    assert {k: mapping[k] for k in examples} == examples
    assert mapping["LEC"] == "mc"
    assert "_COMMENT" not in mapping
    assert all(len(k) == 3 and k.isupper() for k in mapping)
    assert all(len(v) == 2 and v.islower() for v in mapping.values())


@pytest.mark.parametrize(
    ("code", "acronym", "expected"),
    [
        ("NED", "VER", "nl"),  # country_code tem prioridade
        ("GBR", "VER", "gb"),  # ...mesmo se divergir do arquivo
        (None, "NOR", "gb"),  # vazio: usa a sigla (dados de 2026)
        ("", "ANT", "it"),
        ("XYZ", "LEC", "mc"),  # código desconhecido: usa a sigla
        (None, " ver ", "nl"),
        (None, "CAM", None),  # sem nacionalidade conhecida
        (None, None, None),
    ],
)
def test_nationality_fallback(code, acronym, expected):
    assert nationality(code, acronym) == expected


def test_flag_url():
    assert flag_url("gb") == "https://flagcdn.com/w20/gb.png"
    assert flag_url("NL") == "https://flagcdn.com/w20/nl.png"
    assert flag_url(None) is None
    assert flag_url("gbr") is None


def test_driver_info_country_uses_code_then_acronym():
    drivers = normalize(
        Endpoint.DRIVERS,
        [
            {
                "session_key": 1,
                "meeting_key": 1,
                "driver_number": 1,
                "name_acronym": "VER",
                "country_code": "NED",
            },
            {
                "session_key": 1,
                "meeting_key": 1,
                "driver_number": 4,
                "name_acronym": "NOR",
                "country_code": None,
            },
            {
                "session_key": 1,
                "meeting_key": 1,
                "driver_number": 99,
                "name_acronym": "CAM",
            },
        ],
    )
    info = driver_info(drivers)
    assert info["country"].tolist() == ["nl", "gb", None]


def test_driver_info_without_country_column():
    """Partições antigas do silver não têm ``country_code``."""
    drivers = normalize(
        Endpoint.DRIVERS,
        [
            {
                "session_key": 1,
                "meeting_key": 1,
                "driver_number": 16,
                "name_acronym": "LEC",
            }
        ],
    ).drop(columns=["country_code"])
    assert driver_info(drivers)["country"].tolist() == ["mc"]
