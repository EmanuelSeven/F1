"""Cópia do histórico de rejeições no Supabase (Postgres).

O disco do Streamlit Community Cloud é apagado a cada reinício, então cada
arquivo gravado no histórico local também é enviado à função
``record_rejections`` do Supabase, via API REST (PostgREST). O arquivo local
continua sendo a gravação principal: qualquer falha no Supabase é registrada e
ignorada, e a carga nunca quebra por causa dele.
"""

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from f1.domain.models import Partition
from f1.domain.ports import AppendStore
from f1.storage import rejection_history as history

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
RPC_PATH = "/rest/v1/rpc/record_rejections"


def history_payload(frame: pd.DataFrame, environment: str) -> list[dict[str, Any]]:
    """Linhas do histórico no formato esperado por ``record_rejections``.

    O próprio pandas converte para JSON: nulos viram ``null`` e datas, ISO 8601.
    """
    rows = frame[list(history.COLUMNS)].to_json(orient="records", date_format="iso")
    return [{"environment": environment} | row for row in json.loads(rows)]


class SupabaseHistorySink:
    """Envia as linhas de uma carga e partição à função ``record_rejections``."""

    def __init__(
        self,
        url: str,
        key: str,
        environment: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._endpoint = url.rstrip("/") + RPC_PATH
        # Só ``apikey``: a publishable key (``sb_publishable_...``) não é um
        # JWT, então não pode ir em ``Authorization: Bearer``.
        self._headers = {"apikey": key}
        self._environment = environment
        self._client = client

    def send(self, frame: pd.DataFrame) -> bool:
        """Grava as linhas; retorna ``False`` (e registra aviso) em qualquer erro."""
        payload = {"p_rows": history_payload(frame, self._environment)}
        try:
            if self._client is None:
                self._client = httpx.Client(timeout=TIMEOUT_SECONDS)
            response = self._client.post(
                self._endpoint, headers=self._headers, json=payload
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("rejection_history_remote_failed", extra={"error": str(exc)})
            return False
        return True


class MirroredHistoryStore:
    """Grava o histórico no disco e envia uma cópia ao Supabase."""

    def __init__(
        self, local: AppendStore[pd.DataFrame], remote: SupabaseHistorySink
    ) -> None:
        self._local = local
        self._remote = remote

    def append(self, dataset: str, partition: Partition, frame: pd.DataFrame) -> Path:
        path = self._local.append(dataset, partition, frame)
        self._remote.send(frame)
        return path
