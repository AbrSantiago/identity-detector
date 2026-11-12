"""Chat anónimo en tiempo real por WebSocket.

Flujo:
  1. El cliente abre WS /ws/chat y manda un primer mensaje "hello" con
     nickname, avatar y su fingerprint (recolectado por tracker/fp.js).
  2. El backend observa los datos de red del propio WebSocket (IP, headers) y
     guarda la identidad (upsert por (nickname, fp_id)).
  3. A partir de ahí es una sala: los mensajes se difunden a todos los
     conectados y se guardan con tope en memoria.

Lo importante para la demo: el usuario solo eligió un nickname, pero al entrar
quedó registrado su fingerprint + red sin que medie ninguna cookie.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .config import settings
from .models import ChatHello, ChatMessage, Identity
from .network import extract_network_info
from .store import store

logger = logging.getLogger("identity_detector.chat")
router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConnectionManager:
    """Mantiene el set de WebSockets activos y difunde mensajes."""

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        # Copiamos la lista porque podemos descartar conexiones muertas mientras iteramos.
        dead: list[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - una conexión caída no debe cortar el broadcast
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


def _origin_allowed(ws: WebSocket) -> bool:
    """Chequeo de Origin para el WS (los browsers no aplican CORS a WebSocket).

    Si hay orígenes configurados y el request trae un Origin que no está en la
    lista, lo rechazamos. Si no hay Origin (cliente no-browser, tests), pasa.
    """
    origin = ws.headers.get("origin")
    if not origin or not settings.allowed_origins:
        return True
    return origin in settings.allowed_origins


@router.websocket("/ws/chat")
async def chat_ws(ws: WebSocket) -> None:
    if not _origin_allowed(ws):
        # 1008 = Policy Violation
        await ws.close(code=1008)
        return

    await manager.connect(ws)
    nickname: str | None = None
    avatar = "🙂"
    try:
        # El primer mensaje DEBE ser el hello con el fingerprint.
        raw = await ws.receive_json()
        try:
            hello = ChatHello(**raw)
        except ValidationError:
            await ws.send_json({"type": "error", "text": "hello inválido"})
            await ws.close(code=1003)  # 1003 = Unsupported Data
            return

        nickname = hello.nickname
        avatar = hello.avatar

        # Acá ocurre lo central: observamos la red del propio WebSocket y
        # guardamos la identidad. El usuario solo mandó un nickname.
        net = extract_network_info(ws)
        identity = Identity(
            nickname=nickname,
            avatar=avatar,
            fingerprint=hello.fingerprint,
            network=net,
        )
        await store.upsert_identity(identity)

        # Le mandamos el historial reciente al que recién entra.
        history = await store.recent_chat()
        await ws.send_json(
            {
                "type": "history",
                "messages": [m.model_dump(mode="json") for m in history],
            }
        )
        # Avisamos a la sala (mensaje de sistema).
        await manager.broadcast(
            {"type": "system", "text": f"{avatar} {nickname} entró", "at": _now_iso()}
        )

        # Bucle de mensajes.
        while True:
            data = await ws.receive_json()
            if not isinstance(data, dict) or data.get("type") != "msg":
                continue
            text = str(data.get("text", "")).strip()[:1000]
            if not text:
                continue
            msg = ChatMessage(nickname=nickname, avatar=avatar, text=text)
            await store.add_chat_message(msg)
            await manager.broadcast({"type": "msg", **msg.model_dump(mode="json")})

    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("Error en la conexión de chat")
    finally:
        manager.disconnect(ws)
        if nickname:
            await manager.broadcast(
                {"type": "system", "text": f"{nickname} salió", "at": _now_iso()}
            )
