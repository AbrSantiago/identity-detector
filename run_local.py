"""Levanta todo el proyecto en local con un solo comando.

    uv run --project backend python run_local.py [--port 8000]

Un solo proceso uvicorn (un solo worker: el estado vive en memoria) que
despacha por el header Host, para que el chat y el detector sean ORÍGENES
distintos como en producción:

    http://chat.localhost:8000      -> frontends/chat      (estáticos)
    http://detector.localhost:8000  -> frontends/detector  (estáticos)
    http://localhost:8000           -> backend FastAPI (API, WebSocket, tracker, /docs)

Los navegadores resuelven *.localhost a 127.0.0.1 sin tocar el archivo hosts.

Este script NO modifica el backend: lo importa tal cual y le pone adelante un
despachador mínimo. En producción esa tarea la hace el proxy inverso.

Privacidad: el access log de uvicorn está apagado (access_log=False) porque
loguearía la IP completa de cada visitante.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn
from starlette.responses import PlainTextResponse
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
FRONTENDS = ROOT / "frontends"
# Subdominio (primer label del Host) -> carpeta de estáticos.
SITES = ("chat", "detector")


def build_app(port: int):
    # Los orígenes permitidos por CORS dependen del puerto. Hay que fijarlos
    # ANTES de importar el backend, que lee la configuración al importarse.
    os.environ.setdefault(
        "ALLOWED_ORIGINS",
        ",".join(f"http://{s}.localhost:{port}" for s in SITES),
    )
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app as backend  # noqa: E402 - import tardío a propósito

    static = {s: StaticFiles(directory=FRONTENDS / s, html=True) for s in SITES}
    # El config.js del repo apunta a localhost:8000 (editable para producción).
    # En local lo respondemos acá para que el puerto elegido siempre coincida.
    config_js = (
        f'window.IDENTITY_CONFIG = {{ apiBase: "http://localhost:{port}" }};\n'
    ).encode()

    async def app(scope, receive, send):
        if scope["type"] != "http":
            # lifespan (arranque/parada, barrido de TTL) y websocket: al backend.
            await backend(scope, receive, send)
            return

        host = dict(scope["headers"]).get(b"host", b"").decode().split(":")[0]
        site = host.split(".")[0]
        if site not in static:
            await backend(scope, receive, send)
            return

        if scope["path"] == "/config.js":
            resp = PlainTextResponse(config_js, media_type="application/javascript")
            await resp(scope, receive, send)
            return
        await static[site](scope, receive, send)

    return app


def main() -> None:
    ap = argparse.ArgumentParser(description="Backend + chat + detector en local")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    print(f"  chat      http://chat.localhost:{args.port}")
    print(f"  detector  http://detector.localhost:{args.port}")
    print(f"  API/docs  http://localhost:{args.port}/docs")
    uvicorn.run(
        build_app(args.port),
        host="127.0.0.1",
        port=args.port,
        access_log=False,  # no loguear IPs completas
        log_level="info",
    )


if __name__ == "__main__":
    main()
