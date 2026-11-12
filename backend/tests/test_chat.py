"""Tests del chat por WebSocket con TestClient."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.store import store

HELLO_A = {"nickname": "ana", "avatar": "🦊", "fingerprint": {"fp_id": "FP-A"}}
HELLO_B = {"nickname": "beto", "avatar": "🐢", "fingerprint": {"fp_id": "FP-B"}}


def test_hello_registers_identity_and_sends_history():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json(HELLO_A)
            hist = ws.receive_json()
            assert hist["type"] == "history"
            assert hist["messages"] == []  # sala vacía
            join = ws.receive_json()
            assert join["type"] == "system"
            assert "ana" in join["text"]
        # Al entrar quedó registrada la identidad, solo con un nickname de por medio.
        assert any(i.nickname == "ana" and i.fp_id == "FP-A" for i in store._identities.values())


def test_message_is_broadcast_and_stored():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json(HELLO_A)
            ws.receive_json()  # history
            ws.receive_json()  # system join
            ws.send_json({"type": "msg", "text": "hola mundo"})
            msg = ws.receive_json()
            assert msg["type"] == "msg"
            assert msg["nickname"] == "ana"
            assert msg["text"] == "hola mundo"
        # Quedó en el historial en memoria.
        assert any(m.text == "hola mundo" for m in store._chat)


def test_two_clients_see_each_other():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat") as ws1:
            ws1.send_json(HELLO_A)
            ws1.receive_json()  # history
            ws1.receive_json()  # su propio join
            with client.websocket_connect("/ws/chat") as ws2:
                ws2.send_json(HELLO_B)
                ws2.receive_json()  # history de ws2
                # El join de beto llega a ambos.
                j2 = ws2.receive_json()
                assert j2["type"] == "system" and "beto" in j2["text"]
                j1 = ws1.receive_json()
                assert j1["type"] == "system" and "beto" in j1["text"]
                # ana manda un mensaje; beto lo recibe.
                ws1.send_json({"type": "msg", "text": "hola beto"})
                m_on_2 = ws2.receive_json()
                assert m_on_2["type"] == "msg" and m_on_2["text"] == "hola beto"


def test_invalid_hello_is_rejected():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"nickname": "sin_fingerprint"})  # falta fingerprint
            resp = ws.receive_json()
            assert resp["type"] == "error"
