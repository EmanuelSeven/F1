import copy
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from f1.domain.endpoints import Endpoint
from f1.domain.models import Filter, Operator, Record

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "openf1"


def load_fixture(endpoint: Endpoint) -> list[Record]:
    path = FIXTURES_DIR / f"{endpoint.value}.json"
    return json.loads(path.read_text(encoding="utf-8"))


class FakeOpenF1Source:
    """Fonte em memória que aplica filtros de igualdade sobre as fixtures."""

    def __init__(self, data: dict[Endpoint, list[Record]]) -> None:
        self._data = data
        self.calls: list[tuple[Endpoint, tuple[Filter, ...]]] = []

    def fetch(self, endpoint: Endpoint, filters: Sequence[Filter] = ()) -> list[Record]:
        self.calls.append((endpoint, tuple(filters)))
        records = self._data.get(endpoint, [])
        return [copy.deepcopy(r) for r in records if _matches(r, filters)]


def _matches(record: Record, filters: Sequence[Filter]) -> bool:
    for item in filters:
        if item.op is not Operator.EQ:
            raise NotImplementedError("fake source only supports '='")
        if record.get(item.field) not in item.values():
            return False
    return True


@pytest.fixture
def openf1_data() -> dict[Endpoint, list[Record]]:
    return {endpoint: load_fixture(endpoint) for endpoint in Endpoint}


@pytest.fixture
def fake_source(openf1_data) -> FakeOpenF1Source:
    return FakeOpenF1Source(openf1_data)
