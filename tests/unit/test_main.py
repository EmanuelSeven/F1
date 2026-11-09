import json

import pytest

from f1 import __main__ as cli
from f1.config.settings import Settings
from f1.domain.endpoints import SESSION_ENDPOINTS, Endpoint
from tests.conftest import FakeOpenF1Source


class _ClientStub(FakeOpenF1Source):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path)


@pytest.fixture(autouse=True)
def fake_client(monkeypatch, openf1_data):
    stub = _ClientStub(openf1_data)
    monkeypatch.setattr(cli.OpenF1Client, "from_settings", lambda _settings: stub)
    return stub


def test_parser_datasets_option():
    args = cli.build_parser().parse_args(
        ["season", "--year", "2026", "--datasets", "laps,pit_stops"]
    )
    assert args.datasets == (Endpoint.LAPS, Endpoint.PIT)
    default = cli.build_parser().parse_args(["meeting", "--meeting-key", "1"])
    assert default.datasets == SESSION_ENDPOINTS


def test_parser_rejects_unknown_dataset(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ["season", "--year", "2026", "--datasets", "car_data"]
        )
    assert "car_data" in capsys.readouterr().err


def test_main_meeting_command(settings, tmp_path, capsys):
    assert (
        cli.main(["meeting", "--meeting-key", "1219", "--datasets", "laps"], settings)
        == 0
    )

    assert (
        tmp_path / "silver/laps/season=2023/meeting_key=1219/part-00000.parquet"
    ).exists()
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    messages = [e["message"] for e in events]
    assert messages[0] == "run_started"
    assert "pipeline_finished" in messages
    assert len({e["run_id"] for e in events if "run_id" in e}) == 1


def test_main_calendar_and_season_commands(settings, tmp_path):
    assert cli.main(["calendar", "--year", "2023"], settings) == 0
    assert cli.main(["season", "--year", "2023", "--datasets", "stints"], settings) == 0

    assert (tmp_path / "silver/meetings/season=2023/part-00000.parquet").exists()
    assert (tmp_path / "silver/stints/season=2023/meeting_key=1219").exists()
