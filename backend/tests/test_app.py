"""Tests de arranque de la app: /health y que /docs se genera."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_openapi_schema_builds():
    # /docs se arma a partir de este esquema; si los modelos están mal, falla acá.
    with TestClient(app) as client:
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/health" in paths
        assert "/tracker/fp.js" in paths
