"""Carga identidades de ejemplo en un backend en marcha.

Sirve para probar el detector sin depender de que haya varias personas
conectadas al chat. Entra al chat por WebSocket como lo haría el frontend, así
que pasa por el mismo camino que un usuario real (upsert por nickname + fp_id).

Uso (con el backend corriendo):
    uv run python scripts/seed.py
    uv run python scripts/seed.py --url ws://localhost:8000/ws/chat --origin http://chat.localhost:8000

Limitación: el servidor ve la IP de ESTE script, así que todas las identidades
sembradas quedan en la misma red /24 (la tuya). Es más "ruidoso" que un caso
real, donde cada persona tiene su propia red; el dato de IP aporta menos bits.

Para ver el reconocimiento entre navegadores, entrá al detector desde tu
máquina: tu perfil coincide en GPU, pantalla y zona con "ana" pero no en
canvas/audio (ver docs/experimentos.md).
"""
from __future__ import annotations

import argparse
import json
import sys

from websockets.sync.client import connect

# Perfiles inventados (no son datos de nadie). Dos usuarios con equipos casi
# iguales (lucas/mica) sirven para mostrar falsos positivos: es un límite real.
PROFILES = [
    {
        "nickname": "ana", "avatar": "🦊",
        "fingerprint": {
            "fp_id": "seed-ana", "canvas_hash": "cv-ana-chrome", "audio_hash": "au-ana-chrome",
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11)",
            "fonts": ["Arial", "Calibri", "Cambria", "Consolas", "Segoe UI", "Verdana", "Fira Code"],
            "screen_width": 2560, "screen_height": 1440, "device_pixel_ratio": 1.0, "color_depth": 24,
            "hardware_concurrency": 12, "device_memory": 8, "touch_support": False,
            "timezone": "America/Argentina/Buenos_Aires", "languages": ["es-AR", "es", "en"],
            "media_queries": {"dark": True, "reduced_motion": False, "pointer": "fine"},
            "plugins": [], "do_not_track": None,
        },
    },
    {
        "nickname": "beto", "avatar": "🐢",
        "fingerprint": {
            "fp_id": "seed-beto", "canvas_hash": "cv-beto", "audio_hash": "au-beto",
            "webgl_vendor": "Apple", "webgl_renderer": "Apple M1",
            "fonts": ["Helvetica", "Menlo", "Monaco", "Avenir", "Optima"],
            "screen_width": 1440, "screen_height": 900, "device_pixel_ratio": 2.0, "color_depth": 30,
            "hardware_concurrency": 8, "device_memory": 8, "touch_support": False,
            "timezone": "America/Argentina/Buenos_Aires", "languages": ["es-AR", "es"],
            "media_queries": {"dark": False, "reduced_motion": False, "pointer": "fine"},
            "plugins": [], "do_not_track": None,
        },
    },
    {
        "nickname": "cami", "avatar": "🦉",
        "fingerprint": {
            "fp_id": "seed-cami", "canvas_hash": "cv-cami", "audio_hash": "au-cami",
            "webgl_vendor": "Qualcomm", "webgl_renderer": "Adreno (TM) 650",
            "fonts": ["Roboto", "Noto Sans", "Droid Sans"],
            "screen_width": 412, "screen_height": 915, "device_pixel_ratio": 2.6, "color_depth": 24,
            "hardware_concurrency": 8, "device_memory": 4, "touch_support": True,
            "timezone": "America/Argentina/Cordoba", "languages": ["es-AR"],
            "media_queries": {"dark": True, "reduced_motion": False, "pointer": "coarse"},
            "plugins": [], "do_not_track": None,
        },
    },
    # Par de falsos positivos: mismo modelo de notebook, mismo software.
    {
        "nickname": "lucas", "avatar": "🐙",
        "fingerprint": {
            "fp_id": "seed-lucas", "canvas_hash": "cv-office", "audio_hash": "au-office",
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11)",
            "fonts": ["Arial", "Calibri", "Segoe UI", "Verdana", "Times New Roman"],
            "screen_width": 1920, "screen_height": 1080, "device_pixel_ratio": 1.0, "color_depth": 24,
            "hardware_concurrency": 4, "device_memory": 8, "touch_support": False,
            "timezone": "America/Argentina/Buenos_Aires", "languages": ["es-AR", "es"],
            "media_queries": {"dark": False, "reduced_motion": False, "pointer": "fine"},
            "plugins": [], "do_not_track": None,
        },
    },
    {
        "nickname": "mica", "avatar": "🐝",
        "fingerprint": {
            "fp_id": "seed-mica", "canvas_hash": "cv-office", "audio_hash": "au-office",
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11)",
            "fonts": ["Arial", "Calibri", "Segoe UI", "Verdana", "Times New Roman"],
            "screen_width": 1920, "screen_height": 1080, "device_pixel_ratio": 1.0, "color_depth": 24,
            "hardware_concurrency": 4, "device_memory": 8, "touch_support": False,
            "timezone": "America/Argentina/Buenos_Aires", "languages": ["es-AR", "es"],
            "media_queries": {"dark": False, "reduced_motion": False, "pointer": "fine"},
            "plugins": [], "do_not_track": None,
        },
    },
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="ws://localhost:8000/ws/chat")
    ap.add_argument("--origin", default="http://chat.localhost:8000",
                    help="debe estar en ALLOWED_ORIGINS del backend")
    args = ap.parse_args()

    # La consola de Windows usa cp1252 y no puede imprimir los emojis de los avatares.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ok = 0
    for p in PROFILES:
        try:
            with connect(args.url, origin=args.origin) as ws:
                ws.send(json.dumps(p))
                ws.recv()  # history: confirma que el servidor registró la identidad
                ok += 1
                print(f"  + {p['avatar']} {p['nickname']}")
        except Exception as exc:  # noqa: BLE001 - mensaje claro en vez de traceback
            print(f"  ! {p['nickname']}: {exc}", file=sys.stderr)
    print(f"{ok}/{len(PROFILES)} identidades sembradas en {args.url}")
    return 0 if ok == len(PROFILES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
