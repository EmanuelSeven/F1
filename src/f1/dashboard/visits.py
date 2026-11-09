"""Contador de acessos do dashboard, guardado no Supabase (Postgres).

O Streamlit Community Cloud apaga o disco a cada reinício, então o total fica
numa tabela do Supabase, incrementada pela função ``increment_page_views`` via
API REST (PostgREST). Sem ``F1_SUPABASE_URL`` e ``F1_SUPABASE_KEY`` o contador
fica desligado. Qualquer falha é registrada e ignorada: o dashboard nunca
quebra por causa do contador.
"""

import logging

import httpx
import streamlit as st

from f1.config.settings import Settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 3.0
RPC_PATH = "/rest/v1/rpc/increment_page_views"
KEY_PAGE_VIEWS = "page_views"


def register_visit(
    settings: Settings, client: httpx.Client | None = None
) -> int | None:
    """Soma um acesso e devolve o total atualizado.

    Retorna ``None`` se o contador estiver desligado ou em qualquer erro.
    """
    url, key = settings.supabase_url, settings.supabase_key
    if not url or not key:
        return None
    # Só ``apikey``: a publishable key (``sb_publishable_...``) não é um JWT,
    # então não pode ir em ``Authorization: Bearer``.
    headers = {"apikey": key}
    endpoint = url.rstrip("/") + RPC_PATH
    try:
        if client is None:
            with httpx.Client(timeout=TIMEOUT_SECONDS) as own:
                response = own.post(endpoint, headers=headers, json={})
        else:
            response = client.post(
                endpoint, headers=headers, json={}, timeout=TIMEOUT_SECONDS
            )
        response.raise_for_status()
        total = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("page_views_failed", extra={"error": str(exc)})
        return None
    if isinstance(total, bool) or not isinstance(total, int):
        logger.warning("page_views_failed", extra={"error": f"resposta {total!r}"})
        return None
    return total


def session_page_views(settings: Settings) -> int | None:
    """Total de acessos, contando uma única vez por sessão do navegador.

    O resultado (inclusive ``None``, em caso de falha) fica em
    ``st.session_state``: reruns, troca de página e filtros não contam de novo
    nem repetem a requisição.
    """
    state = st.session_state
    if KEY_PAGE_VIEWS not in state:
        state[KEY_PAGE_VIEWS] = register_visit(settings)
    value = state[KEY_PAGE_VIEWS]
    return value if isinstance(value, int) else None
