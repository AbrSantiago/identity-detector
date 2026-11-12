"""Fixtures compartidas. Limpia el estado en memoria entre tests."""
from __future__ import annotations

import pytest

from app.store import store


@pytest.fixture(autouse=True)
def clean_store():
    store._identities.clear()
    store._chat.clear()
    store._matches.clear()
    yield
    store._identities.clear()
    store._chat.clear()
    store._matches.clear()
