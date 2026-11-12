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
        # Clave: "{fp_id}::{nickname}". Valor: Identity.
        # Una participación es única por (nickname, fp_id): el mismo navegador
        # usado con dos nicknames distintos son dos identidades (dos seudónimos
        # linkeables, justo lo que la demo quiere mostrar). "Borrar mis datos"
        # elimina todas las identidades de un mismo fp_id.
        self._identities: dict[str, Identity] = {}
        self._chat: deque[ChatMessage] = deque(maxlen=settings.chat_history_limit)
        self._matches: deque[MatchEvent] = deque(maxlen=settings.match_history_limit)
        self._lock = asyncio.Lock()

    # --- Identidades ---

    @staticmethod
    def _key(nickname: str, fp_id: str) -> str:
        return f"{fp_id}::{nickname}"

    async def upsert_identity(self, identity: Identity) -> Identity:
        """Inserta o actualiza una identidad por (nickname, fp_id).

        Si ya existe una identidad con el mismo nickname y el mismo fp_id, la
        actualizamos (misma persona reconectándose) en vez de duplicar. Así
        cada participación única queda registrada una sola vez.
        """
        async with self._lock:
            key = self._key(identity.nickname, identity.fp_id)
            existing = self._identities.get(key)
            if existing:
                existing.fingerprint = identity.fingerprint
                existing.network = identity.network
                existing.avatar = identity.avatar
                existing.updated_at = datetime.now(timezone.utc)
                return existing
            self._identities[key] = identity
            return identity

    async def list_identities(self) -> list[Identity]:
        async with self._lock:
            return list(self._identities.values())

    async def delete_by_fp(self, fp_id: str) -> int:
        """Borra todas las identidades asociadas a un fp_id.

        Devuelve cuántas identidades se borraron, para que el endpoint pueda
        confirmar y los tests verificar. Como varias participaciones (nicknames)
        pueden compartir el mismo fp_id, borramos todas.
        """
        async with self._lock:
            keys = [k for k, v in self._identities.items() if v.fp_id == fp_id]
            for k in keys:
                del self._identities[k]
            return len(keys)

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
