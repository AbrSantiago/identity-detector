"""Tests de privacidad: borrado de datos ("borrar mis datos") y TTL."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models import Fingerprint, Identity, NetworkInfo
from app.store import store

FP_A = {"fp_id": "FP-A", "canvas_hash": "c1", "webgl_renderer": "GPU raro", "timezone": "UTC"}
FP_B = {"fp_id": "FP-B", "canvas_hash": "c2", "webgl_renderer": "Otra GPU", "timezone": "UTC"}


def _join(client: TestClient, nickname: str, fp: dict) -> None:
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"nickname": nickname, "avatar": "🦊", "fingerprint": fp})
        ws.receive_json()
        ws.receive_json()


def _delete(client: TestClient, fp_id: str):
    # httpx no permite body en .delete(); usamos request() como el fetch del chat.
    return client.request("DELETE", "/api/me", json={"fp_id": fp_id})


def test_delete_me_removes_identity_and_it_is_no_longer_recognized():
    with TestClient(app) as client:
        _join(client, "ana", FP_A)
        assert client.post("/api/identify", json=FP_A).json()["recognized"] is True

        r = _delete(client, "FP-A")
        assert r.status_code == 200
        assert r.json() == {"removed": 1}
        assert not any(i.fp_id == "FP-A" for i in store._identities.values())

        # Ya no hay a quién reconocer.
        after = client.post("/api/identify", json=FP_A).json()
        assert after["recognized"] is False
        assert after["top"] == []


def test_delete_me_only_affects_that_fp_id():
    with TestClient(app) as client:
        _join(client, "ana", FP_A)
        _join(client, "beto", FP_B)
        assert _delete(client, "FP-A").json() == {"removed": 1}
        assert [i.nickname for i in store._identities.values()] == ["beto"]


def test_delete_me_removes_every_nickname_of_the_same_browser():
    with TestClient(app) as client:
        _join(client, "ana", FP_A)
        _join(client, "ana_2", FP_A)  # mismo navegador, otro seudónimo
        assert len(store._identities) == 2
        assert _delete(client, "FP-A").json() == {"removed": 2}
        assert store._identities == {}


def test_delete_me_unknown_fp_id_is_ok_and_removes_nothing():
    with TestClient(app) as client:
        r = _delete(client, "no-existe")
        assert r.status_code == 200
        assert r.json() == {"removed": 0}


def test_delete_me_requires_fp_id():
    with TestClient(app) as client:
        assert client.request("DELETE", "/api/me", json={}).status_code == 422
        assert client.request("DELETE", "/api/me", json={"fp_id": ""}).status_code == 422


def test_ttl_purges_only_expired_identities():
    old = Identity(
        nickname="vieja", avatar="🐢", fingerprint=Fingerprint(fp_id="FP-OLD"), network=NetworkInfo(),
        updated_at=datetime.now(timezone.utc) - timedelta(hours=100),
    )
    fresh = Identity(
        nickname="nueva", avatar="🦊", fingerprint=Fingerprint(fp_id="FP-NEW"), network=NetworkInfo(),
    )

    async def run() -> int:
        await store.upsert_identity(old)
        await store.upsert_identity(fresh)
        # upsert_identity inserta tal cual la primera vez, así que conserva el updated_at viejo.
        return await store.purge_expired()

    assert asyncio.run(run()) == 1
    assert [i.nickname for i in store._identities.values()] == ["nueva"]
