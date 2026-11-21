"""Privacidad: los logs de uvicorn que incluyen la IP completa se descartan."""
from __future__ import annotations

import logging

import app.main  # noqa: F401 - al importarse instala los filtros


def _record(logger: str, msg: str, args: tuple) -> logging.LogRecord:
    return logging.LogRecord(logger, logging.INFO, __file__, 1, msg, args, None)


def test_http_access_log_is_dropped():
    rec = _record("uvicorn.access", '%s - "%s %s HTTP/%s" %d',
                  ("203.0.113.9:5000", "GET", "/", "1.1", 200))
    assert logging.getLogger("uvicorn.access").filter(rec) is False


def test_websocket_client_lines_are_dropped():
    rec = _record("uvicorn.error", '%s - "WebSocket %s" [accepted]',
                  (("203.0.113.9", 5000), "/ws/chat"))
    assert logging.getLogger("uvicorn.error").filter(rec) is False


def test_other_server_logs_are_kept():
    rec = _record("uvicorn.error", "Application startup complete.", ())
    assert logging.getLogger("uvicorn.error").filter(rec)
