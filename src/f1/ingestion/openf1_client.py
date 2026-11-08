"""Cliente HTTP da OpenF1 com retry, backoff e intervalo mínimo entre requisições."""

import logging
import time
from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Self

import httpx

from f1.config.settings import Settings
from f1.domain.endpoints import Endpoint
from f1.domain.models import Filter, Record
from f1.ingestion.query import build_query

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
BASE_BACKOFF_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 30.0
HTTP_NOT_FOUND = 404
HTTP_ACCESS_DENIED = frozenset({401, 403})


class OpenF1Error(Exception):
    """Falha ao obter dados da OpenF1."""


class OpenF1AccessError(OpenF1Error):
    """Acesso negado (ex.: sessão ao vivo em andamento bloqueia o acesso gratuito)."""


class OpenF1Client:
    """Implementa ``OpenF1Source`` sobre ``httpx``."""

    def __init__(  # noqa: PLR0913 - parâmetros de configuração explícitos
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 5,
        request_interval_seconds: float = 0.5,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._max_retries = max_retries
        self._interval = request_interval_seconds
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None

    @classmethod
    def from_settings(
        cls, settings: Settings, client: httpx.Client | None = None
    ) -> "OpenF1Client":
        return cls(
            settings.api_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            max_retries=settings.http_max_retries,
            request_interval_seconds=settings.request_interval_seconds,
            client=client,
        )

    def fetch(self, endpoint: Endpoint, filters: Sequence[Filter] = ()) -> list[Record]:
        url = self._url(endpoint, filters)
        for attempt in range(self._max_retries + 1):
            is_last = attempt == self._max_retries
            started = self._throttle()
            try:
                response = self._client.get(url)
            except httpx.TransportError as exc:
                if is_last:
                    raise OpenF1Error(f"request to {endpoint} failed: {exc}") from exc
                self._wait_retry(endpoint, attempt, None, repr(exc))
                continue
            if response.status_code in RETRYABLE_STATUS and not is_last:
                self._wait_retry(endpoint, attempt, response, response.status_code)
                continue
            records = self._parse(endpoint, response)
            logger.info(
                "openf1_request",
                extra={
                    "endpoint": str(endpoint),
                    "status": response.status_code,
                    "records": len(records),
                    "attempt": attempt,
                    "elapsed_seconds": round(self._clock() - started, 3),
                },
            )
            return records
        raise OpenF1Error("unreachable")  # pragma: no cover

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _url(self, endpoint: Endpoint, filters: Sequence[Filter]) -> str:
        query = build_query(filters)
        url = f"{self._base_url}/{endpoint.value}"
        return f"{url}?{query}" if query else url

    def _throttle(self) -> float:
        now = self._clock()
        if self._last_request is not None:
            wait = self._interval - (now - self._last_request)
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
        self._last_request = now
        return now

    def _wait_retry(
        self,
        endpoint: Endpoint,
        attempt: int,
        response: httpx.Response | None,
        reason: object,
    ) -> None:
        delay = _retry_after(response) or min(
            BASE_BACKOFF_SECONDS * 2**attempt, MAX_BACKOFF_SECONDS
        )
        logger.warning(
            "openf1_retry",
            extra={
                "endpoint": str(endpoint),
                "attempt": attempt,
                "reason": str(reason),
                "delay_seconds": delay,
            },
        )
        self._sleep(delay)

    @staticmethod
    def _parse(endpoint: Endpoint, response: httpx.Response) -> list[Record]:
        status = response.status_code
        if status == HTTP_NOT_FOUND:
            return []
        if status in HTTP_ACCESS_DENIED:
            raise OpenF1AccessError(
                f"access denied for {endpoint} ({status}): {_detail(response)}"
            )
        if response.is_error:
            raise OpenF1Error(f"{endpoint} returned {status}: {_detail(response)}")
        payload: object = response.json()
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise OpenF1Error(f"{endpoint} returned an unexpected payload")
        return payload


def _retry_after(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    value = response.headers.get("Retry-After", "")
    try:
        seconds = float(value)
    except ValueError:
        return None
    return min(max(seconds, 0.0), MAX_BACKOFF_SECONDS * 2)


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(payload, dict) and "detail" in payload:
        return str(payload["detail"])[:200]
    return str(payload)[:200]
