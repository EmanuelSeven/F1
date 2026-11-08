import pytest

from f1.config.settings import Settings
from f1.dashboard.bootstrap import BOOTSTRAP_YEAR, run_initial_calendar
from f1.dashboard.loaders import is_lake_empty
from f1.domain.endpoints import Endpoint
from f1.ingestion.openf1_client import OpenF1AccessError
from tests.conftest import FakeOpenF1Source


class StubClient(FakeOpenF1Source):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


class DeniedClient(StubClient):
    def fetch(self, endpoint, filters=()):
        raise OpenF1AccessError("Live F1 session in progress")


def test_run_initial_calendar_writes_lake(tmp_path, openf1_data):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    stub = StubClient(openf1_data)

    result = run_initial_calendar(settings, year=2023, source_factory=lambda _: stub)

    assert (result.year, result.meetings) == (2023, 1)
    assert len(result.run_id) == 32
    assert not is_lake_empty(tmp_path)
    assert (tmp_path / "silver/meetings/season=2023/part-00000.parquet").exists()
    assert stub.calls[0][0] is Endpoint.MEETINGS


def test_run_initial_calendar_defaults_to_2024(tmp_path, openf1_data):
    stub = StubClient(openf1_data)
    result = run_initial_calendar(
        Settings(_env_file=None, data_dir=tmp_path), source_factory=lambda _: stub
    )
    assert result.year == BOOTSTRAP_YEAR == 2024


def test_run_initial_calendar_propagates_access_error(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    with pytest.raises(OpenF1AccessError):
        run_initial_calendar(settings, source_factory=lambda _: DeniedClient({}))
    assert is_lake_empty(tmp_path)


def test_is_lake_empty(tmp_path, populated_lake):
    assert is_lake_empty(tmp_path / "missing")
    (tmp_path / "staging" / "silver" / "laps" / "_x.staging").mkdir(parents=True)
    assert is_lake_empty(tmp_path / "staging")
    assert not is_lake_empty(populated_lake)
