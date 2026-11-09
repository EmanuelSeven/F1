"""Contador de acessos (Supabase), sem rede: ``httpx.MockTransport``."""

import json
import logging

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from f1.config.settings import Settings
from f1.dashboard import visits
from f1.dashboard.visits import RPC_PATH, register_visit

URL = "https://projeto.supabase.co"
KEY = "sb_publishable_chave"


def _settings(url: str | None = URL, key: str | None = KEY) -> Settings:
    return Settings(supabase_url=url, supabase_key=key)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_success_returns_updated_total():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=1234)

    assert register_visit(_settings(url=URL + "/"), _client(handler)) == 1234
    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == URL + RPC_PATH
    assert request.headers["apikey"] == KEY
    assert "Authorization" not in request.headers
    assert json.loads(request.content) == {}


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"message": "erro"}),
        httpx.Response(401, json={"message": "Invalid API key"}),
        httpx.Response(200, content=b"<html>"),  # JSON inválido
        httpx.Response(200, json={"total": 3}),  # formato inesperado
        httpx.Response(200, json=None),
    ],
)
def test_bad_response_returns_none(response, caplog):
    with caplog.at_level(logging.WARNING, logger=visits.__name__):
        assert register_visit(_settings(), _client(lambda _r: response)) is None
    assert "page_views_failed" in caplog.text


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("timeout"), httpx.ConnectError("sem rede")]
)
def test_network_error_returns_none(error, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    with caplog.at_level(logging.WARNING, logger=visits.__name__):
        assert register_visit(_settings(), _client(handler)) is None
    assert "page_views_failed" in caplog.text
    assert KEY not in caplog.text


@pytest.mark.parametrize(
    ("url", "key"), [(None, KEY), (URL, None), ("", ""), (URL, "")]
)
def test_without_config_makes_no_request(url, key):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("não deveria chamar o Supabase")

    assert register_visit(_settings(url, key), _client(handler)) is None


def _session_script() -> None:
    import streamlit as st  # noqa: PLC0415

    from f1.config.settings import Settings  # noqa: PLC0415
    from f1.dashboard.visits import session_page_views  # noqa: PLC0415

    st.write(str(session_page_views(Settings())))
    st.button("rerun")


def test_counts_once_per_session(monkeypatch):
    calls: list[int] = []

    def fake(_settings, client=None):
        calls.append(1)
        return 41 + len(calls)

    monkeypatch.setattr(visits, "register_visit", fake)
    app = AppTest.from_function(_session_script)
    app.run()
    app.button[0].click().run()
    app.run()
    assert not app.exception
    assert app.markdown[0].value == "42"
    assert calls == [1]


def test_failure_is_not_retried_on_rerun(monkeypatch):
    calls: list[int] = []

    def fake(_settings, client=None):
        calls.append(1)

    monkeypatch.setattr(visits, "register_visit", fake)
    app = AppTest.from_function(_session_script)
    app.run()
    app.run()
    assert app.markdown[0].value == "None"
    assert calls == [1]


def test_own_client_uses_short_timeout(monkeypatch):
    created: list[dict] = []
    real_client = httpx.Client

    def factory(**kwargs):
        created.append(kwargs)
        transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=7))
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(visits.httpx, "Client", factory)
    assert register_visit(_settings()) == 7
    assert created == [{"timeout": visits.TIMEOUT_SECONDS}]


def test_unexpected_error_does_not_break_the_page(monkeypatch):
    """Ex.: ``Settings`` antigo em memória, sem ``supabase_url``."""

    def broken(_settings, client=None):
        raise AttributeError("'Settings' object has no attribute 'supabase_url'")

    monkeypatch.setattr(visits, "register_visit", broken)
    app = AppTest.from_function(_session_script)
    app.run()
    assert not app.exception
    assert app.markdown[0].value == "None"
