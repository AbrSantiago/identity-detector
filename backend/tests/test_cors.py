"""Tests del chequeo de origen (lista exacta + regex para túneles)."""
from __future__ import annotations

import dataclasses

from app import chat
from app.config import settings as base_settings


class FakeWS:
    """WebSocket mínimo: _origin_allowed solo mira .headers.get('origin')."""

    def __init__(self, origin: str | None):
        self.headers = {"origin": origin} if origin else {}


def _patch(monkeypatch, **over):
    patched = dataclasses.replace(base_settings, **over)
    monkeypatch.setattr(chat, "settings", patched)
    chat._compiled_origin_re.cache_clear()
    return patched


def test_exact_origin_allowed(monkeypatch):
    _patch(monkeypatch, allowed_origins=["https://chat.ok"], allowed_origin_regex="")
    assert chat._origin_allowed(FakeWS("https://chat.ok"))
    assert not chat._origin_allowed(FakeWS("https://malicioso.ok"))


def test_devtunnels_regex_allows_dynamic_host(monkeypatch):
    _patch(
        monkeypatch,
        allowed_origins=[],
        allowed_origin_regex=r"https://.*\.devtunnels\.ms$",
    )
    assert chat._origin_allowed(FakeWS("https://abc123-8080.use.devtunnels.ms"))
    assert chat._origin_allowed(FakeWS("https://abc123-8000.use.devtunnels.ms"))
    # Un host que no es de devtunnels no pasa.
    assert not chat._origin_allowed(FakeWS("https://evil.example.com"))


def test_no_origin_header_passes(monkeypatch):
    # Clientes no-browser y los tests no mandan Origin.
    _patch(monkeypatch, allowed_origins=["https://chat.ok"], allowed_origin_regex="")
    assert chat._origin_allowed(FakeWS(None))


def test_no_allowlist_and_no_regex_is_dev_open(monkeypatch):
    _patch(monkeypatch, allowed_origins=[], allowed_origin_regex="")
    assert chat._origin_allowed(FakeWS("https://cualquiera.com"))
