import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest

from f1.storage import atomic
from f1.storage.atomic import remove_stale_temps, replace_file, swap_directory
from f1.storage.bronze import write_json_atomic
from f1.storage.parquet_writer import PART_FILE, read_partition, write_partition

WRITERS = 16


def _leftovers(parent: Path) -> list[str]:
    return sorted(p.name for p in parent.iterdir() if p.name.startswith("_"))


def _age(path: Path, seconds: float) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_concurrent_writes_to_same_partition_do_not_collide(tmp_path):
    """Regressão: FileExistsError em '_season=2024.staging' com gravações paralelas."""
    target = tmp_path / "meetings" / "season=2024"
    frames = [pd.DataFrame({"writer": [n] * 50}) for n in range(WRITERS)]

    with ThreadPoolExecutor(max_workers=WRITERS) as pool:
        list(pool.map(lambda df: write_partition(df, target), frames))

    result = read_partition(target)
    assert len(result) == 50
    assert result["writer"].nunique() == 1  # uma gravação inteira venceu
    assert _leftovers(target.parent) == []


def test_concurrent_bronze_writes_do_not_collide(tmp_path):
    target = tmp_path / "laps" / "session_key=1.json"

    with ThreadPoolExecutor(max_workers=WRITERS) as pool:
        list(pool.map(lambda n: write_json_atomic(target, [{"n": n}]), range(WRITERS)))

    assert len(json.loads(target.read_text(encoding="utf-8"))) == 1
    assert _leftovers(target.parent) == []


def test_write_removes_stale_legacy_staging(tmp_path):
    target = tmp_path / "meetings" / "season=2024"
    stale = target.with_name("_season=2024.staging")  # formato antigo, órfão
    stale.mkdir(parents=True)
    _age(stale, atomic.STALE_AFTER_SECONDS + 60)
    recent = target.with_name("_season=2024.abcd1234.staging")  # em uso por outro
    recent.mkdir()

    write_partition(pd.DataFrame({"a": [1]}), target)

    assert not stale.exists()
    assert recent.exists()
    assert (target / PART_FILE).is_file()


def test_remove_stale_temps_ignores_other_entries(tmp_path):
    target = tmp_path / "season=2024"
    other = tmp_path / "_season=2023.staging"
    other.mkdir()
    _age(other, 10_000)
    temp_file = tmp_path / "_season=2024.x.tmp"
    temp_file.write_text("x", encoding="utf-8")
    _age(temp_file, 10_000)

    assert remove_stale_temps(target) == 1
    assert other.exists()
    assert not temp_file.exists()
    assert remove_stale_temps(tmp_path / "missing" / "x") == 0


def test_swap_retries_when_target_reappears(tmp_path, monkeypatch):
    staging = tmp_path / "_p.staging"
    staging.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")
    target = tmp_path / "p"
    original = Path.rename
    calls = {"n": 0}

    def flaky(self, dest):
        if self == staging and calls["n"] == 0:
            calls["n"] += 1
            raise FileExistsError(183, "outro gravador venceu")
        return original(self, dest)

    monkeypatch.setattr(Path, "rename", flaky)
    monkeypatch.setattr(atomic, "RETRY_DELAY_SECONDS", 0)

    swap_directory(staging, target)

    assert (target / "new.txt").read_text(encoding="utf-8") == "new"
    assert calls["n"] == 1


def test_swap_gives_up_and_cleans_staging(tmp_path, monkeypatch):
    staging = tmp_path / "_p.staging"
    staging.mkdir()
    target = tmp_path / "p"
    target.mkdir()
    monkeypatch.setattr(atomic, "RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(
        atomic, "_move_aside", lambda _t: (_ for _ in ()).throw(PermissionError("x"))
    )

    with pytest.raises(OSError, match="could not replace"):
        swap_directory(staging, target)
    assert not staging.exists()
    assert target.exists()  # a partição anterior não foi perdida


def test_replace_file_retries_permission_error(tmp_path, monkeypatch):
    source = tmp_path / "_a.tmp"
    source.write_text("ok", encoding="utf-8")
    target = tmp_path / "a.json"
    original = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("arquivo aberto")
        return original(src, dst)

    monkeypatch.setattr(atomic.os, "replace", flaky)
    monkeypatch.setattr(atomic, "RETRY_DELAY_SECONDS", 0)

    replace_file(source, target)
    assert target.read_text(encoding="utf-8") == "ok"


def test_replace_file_gives_up(tmp_path, monkeypatch):
    source = tmp_path / "_a.tmp"
    source.write_text("ok", encoding="utf-8")

    def always_locked(_src, _dst):
        raise PermissionError("arquivo aberto")

    monkeypatch.setattr(atomic.os, "replace", always_locked)
    monkeypatch.setattr(atomic, "RETRY_DELAY_SECONDS", 0)

    with pytest.raises(PermissionError):
        replace_file(source, tmp_path / "a.json")
    assert not source.exists()


def test_cleanup_failure_is_logged_not_raised(tmp_path, monkeypatch, caplog):
    folder = tmp_path / "_x.old"
    folder.mkdir()

    def locked(_path):
        raise PermissionError("em uso")

    monkeypatch.setattr(atomic.shutil, "rmtree", locked)
    with caplog.at_level(logging.WARNING):
        atomic._remove_tree(folder)

    assert caplog.records[-1].getMessage() == "temp_cleanup_failed"
    assert folder.exists()
