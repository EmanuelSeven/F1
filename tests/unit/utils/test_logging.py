import json
import logging
import sys

from f1.utils.logging import JsonFormatter, configure_logging


def _record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("f1.test", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_includes_standard_fields_and_extras():
    payload = json.loads(JsonFormatter().format(_record(rows=10)))

    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "f1.test"
    assert payload["rows"] == 10
    assert "args" not in payload


def test_json_formatter_includes_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "f1", logging.ERROR, __file__, 1, "failed", None, sys.exc_info()
        )
    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]


def test_configure_logging_sets_json_handler(capsys):
    configure_logging("debug")
    logging.getLogger("f1.x").info("event", extra={"k": "v"})

    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(line)["k"] == "v"
    assert logging.getLogger().level == logging.DEBUG
