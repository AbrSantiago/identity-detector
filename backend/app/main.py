"""Aplicación FastAPI: punto de entrada del backend.

Expone (a medida que avanzan las fases):
  - GET  /health            chequeo simple.
  - GET  /tracker/fp.js     sirve el script tracker compartido.
  - WS   /ws/chat           chat anónimo en tiempo real.         (fase 3)
  - POST /api/identify      correlación de identidad.            (fase 5)
  - GET  /api/matches       historial de matches.                (fase 5)
  - WS   /ws/matches        historial en vivo.                   (fase 5)
  - DELETE /api/me          borrado de datos.                    (fase 6)

El estado vive en memoria (store.py), por eso corremos un solo worker.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import api, chat
from .config import settings
from .store import store

logger = logging.getLogger("identity_detector")

# tracker/fp.js está en la raíz del repo, dos niveles arriba de backend/app.
TRACKER_PATH = Path(__file__).resolve().parents[2] / "tracker" / "fp.js"

# Cada cuánto corre el barrido de TTL (en segundos).
_PURGE_INTERVAL_SECONDS = 300


async def _purge_loop() -> None:
    """Tarea de fondo: borra datos vencidos cada tanto."""
    while True:
        try:
            await asyncio.sleep(_PURGE_INTERVAL_SECONDS)
            removed = await store.purge_expired()
            if removed:
                logger.info("TTL: %d identidades vencidas barridas", removed)
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001 - la tarea nunca debe morir en silencio
            logger.exception("Error en el barrido de TTL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_purge_loop())
    logger.info(
        "Backend iniciado. TTL=%sh, umbral=%s, orígenes=%s",
        settings.data_ttl_hours,
        settings.match_threshold,
        settings.allowed_origins,
    )
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(
    title="Identity Detector",
    description=(
        "Demostración de correlación de identidades por fingerprint del "
        "navegador y datos de red. Contexto pedagógico (TP3 Seguridad)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: solo los orígenes configurados. El tracker es un tercero servido por
# este backend e incluido desde dos orígenes distintos, así que necesitamos
# que esos orígenes puedan llamar a la API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,  # no usamos cookies; el fp_id va en el cuerpo
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# WS /ws/chat
app.include_router(chat.router, tags=["chat"])
# POST /api/identify, GET /api/matches, WS /ws/matches
app.include_router(api.router)


@app.get("/health", tags=["infra"])
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "identity-detector"})


@app.get("/tracker/fp.js", tags=["tracker"], include_in_schema=True)
async def tracker() -> FileResponse:
    """Sirve el script tracker compartido entre los dos frontends.

    Se incluye con <script src="https://<api>/tracker/fp.js"> desde el chat y
    desde el detector: el mismo tercero presente en dos sitios distintos.
    """
    return FileResponse(
        TRACKER_PATH,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )
