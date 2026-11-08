from collections.abc import Callable

import httpx
import pytest

from f1.config.settings import Settings
from f1.domain.endpoints import Endpoint
from f1.domain.models import Filter, Operator
from f1.ingestion.openf1_client import OpenF1AccessError, OpenF1Client, OpenF1Error

BASE_URL = "https://api.test/v1"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    clock: FakeClock,
    **kwargs,
) -> OpenF1Client:
    transport = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenF1Client(
        BASE_URL, client=transport, sleep=clock.sleep, clock=clock, **kwargs
    )


def test_fetch_builds_url_and_returns_records():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=[{"lap_number": 1}])

    with make_client(handler, FakeClock()) as client:
        records = client.fetch(
            Endpoint.LAPS,
            [Filter("session_key", 9161), Filter("lap_number", 3, Operator.GTE)],
        )

    assert records == [{"lap_number": 1}]
    assert seen == [f"{BASE_URL}/laps?session_key=9161&lap_number%3E%3D3"]


def test_fetch_without_filters_has_no_query():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=[])

    assert make_client(handler, FakeClock()).fetch(Endpoint.MEETINGS) == []
    assert seen == [f"{BASE_URL}/meetings"]


def test_fetch_retries_on_429_honoring_retry_after():
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(503),
            httpx.Response(200, json=[{"a": 1}]),
        ]
    )
    clock = FakeClock()
    client = make_client(lambda _: next(responses), clock, request_interval_seconds=0)

    assert client.fetch(Endpoint.PIT) == [{"a": 1}]
    assert clock.sleeps == [3.0, 1.0]


def test_fetch_retries_on_timeout_then_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    clock = FakeClock()
    client = make_client(handler, clock, max_retries=2, request_interval_seconds=0)

    with pytest.raises(OpenF1Error, match="failed"):
        client.fetch(Endpoint.LAPS)
    assert clock.sleeps == [0.5, 1.0]


def test_fetch_raises_after_retries_exhausted_on_5xx():
    client = make_client(
        lambda _: httpx.Response(500, text="oops"), FakeClock(), max_retries=1
    )
    with pytest.raises(OpenF1Error, match="500: oops"):
        client.fetch(Endpoint.LAPS)


def test_fetch_404_is_empty_list():
    client = make_client(lambda _: httpx.Response(404), FakeClock())
    assert client.fetch(Endpoint.WEATHER) == []


def test_fetch_401_raises_access_error_without_retry():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"detail": "Live F1 session in progress"})

    with pytest.raises(OpenF1AccessError, match="Live F1 session"):
        make_client(handler, FakeClock()).fetch(Endpoint.LAPS)
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [{"a": 1}, [1, 2]])
def test_fetch_rejects_unexpected_payload(payload):
    client = make_client(lambda _: httpx.Response(200, json=payload), FakeClock())
    with pytest.raises(OpenF1Error, match="unexpected payload"):
        client.fetch(Endpoint.LAPS)


def test_fetch_respects_min_interval_between_requests():
    clock = FakeClock()
    client = make_client(
        lambda _: httpx.Response(200, json=[]), clock, request_interval_seconds=0.5
    )
    client.fetch(Endpoint.LAPS)
    clock.now += 0.2
    client.fetch(Endpoint.LAPS)

    assert clock.sleeps == [pytest.approx(0.3)]


def test_from_settings_uses_configuration():
    settings = Settings(_env_file=None, api_base_url=BASE_URL + "/")
    client = OpenF1Client.from_settings(
        settings,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
        ),
    )
    assert client.fetch(Endpoint.LAPS) == []
    client.close()
