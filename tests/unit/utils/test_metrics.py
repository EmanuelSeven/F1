import logging

import pytest

from f1.utils.metrics import new_run_id, track_pipeline


def test_track_pipeline_logs_start_and_finish(caplog):
    caplog.set_level(logging.INFO)
    with track_pipeline("laps", destination="data/silver/laps") as metrics:
        metrics.records_read = 3
        metrics.records_processed = 2
        metrics.records_rejected = 1

    messages = [r.getMessage() for r in caplog.records]
    assert messages == ["pipeline_started", "pipeline_finished"]
    finished = caplog.records[-1]
    assert finished.records_read == 3
    assert finished.records_rejected == 1
    assert finished.duration_seconds >= 0


def test_track_pipeline_uses_given_run_id():
    with track_pipeline("laps", destination="x", run_id="abc") as metrics:
        pass
    assert metrics.run_id == "abc"


def test_track_pipeline_logs_failure_and_reraises(caplog):
    caplog.set_level(logging.INFO)
    with pytest.raises(RuntimeError), track_pipeline("laps", destination="x"):
        raise RuntimeError("boom")

    failed = caplog.records[-1]
    assert failed.getMessage() == "pipeline_failed"
    assert failed.exc_info is not None


def test_new_run_id_is_unique_hex():
    first, second = new_run_id(), new_run_id()
    assert first != second
    assert len(first) == 32
