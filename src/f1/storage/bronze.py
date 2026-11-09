"""Camada bronze: JSON bruto exatamente como retornado pela API."""

import json
from collections.abc import Sequence
from pathlib import Path

from f1.domain.endpoints import Endpoint
from f1.domain.models import Partition, Record
from f1.storage.atomic import path_lock, remove_stale_temps, replace_file, temp_sibling
from f1.storage.paths import partition_path


def write_json_atomic(path: Path, records: Sequence[Record]) -> Path:
    """Grava ``records`` em ``path`` via arquivo temporário exclusivo + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = temp_sibling(path, ".tmp")
    tmp.write_text(
        json.dumps(list(records), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    with path_lock(path):
        replace_file(tmp, path)
        remove_stale_temps(path)
    return path


class JsonRawStore:
    """Implementa ``RawStore``: ``{base}/{endpoint}/{partição}/{name}.json``."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def write(
        self,
        endpoint: Endpoint,
        partition: Partition,
        name: str,
        records: Sequence[Record],
    ) -> Path:
        target = partition_path(self._base, endpoint.value, partition) / f"{name}.json"
        return write_json_atomic(target, records)
