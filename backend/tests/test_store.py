"""Tests del store: upsert por (nickname, fp_id) y borrado por fp_id."""
from __future__ import annotations

import asyncio

from app.models import Fingerprint, Identity, NetworkInfo
from app.store import store


def _identity(nickname: str, fp_id: str) -> Identity:
    return Identity(
        nickname=nickname,
        avatar="🙂",
        fingerprint=Fingerprint(fp_id=fp_id),
        network=NetworkInfo(ip="1.2.3.4", ip_network="1.2.3.0/24"),
    )


def test_upsert_same_nick_and_fp_updates_not_duplicates():
    async def run():
        await store.upsert_identity(_identity("ana", "FP1"))
        first = (await store.list_identities())[0]
        created = first.created_at
        await asyncio.sleep(0.01)
        await store.upsert_identity(_identity("ana", "FP1"))
        ids = await store.list_identities()
        assert len(ids) == 1  # no duplica
        assert ids[0].created_at == created  # misma identidad
        assert ids[0].updated_at >= created  # se actualizó

    asyncio.run(run())


def test_same_fp_different_nick_are_two_identities():
    async def run():
        # Mismo navegador, dos seudónimos distintos: dos participaciones.
        await store.upsert_identity(_identity("ana", "FP1"))
        await store.upsert_identity(_identity("beto", "FP1"))
        ids = await store.list_identities()
        assert len(ids) == 2

    asyncio.run(run())


def test_delete_by_fp_removes_all_pseudonyms_of_that_browser():
    async def run():
        await store.upsert_identity(_identity("ana", "FP1"))
        await store.upsert_identity(_identity("beto", "FP1"))
        await store.upsert_identity(_identity("otro", "FP2"))
        removed = await store.delete_by_fp("FP1")
        assert removed == 2
        ids = await store.list_identities()
        assert len(ids) == 1
        assert ids[0].fp_id == "FP2"

    asyncio.run(run())
