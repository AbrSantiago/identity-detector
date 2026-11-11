"""Modelos Pydantic: contratos de datos entre tracker, backend y detector.

Separamos a propósito tres capas de datos:
  - Fingerprint: lo que mide el navegador (lado cliente, tracker/fp.js).
  - NetworkInfo: lo que observa el servidor del propio request (IP, headers).
  - Identity: la unión de ambos con nickname/avatar, que es lo que guardamos.

Casi todos los campos del fingerprint son Optional: si una API del navegador
está bloqueada o no existe, el colector manda null, y ese null también es
información (ver tracker/fp.js).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Fingerprint(BaseModel):
    """Datos medidos por el navegador. Todo opcional salvo fp_id."""

    # Identificador estable derivado en el cliente de los componentes de
    # abajo. Lo usamos como clave para upsert y para "borrar mis datos".
    fp_id: str = Field(..., description="Hash estable calculado en el cliente")

    # --- Gráficos / render ---
    canvas_hash: Optional[str] = None
    webgl_vendor: Optional[str] = None
    webgl_renderer: Optional[str] = None
    webgl_params: Optional[dict[str, Any]] = None

    # --- Audio ---
    audio_hash: Optional[str] = None

    # --- Fuentes instaladas (medidas por ancho de texto) ---
    fonts: Optional[list[str]] = None

    # --- Hardware / pantalla ---
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    device_pixel_ratio: Optional[float] = None
    color_depth: Optional[int] = None
    hardware_concurrency: Optional[int] = None  # núcleos
    device_memory: Optional[float] = None  # GB aprox
    touch_support: Optional[bool] = None

    # --- Localización ---
    timezone: Optional[str] = None
    languages: Optional[list[str]] = None
    intl_formats: Optional[dict[str, Any]] = None
    voices: Optional[list[str]] = None  # voces de síntesis de voz

    # --- Preferencias / entorno ---
    media_queries: Optional[dict[str, Any]] = None  # tema, reduced-motion, puntero
    plugins: Optional[list[str]] = None
    do_not_track: Optional[str] = None

    # --- Red vista por el navegador (WebRTC/STUN) ---
    webrtc_public_ips: Optional[list[str]] = None
    webrtc_local_ips: Optional[list[str]] = None

    # --- Client hints de alta entropía leídos por JS (userAgentData) ---
    ua_data: Optional[dict[str, Any]] = None


class NetworkInfo(BaseModel):
    """Datos que el servidor observa del request. No vienen del cliente."""

    ip: Optional[str] = None
    ip_network: Optional[str] = None  # /24 en IPv4, /64 en IPv6
    user_agent: Optional[str] = None
    accept_language: Optional[str] = None
    accept_encoding: Optional[str] = None
    # Client hints de baja entropía que sí llegan por header.
    sec_ch_ua: Optional[str] = None
    sec_ch_ua_mobile: Optional[str] = None
    sec_ch_ua_platform: Optional[str] = None
    # Orden de los headers tal como llegaron (señal de implementación del
    # cliente). Solo confiable sin proxy de por medio; se documenta el límite.
    header_order: Optional[list[str]] = None


class ChatHello(BaseModel):
    """Primer mensaje del cliente al entrar al chat."""

    nickname: str = Field(..., min_length=1, max_length=40)
    avatar: str = Field(default="🙂", max_length=16)
    fingerprint: Fingerprint


class ChatMessage(BaseModel):
    """Mensaje de chat ya emitido por el servidor."""

    nickname: str
    avatar: str
    text: str = Field(..., max_length=1000)
    at: datetime = Field(default_factory=_now)


class Identity(BaseModel):
    """Identidad guardada: nickname + fingerprint + red. La unidad de verdad."""

    nickname: str
    avatar: str
    fingerprint: Fingerprint
    network: NetworkInfo
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @property
    def fp_id(self) -> str:
        return self.fingerprint.fp_id


class ScoreBreakdownRow(BaseModel):
    """Una fila de la explicación: qué dato, si coincidió y cuántos bits aportó."""

    attribute: str
    level: str  # "browser" o "device"
    matched: bool
    bits: float  # bits de entropía que aportó este dato si coincidió
    detail: Optional[str] = None  # texto corto para la UI


class Candidate(BaseModel):
    """Una identidad candidata con sus puntajes."""

    nickname: str
    avatar: str
    browser_score: float  # 0..1
    device_score: float  # 0..1
    combined_score: float  # 0..1


class MatchResult(BaseModel):
    """Respuesta de /api/identify."""

    recognized: bool
    best: Optional[Candidate] = None
    top: list[Candidate] = Field(default_factory=list)
    breakdown: list[ScoreBreakdownRow] = Field(default_factory=list)
    # "Esto sabemos de vos": datos crudos observados del visitante.
    observed_network: NetworkInfo
    observed_fingerprint: Fingerprint
    threshold: float


class MatchEvent(BaseModel):
    """Entrada del historial de matches (para el detector en vivo)."""

    at: datetime = Field(default_factory=_now)
    recognized: bool
    best_nickname: Optional[str] = None
    best_avatar: Optional[str] = None
    combined_score: float = 0.0
    device_score: float = 0.0
    browser_score: float = 0.0
    # No guardamos la IP completa en el historial (privacidad): solo la red.
    visitor_ip_network: Optional[str] = None
