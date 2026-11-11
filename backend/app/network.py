"""Extracción de datos de red desde el request HTTP.

Responsabilidad principal: resolver la IP real del cliente de forma segura.

El problema: detrás de un proxy inverso (Caddy, Cloudflare, nginx) la IP de la
conexión TCP es la del proxy, no la del cliente. El proxy pone la IP real en
X-Forwarded-For. Pero ese header lo puede mandar cualquiera: si confiáramos en
él siempre, cualquier visitante podría falsear su IP y romper la correlación.

La regla: solo leemos X-Forwarded-For si la conexión viene de una IP que
declaramos de confianza (TRUSTED_PROXIES). Si no, usamos la IP de la conexión.
Este es un patrón estándar y conviene poder explicarlo en la defensa.
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from starlette.requests import HTTPConnection

from .config import settings
from .models import NetworkInfo


def _client_host(conn: HTTPConnection) -> Optional[str]:
    """IP de la conexión TCP (el peer real, sea cliente o proxy)."""
    if conn.client is None:
        return None
    return conn.client.host


def _is_trusted_proxy(ip: Optional[str]) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in settings.trusted_proxies:
        try:
            # Aceptamos tanto IPs sueltas como redes CIDR en la config.
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def resolve_client_ip(conn: HTTPConnection) -> Optional[str]:
    """Devuelve la IP del cliente aplicando la regla de proxy de confianza.

    Si la conexión viene de un proxy de confianza, tomamos la primera IP de
    X-Forwarded-For (el cliente original). Si no, devolvemos la IP de la
    conexión y descartamos cualquier X-Forwarded-For (no es confiable).
    """
    peer = _client_host(conn)
    if _is_trusted_proxy(peer):
        xff = conn.headers.get("x-forwarded-for")
        if xff:
            # X-Forwarded-For: cliente, proxy1, proxy2 ... el primero es el cliente.
            first = xff.split(",")[0].strip()
            if first:
                try:
                    ipaddress.ip_address(first)
                    return first
                except ValueError:
                    pass  # header malformado: caemos a la IP del peer
    return peer


def ip_to_network(ip: Optional[str]) -> Optional[str]:
    """Reduce la IP a su bloque de red: /24 en IPv4, /64 en IPv6.

    Trabajamos a nivel de red y no de IP exacta porque dentro de una misma
    casa/empresa la IP puede variar, pero el bloque suele ser estable. También
    es lo que guardamos en el historial, para no persistir la IP completa.
    """
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.version == 4:
        net = ipaddress.ip_network(f"{ip}/24", strict=False)
    else:
        net = ipaddress.ip_network(f"{ip}/64", strict=False)
    return str(net)


# Headers de interés para el fingerprint de red (además de la IP).
_INTERESTING_HEADERS = (
    "user-agent",
    "accept-language",
    "accept-encoding",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
)


def extract_network_info(conn: HTTPConnection) -> NetworkInfo:
    """Arma el NetworkInfo a partir de un request/websocket."""
    ip = resolve_client_ip(conn)
    headers = conn.headers
    return NetworkInfo(
        ip=ip,
        ip_network=ip_to_network(ip),
        user_agent=headers.get("user-agent"),
        accept_language=headers.get("accept-language"),
        accept_encoding=headers.get("accept-encoding"),
        sec_ch_ua=headers.get("sec-ch-ua"),
        sec_ch_ua_mobile=headers.get("sec-ch-ua-mobile"),
        sec_ch_ua_platform=headers.get("sec-ch-ua-platform"),
        # Orden en que llegaron los headers. Solo es señal útil sin proxy que
        # los reescriba; se documenta como limitación.
        header_order=[k.decode("latin-1").lower() for k, _ in conn.scope.get("headers", [])],
    )
