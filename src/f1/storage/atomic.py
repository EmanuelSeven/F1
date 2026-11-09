"""Operações de arquivo atômicas e seguras para gravações concorrentes.

Duas gravações na mesma partição (ex.: duas abas do dashboard, ou o dashboard e
a CLI ao mesmo tempo) não podem compartilhar diretórios temporários nem deixar
a partição final faltando. Por isso:

- cada gravação usa um nome temporário único (prefixo ``_``, ignorado pelos
  leitores do lake);
- a troca da partição é serializada por um lock por caminho dentro do processo
  e, entre processos, é feita por renomeações com nova tentativa;
- temporários órfãos de execuções interrompidas são removidos depois de
  ``STALE_AFTER_SECONDS``.
"""

import logging
import os
import shutil
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

SWAP_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 0.05
STALE_AFTER_SECONDS = 300
TEMP_SUFFIXES = (".staging", ".old", ".tmp")

_locks: dict[Path, threading.Lock] = {}
_locks_guard = threading.Lock()


@contextmanager
def path_lock(path: Path) -> Iterator[None]:
    """Serializa, dentro do processo, operações sobre o mesmo caminho."""
    key = path.absolute()
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        yield


def temp_sibling(path: Path, suffix: str) -> Path:
    """Caminho temporário único ao lado de ``path`` (ex.: ``_nome.ab12cd34.tmp``)."""
    return path.with_name(f"_{path.name}.{uuid4().hex[:8]}{suffix}")


def swap_directory(staging: Path, target: Path) -> None:
    """Substitui ``target`` por ``staging`` (último gravador vence).

    A partição antiga é renomeada para um backup antes de ``staging`` assumir o
    nome final, e só então é apagada.

    Raises:
        OSError: se a troca não for possível após ``SWAP_ATTEMPTS`` tentativas.
    """
    last_error: OSError | None = None
    for _attempt in range(SWAP_ATTEMPTS):
        try:
            backup = _move_aside(target)
        except OSError as exc:  # ex.: arquivo aberto por outro processo no Windows
            last_error = exc
            time.sleep(RETRY_DELAY_SECONDS)
            continue
        try:
            staging.rename(target)
        except OSError as exc:  # outro gravador recriou a partição no meio da troca
            last_error = exc
            if backup is not None:
                _remove_tree(backup)
            time.sleep(RETRY_DELAY_SECONDS)
            continue
        if backup is not None:
            _remove_tree(backup)
        return
    _remove_tree(staging)
    raise OSError(f"could not replace {target}") from last_error


def _move_aside(target: Path) -> Path | None:
    """Renomeia ``target`` para um backup; ``None`` se ele não existir."""
    backup = temp_sibling(target, ".old")
    try:
        target.rename(backup)
    except FileNotFoundError:
        return None  # partição ainda não existe (ou outro processo a moveu)
    return backup


def replace_file(source: Path, target: Path) -> None:
    """``os.replace`` com nova tentativa (no Windows o destino pode estar aberto)."""
    for attempt in range(SWAP_ATTEMPTS):
        try:
            os.replace(source, target)
        except PermissionError:
            if attempt == SWAP_ATTEMPTS - 1:
                source.unlink(missing_ok=True)
                raise
            time.sleep(RETRY_DELAY_SECONDS)
        else:
            return


def remove_stale_temps(
    target: Path, max_age_seconds: float = STALE_AFTER_SECONDS
) -> int:
    """Apaga temporários órfãos de ``target`` mais antigos que ``max_age_seconds``.

    Considera ``_{nome}.*`` com sufixo temporário (inclui o formato antigo
    ``_{nome}.staging``). Retorna quantos foram removidos.
    """
    parent = target.parent
    if not parent.is_dir():
        return 0
    prefix = f"_{target.name}."
    limit = time.time() - max_age_seconds
    removed = 0
    for candidate in parent.iterdir():
        name = candidate.name
        if not (name.startswith(prefix) and name.endswith(TEMP_SUFFIXES)):
            continue
        try:
            if candidate.stat().st_mtime > limit:
                continue
        except FileNotFoundError:
            continue
        _remove_tree(candidate)
        removed += 1
    return removed


def _remove_tree(path: Path) -> None:
    """Remoção de temporário: falhas são registradas, não propagadas.

    Temporários têm prefixo ``_`` e são ignorados pelos leitores; se a remoção
    falhar agora, ``remove_stale_temps`` tenta de novo numa próxima gravação.
    """
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning(
            "temp_cleanup_failed", extra={"path": str(path), "error": str(exc)}
        )
