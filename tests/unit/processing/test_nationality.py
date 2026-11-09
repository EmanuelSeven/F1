import pytest

from f1.domain.endpoints import Endpoint
from f1.processing.nationality import (
    COUNTRY_ISO2,
    acronym_nationalities,
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
        (None, "ZZZ", None),  # sem nacionalidade conhecida
        (None, None, None),
    ],
)
def test_nationality_fallback(code, acronym, expected):
    assert nationality(code, acronym) == expected


@pytest.mark.parametrize(
    ("acronym", "iso2"),
    [
        ("VER", "nl"),
        ("NOR", "gb"),
        ("LEC", "mc"),
        ("ANT", "it"),
        ("BOR", "br"),
    ],
)
def test_acronym_to_iso2_when_country_code_is_null(acronym, iso2):
    """Sigla → ISO-2 pelo arquivo versionado quando a OpenF1 não manda o país."""
    assert nationality(None, acronym) == iso2


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
                "name_acronym": "ZZZ",
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


# --- nacionalidade desconhecida e cobertura de 2026 ------------------------

# Todos os pilotos que aparecem nos dados de 2026 da OpenF1 (titulares,
# reservas e estreantes de treino livre), conferidos em 08/11/2026.
DRIVERS_2026 = [
    "ALB",
    "ALO",
    "ANT",
    "ARO",
    "BEA",
    "BEG",
    "BOR",
    "BOT",
    "BRO",
    "CAM",
    "COL",
    "CRA",
    "FOR",
    "GAS",
    "HAD",
    "HAM",
    "HER",
    "HIR",
    "HUL",
    "IWA",
    "LAW",
    "LEC",
    "LIN",
    "MIN",
    "NOR",
    "OCO",
    "PER",
    "PIA",
    "RUS",
    "SAI",
    "SLA",
    "STR",
    "TSO",
    "TSU",
    "VER",
    "VES",
]


def test_rafael_camara_is_brazilian():
    assert nationality(None, "CAM") == "br"


def test_mapping_covers_every_2026_driver():
    missing = [a for a in DRIVERS_2026 if a not in acronym_nationalities()]
    assert missing == []


@pytest.fixture
def fresh_reports():
    from f1.processing import nationality as module  # noqa: PLC0415

    module._reported.clear()
    yield
    module._reported.clear()


def test_unknown_nationality_is_logged_once(fresh_reports, caplog):
    from f1.processing.nationality import report_unknown  # noqa: PLC0415

    with caplog.at_level("WARNING"):
        report_unknown("ZZZ", "Fulano de Tal")
        report_unknown("ZZZ", "Fulano de Tal")  # repetido: não loga de novo
        report_unknown("YYY", "Beltrano")

    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        "nacionalidade desconhecida: ZZZ Fulano de Tal",
        "nacionalidade desconhecida: YYY Beltrano",
    ]
    assert caplog.records[0].driver_acronym == "ZZZ"


def test_driver_info_reports_only_unknown_drivers(fresh_reports, caplog):
    drivers = normalize(
        Endpoint.DRIVERS,
        [
            {
                "session_key": 1,
                "meeting_key": 1,
                "driver_number": 7,
                "name_acronym": "ZZZ",
                "first_name": "Novo",
                "last_name": "Piloto",
            },
            {
                "session_key": 1,
                "meeting_key": 1,
                "driver_number": 5,
                "name_acronym": "CAM",
                "first_name": "Rafael",
                "last_name": "Camara",
            },
        ],
    )
    with caplog.at_level("WARNING"):
        info = driver_info(drivers)

    assert info["country"].tolist() == [None, "br"]
    assert [r.getMessage() for r in caplog.records] == [
        "nacionalidade desconhecida: ZZZ Novo Piloto"
    ]
