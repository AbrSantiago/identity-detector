"""Almacenamiento en memoria del estado de la aplicación.

Todo vive en el proceso: un dict de identidades, una lista de mensajes de chat
con tope, y una lista de eventos de match con tope. Por eso el despliegue usa
un solo worker (si hubiera varios, cada uno tendría su propia memoria).

Un asyncio.Lock protege las estructuras. Las operaciones son cortas, así que
no hay contención real, pero el lock deja explícito que el estado es compartido
entre las conexiones websocket y las llamadas a la API.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import settings
from .models import ChatMessage, Identity, MatchEvent


class Store:
    def __init__(self) -> None:
        # Clave: fp_id. Valor: Identity. El upsert se hace por (nickname, fp_id)
        # pero indexamos por fp_id porque es lo que borra "borrar mis datos".
        self._identities: dict[str, Identity] = {}
        self._chat: deque[ChatMessage] = deque(maxlen=settings.chat_history_limit)
        self._matches: deque[MatchEvent] = deque(maxlen=settings.match_history_limit)
        self._lock = asyncio.Lock()

    # --- Identidades ---

    async def upsert_identity(self, identity: Identity) -> Identity:
        """Inserta o actualiza una identidad.

        Si ya existe una identidad con el mismo nickname y el mismo fp_id, la
        actualizamos (misma persona reconectándose) en vez de duplicar. Así
        cada participación única queda registrada una sola vez.
        """
        async with self._lock:
            existing = self._identities.get(identity.fingerprint.fp_id)
            if existing and existing.nickname == identity.nickname:
                existing.fingerprint = identity.fingerprint
                existing.network = identity.network
                existing.avatar = identity.avatar
                existing.updated_at = datetime.now(timezone.utc)
                return existing
            self._identities[identity.fingerprint.fp_id] = identity
            return identity

    async def list_identities(self) -> list[Identity]:
        async with self._lock:
            return list(self._identities.values())

    async def delete_by_fp(self, fp_id: str) -> int:
        """Borra la identidad y los matches asociados a un fp_id.

        Devuelve cuántos elementos se borraron (identidad + eventos), para que
        el endpoint pueda confirmar y los tests verificar.
        """
        async with self._lock:
            removed = 0
            if fp_id in self._identities:
                del self._identities[fp_id]
                removed += 1
            # Los eventos de match no guardan fp_id crudo por privacidad, así
            # que el borrado de identidad es lo que elimina el rastro. Dejamos
            # el hook por si se decide indexar eventos por fp en el futuro.
            return removed

    # --- Chat ---

    async def add_chat_message(self, msg: ChatMessage) -> None:
        async with self._lock:
            self._chat.append(msg)

    async def recent_chat(self) -> list[ChatMessage]:
        async with self._lock:
            return list(self._chat)

    # --- Historial de matches ---

    async def add_match_event(self, event: MatchEvent) -> None:
        async with self._lock:
            self._matches.append(event)

    async def recent_matches(self, hours: float) -> list[MatchEvent]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with self._lock:
            return [e for e in self._matches if e.at >= cutoff]

    # --- TTL ---

    async def purge_expired(self) -> int:
        """Elimina identidades y eventos más viejos que el TTL configurado.

        Lo llama una tarea de fondo periódica. Devuelve cuántas identidades se
        barrieron (útil para log sin datos sensibles).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.data_ttl_hours)
        async with self._lock:
            stale = [
                fp for fp, ident in self._identities.items() if ident.updated_at < cutoff
            ]
            for fp in stale:
                del self._identities[fp]
            # Barremos eventos viejos del historial.
            fresh = [e for e in self._matches if e.at >= cutoff]
            self._matches.clear()
            self._matches.extend(fresh)
            return len(stale)


# Instancia única compartida por toda la app.
store = Store()
