"""API de correlación (fase 5).

  - POST /api/identify   recibe el fingerprint del visitante, lo correlaciona
                         contra las identidades del chat y devuelve el match
                         con su explicación. Cada consulta queda en el historial.
  - GET  /api/matches    historial de matches de las últimas N horas.
  - WS   /ws/matches     cada consulta nueva se empuja en vivo a los detectores
                         abiertos (la sección "historial en vivo").

El visitante del detector NO se guarda como identidad: solo consulta. Lo único
que persiste de su visita es un MatchEvent con la red en /24 o /64, nunca la IP
completa.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from . import matching
from .chat import _origin_allowed
from .config import settings
from .models import Fingerprint, MatchEvent, MatchResult
from .network import extract_network_info
from .store import store

logger = logging.getLogger("identity_detector.api")
router = APIRouter()


class _Subscribers:
    """Websockets abiertos del historial en vivo."""

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - un cliente caído no corta el resto
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


subscribers = _Subscribers()


@router.post("/api/identify", response_model=MatchResult, tags=["detector"])
async def identify(fp: Fingerprint, request: Request) -> MatchResult:
    """Devuelve la identidad más parecida y qué datos permitieron reconocerla.

    La red (IP, headers) la observa el servidor del propio request: el cliente
    no puede falsearla en el cuerpo.
    """
    net = extract_network_info(request)
    identities = await store.list_identities()
    result = matching.identify(fp, net, identities, settings.match_threshold)

    best = result.best
    event = MatchEvent(
        recognized=result.recognized,
        best_nickname=best.nickname if best else None,
        best_avatar=best.avatar if best else None,
        combined_score=best.combined_score if best else (result.top[0].combined_score if result.top else 0.0),
        device_score=best.device_score if best else (result.top[0].device_score if result.top else 0.0),
        browser_score=best.browser_score if best else (result.top[0].browser_score if result.top else 0.0),
        visitor_ip_network=net.ip_network,
    )
    await store.add_match_event(event)
    await subscribers.broadcast({"type": "match", **event.model_dump(mode="json")})
    return result


@router.get("/api/matches", response_model=list[MatchEvent], tags=["detector"])
async def matches(hours: float = Query(6, gt=0, le=168)) -> list[MatchEvent]:
    """Historial de matches de las últimas `hours` horas (más nuevo primero)."""
    events = await store.recent_matches(hours)
    return list(reversed(events))


class ForgetRequest(BaseModel):
    fp_id: str = Field(..., min_length=1, description="fp_id que calculó el tracker en este navegador")


class ForgetResponse(BaseModel):
    removed: int = Field(..., description="Cantidad de identidades (nickname + fingerprint) borradas")


@router.delete("/api/me", response_model=ForgetResponse, tags=["privacidad"])
async def forget_me(body: ForgetRequest) -> ForgetResponse:
    """Borra todas las identidades asociadas al fp_id del visitante.

    Un mismo navegador puede haber entrado al chat con varios nicknames; todos
    comparten fp_id y se borran juntos. El historial de matches no se toca: sus
    entradas no guardan fp_id (ni IP completa), solo el resultado y la red /24,
    así que no hay forma de atribuirlas a este visitante, y expiran por TTL.
    Límite documentado: si el navegador randomiza su fingerprint (Brave), el
    fp_id cambia entre visitas y el borrado solo alcanza al fp_id actual.
    """
    removed = await store.delete_by_fp(body.fp_id)
    return ForgetResponse(removed=removed)


@router.websocket("/ws/matches")
async def matches_ws(ws: WebSocket) -> None:
    if not _origin_allowed(ws):
        await ws.close(code=1008)
        return
    await subscribers.connect(ws)
    try:
        # Solo escuchamos para detectar la desconexión; el flujo es servidor -> cliente.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        subscribers.disconnect(ws)
