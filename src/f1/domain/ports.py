"""Contratos que a infraestrutura deve implementar."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from f1.domain.endpoints import Endpoint
from f1.domain.models import Filter, Partition, Record


class OpenF1Source(Protocol):
    def fetch(
        self, endpoint: Endpoint, filters: Sequence[Filter] = ()
    ) -> list[Record]: ...


class RawStore(Protocol):
    def write(
        self,
        endpoint: Endpoint,
        partition: Partition,
        name: str,
        records: Sequence[Record],
    ) -> Path: ...


class DatasetStore[FrameT](Protocol):
    def write_partition(
        self, dataset: str, partition: Partition, frame: FrameT
    ) -> Path | None: ...


class AppendStore[FrameT](Protocol):
    """Store que só acrescenta (não sobrescreve cargas anteriores)."""

    def append(self, dataset: str, partition: Partition, frame: FrameT) -> Path: ...
