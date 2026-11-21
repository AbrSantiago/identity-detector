"""Tests de network.py: resolución de IP, regla de proxy de confianza y redes.

Es la lógica más delicada de la fase 1: si confiáramos en X-Forwarded-For sin
chequear el peer, cualquiera podría falsear su IP.
"""
from __future__ import annotations

import dataclasses

import pytest
from starlette.requests import Request

from app import network
from app.config import settings as base_settings


def make_conn(client_ip: str, headers: list[tuple[bytes, bytes]]) -> Request:
    """Arma un Request de Starlette con un peer y headers dados."""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "client": (client_ip, 12345),
        "server": ("testserver", 80),
        "headers": headers,
        "asgi": {"version": "3.0"},
    }
    return Request(scope)


@pytest.fixture
def trust_10(monkeypatch):
    """Configura 10.0.0.1 como proxy de confianza para el test."""
    patched = dataclasses.replace(base_settings, trusted_proxies=["10.0.0.1"])
    monkeypatch.setattr(network, "settings", patched)
    return patched


# --- ip_to_network ---


def test_ipv4_to_slash24():
    assert network.ip_to_network("190.1.2.3") == "190.1.2.0/24"


def test_ipv6_to_slash64():
    assert network.ip_to_network("2800:abcd:1234:5678:9abc:def0:1111:2222") == (
        "2800:abcd:1234:5678::/64"
    )


def test_ip_to_network_none_and_invalid():
    assert network.ip_to_network(None) is None
    assert network.ip_to_network("no-es-ip") is None


# --- resolve_client_ip: regla de proxy ---


def test_untrusted_peer_ignores_xff(monkeypatch):
    # Sin proxies de confianza configurados: el XFF se ignora por completo.
    patched = dataclasses.replace(base_settings, trusted_proxies=[])
    monkeypatch.setattr(network, "settings", patched)
    conn = make_conn("200.100.50.25", [(b"x-forwarded-for", b"1.1.1.1")])
    # Devuelve el peer real, no el header falseable.
    assert network.resolve_client_ip(conn) == "200.100.50.25"


def test_trusted_proxy_reads_xff(trust_10):
    conn = make_conn("10.0.0.1", [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")])
    # El primer valor del XFF es el cliente original.
    assert network.resolve_client_ip(conn) == "203.0.113.9"


def test_trusted_proxy_but_malformed_xff_falls_back(trust_10):
    conn = make_conn("10.0.0.1", [(b"x-forwarded-for", b"basura")])
    assert network.resolve_client_ip(conn) == "10.0.0.1"


def test_trusted_proxy_without_xff_uses_peer(trust_10):
    conn = make_conn("10.0.0.1", [])
    assert network.resolve_client_ip(conn) == "10.0.0.1"


# --- extract_network_info ---


def test_extract_captures_headers_and_order(monkeypatch):
    patched = dataclasses.replace(base_settings, trusted_proxies=[])
    monkeypatch.setattr(network, "settings", patched)
    conn = make_conn(
        "190.1.2.3",
        [
            (b"user-agent", b"Mozilla/5.0 Test"),
            (b"accept-language", b"es-AR,es;q=0.9"),
            (b"sec-ch-ua-platform", b'"Windows"'),
        ],
    )
    info = network.extract_network_info(conn)
    assert info.ip == "190.1.2.3"
    assert info.ip_network == "190.1.2.0/24"
    assert info.user_agent == "Mozilla/5.0 Test"
    assert info.accept_language == "es-AR,es;q=0.9"
    assert info.sec_ch_ua_platform == '"Windows"'
    # El orden de headers queda registrado (señal de red, con su límite).
    assert info.header_order == ["user-agent", "accept-language", "sec-ch-ua-platform"]
