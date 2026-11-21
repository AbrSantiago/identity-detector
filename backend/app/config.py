"""Configuración del backend, leída desde variables de entorno.

Toda la configuración sensible al despliegue (orígenes permitidos, proxies de
confianza, TTL de datos) vive acá y se lee una sola vez al importar el módulo.
En la defensa conviene poder mostrar que nada está hardcodeado en la lógica.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _split_env(name: str, default: str = "") -> list[str]:
    """Lee una variable separada por comas y devuelve una lista limpia."""
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # Orígenes exactos permitidos por CORS. Sin comodines: queremos que el
    # chat y el detector sean orígenes distintos y explícitos.
    allowed_origins: list[str] = field(
        default_factory=lambda: _split_env(
            "ALLOWED_ORIGINS",
            "http://chat.localhost:8000,http://detector.localhost:8000",
        )
    )
    # Regex opcional de orígenes permitidos (además de la lista exacta).
    # Sirve cuando el host es dinámico: p. ej. al exponer por un túnel de
    # VS Code, donde cada puerto queda en
    # https://<id>-<puerto>.<cluster>.devtunnels.ms. Vacío = sin regex.
    allowed_origin_regex: str = field(
        default_factory=lambda: os.environ.get("ALLOWED_ORIGIN_REGEX", "").strip()
    )
    # IPs de proxies en los que confiamos para leer X-Forwarded-For. Si el
    # request no viene de acá, ignoramos ese header (si no, cualquiera podría
    # falsear su IP mandando el header a mano).
    trusted_proxies: list[str] = field(
        default_factory=lambda: _split_env("TRUSTED_PROXIES", "")
    )
    # Horas que viven los datos en memoria antes de que el barrido los borre.
    data_ttl_hours: float = field(
        default_factory=lambda: float(os.environ.get("DATA_TTL_HOURS", "6"))
    )
    # Umbral mínimo de puntaje (0..1) para afirmar "te reconozco".
    match_threshold: float = field(
        default_factory=lambda: float(os.environ.get("MATCH_THRESHOLD", "0.35"))
    )
    # Tope de mensajes de chat guardados en memoria.
    chat_history_limit: int = field(
        default_factory=lambda: int(os.environ.get("CHAT_HISTORY_LIMIT", "200"))
    )
    # Tope de eventos de match guardados para el historial en vivo.
    match_history_limit: int = field(
        default_factory=lambda: int(os.environ.get("MATCH_HISTORY_LIMIT", "500"))
    )


settings = Settings()
