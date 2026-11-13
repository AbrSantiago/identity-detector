"""Tests de /api/identify, /api/matches y /ws/matches."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

FP_CHAT = {
    "fp_id": "FP-A",
    "canvas_hash": "c1",
    "audio_hash": "a1",
    "webgl_renderer": "GPU raro X1",
    "webgl_vendor": "Acme",
    "fonts": ["Arial", "Fira", "Zilla"],
    "screen_width": 1920,
    "screen_height": 1080,
    "device_pixel_ratio": 1.0,
    "timezone": "America/Argentina/Buenos_Aires",
}
# Mismo dispositivo, otro navegador: cambia canvas/audio, no el hardware.
FP_OTHER_BROWSER = {**FP_CHAT, "fp_id": "FP-A2", "canvas_hash": "c2", "audio_hash": "a2"}
FP_STRANGER = {
    "fp_id": "FP-Z",
    "canvas_hash": "zz",
    "audio_hash": "zz",
    "webgl_renderer": "Otra GPU",
    "webgl_vendor": "Otro",
    "fonts": ["Comic"],
    "screen_width": 800,
    "screen_height": 600,
    "device_pixel_ratio": 2.0,
    "timezone": "Asia/Tokyo",
}


def _join(client: TestClient, nickname: str, fp: dict) -> None:
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"nickname": nickname, "avatar": "🦊", "fingerprint": fp})
        ws.receive_json()  # history
        ws.receive_json()  # system join


def test_identify_recognizes_same_device_other_browser():
    with TestClient(app) as client:
        _join(client, "ana", FP_CHAT)
        r = client.post("/api/identify", json=FP_OTHER_BROWSER)
        assert r.status_code == 200
        data = r.json()
        assert data["recognized"] is True
        assert data["best"]["nickname"] == "ana"
        # El nivel dispositivo reconoce aunque el navegador sea otro.
        assert data["best"]["device_score"] > data["best"]["browser_score"]
        assert data["breakdown"], "debe explicar qué datos coincidieron"
        assert data["observed_fingerprint"]["fp_id"] == "FP-A2"


def test_identify_does_not_recognize_stranger():
    with TestClient(app) as client:
        _join(client, "ana", FP_CHAT)
        data = client.post("/api/identify", json=FP_STRANGER).json()
        assert data["recognized"] is False
        assert data["best"] is None


def test_identify_with_empty_population():
    with TestClient(app) as client:
        data = client.post("/api/identify", json=FP_CHAT).json()
        assert data["recognized"] is False
        assert data["top"] == []


def test_each_identify_is_added_to_history_without_full_ip(monkeypatch):
    # TestClient usa el host "testclient" (no es una IP); fijamos una real.
    monkeypatch.setattr("app.network._client_host", lambda conn: "203.0.113.9")
    with TestClient(app) as client:
        _join(client, "ana", FP_CHAT)
        client.post("/api/identify", json=FP_OTHER_BROWSER)
        client.post("/api/identify", json=FP_STRANGER)
        events = client.get("/api/matches?hours=1").json()
        assert len(events) == 2
        # Más nuevo primero: el último fue el desconocido.
        assert events[0]["recognized"] is False
        assert events[1]["best_nickname"] == "ana"
        # Privacidad: solo la red /24, nunca la IP completa.
        assert "ip" not in events[0]
        assert events[0]["visitor_ip_network"] == "203.0.113.0/24"
        assert "203.0.113.9" not in str(events)


def test_matches_rejects_bad_hours():
    with TestClient(app) as client:
        assert client.get("/api/matches?hours=0").status_code == 422


def test_ws_matches_pushes_new_events_live():
    with TestClient(app) as client:
        _join(client, "ana", FP_CHAT)
        with client.websocket_connect("/ws/matches") as ws:
            client.post("/api/identify", json=FP_OTHER_BROWSER)
            msg = ws.receive_json()
            assert msg["type"] == "match"
            assert msg["best_nickname"] == "ana"
