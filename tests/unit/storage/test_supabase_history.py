"""Cópia do histórico no Supabase, sem rede: ``httpx.MockTransport``."""

import json
import logging
from datetime import UTC, datetime

import httpx
import pandas as pd
import pytest

from f1.config.settings import Settings
from f1.domain.models import Partition
from f1.pipelines.factory import build_stores
from f1.storage import supabase_history
from f1.storage.rejection_history import RejectionHistoryStore, rejection_rows
from f1.storage.supabase_history import (
    RPC_PATH,
    MirroredHistoryStore,
    SupabaseHistorySink,
    history_payload,
)

URL = "https://projeto.supabase.co"
KEY = "sb_publishable_chave"
PARTITION = Partition(2026, 1298)


def _rows(reasons: list[str]) -> pd.DataFrame:
    return rejection_rows(
        run_id="r1",
        recorded_at=datetime(2026, 11, 14, 19, tzinfo=UTC),
        dataset="pit_stops",
        partition=PARTITION,
        rejected=pd.DataFrame({"_reject_reason": reasons}),
        records_read=612,
        aborted=False,
        rules_version=2,
    )


def _sink(handler, environment: str = "cloud") -> SupabaseHistorySink:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SupabaseHistorySink(URL + "/", KEY, environment, client)


def test_payload_matches_function_columns():
    [row] = history_payload(_rows(["driver_number:x", "driver_number:x"]), "cloud")

    assert row == {
        "environment": "cloud",
        "run_id": "r1",
        "recorded_at": "2026-11-14T19:00:00.000Z",
        "dataset": "pit_stops",
        "season": 2026,
        "meeting_key": 1298,
        "rule": "driver_number:x",
        "rejected": 2,
        "records_read": 612,
        "aborted": False,
        "rows_rejected": 2,
        "rules_version": 2,
    }
    json.dumps(row)  # serializável


def test_payload_clean_load_and_season_partition_use_null():
    frame = _rows([]).assign(meeting_key=pd.array([None], dtype="Int64"))

    [row] = history_payload(frame, "local")

    assert (row["rule"], row["meeting_key"], row["rejected"]) == (None, None, 0)


def test_send_posts_rows_with_publishable_key():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=1)

    assert _sink(handler).send(_rows(["a:x"])) is True
    (request,) = seen
    assert str(request.url) == URL + RPC_PATH
    assert request.headers["apikey"] == KEY
    assert "Authorization" not in request.headers
    body = json.loads(request.content)
    assert [r["environment"] for r in body["p_rows"]] == ["cloud"]


@pytest.mark.parametrize(
    "reply",
    [
        lambda _r: httpx.Response(400, json={"message": "violates check"}),
        lambda _r: httpx.Response(401, json={"message": "Invalid API key"}),
        lambda _r: (_ for _ in ()).throw(httpx.ConnectError("sem rede")),
        lambda _r: (_ for _ in ()).throw(httpx.ReadTimeout("timeout")),
    ],
)
def test_send_failure_only_warns(reply, caplog):
    with caplog.at_level(logging.WARNING, logger=supabase_history.__name__):
        assert _sink(reply).send(_rows(["a:x"])) is False
    assert "rejection_history_remote_failed" in caplog.text


def test_mirror_writes_local_even_when_supabase_fails(tmp_path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "fora do ar"})

    store = MirroredHistoryStore(RejectionHistoryStore(tmp_path), _sink(handler))

    path = store.append("pit_stops", PARTITION, _rows(["a:x"]))

    assert path.exists()
    assert pd.read_parquet(path)["rejected"].tolist() == [1]


def test_build_stores_mirrors_only_with_supabase_settings(tmp_path):
    local = build_stores(Settings(data_dir=tmp_path, supabase_url="", supabase_key=""))
    mirrored = build_stores(
        Settings(data_dir=tmp_path, supabase_url=URL, supabase_key=KEY)
    )

    assert isinstance(local.rejections, RejectionHistoryStore)
    assert isinstance(mirrored.rejections, MirroredHistoryStore)


def test_history_environment_defaults_to_local(monkeypatch):
    monkeypatch.delenv("F1_HISTORY_ENVIRONMENT", raising=False)
    assert Settings(_env_file=None).history_environment == "local"
    with pytest.raises(ValueError):
        Settings(_env_file=None, history_environment="prod")
