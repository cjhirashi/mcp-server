"""Ruta POST /bedrock/knowledge-base/reindex (spec 003, reapertura — RF-012)."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from database import get_db
from middleware.auth import get_current_user


class _FakeUser:
    id = "usr-1"


class _FakeDB:
    async def execute(self, *a, **k):
        raise AssertionError("la ruta no debe tocar la DB directamente")


async def _override_db():
    yield _FakeDB()


def _client():
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    return TestClient(app)


@pytest.mark.requisito("RF-012")
def test_post_reindex_returns_counts():
    client = _client()
    try:
        with patch(
            "services.bedrock.knowledge_base.reindex_knowledge_base",
            new=AsyncMock(
                return_value={
                    "reindexed": {"methodology": 23, "career_record": 338},
                    "purged_orphans": 250,
                    "users": 2,
                }
            ),
        ):
            resp = client.post("/bedrock/knowledge-base/reindex")
        assert resp.status_code == 200
        body = resp.json()
        assert body["reindexed"]["methodology"] == 23
        assert body["purged_orphans"] == 250
        assert body["users"] == 2
    finally:
        client.close()
        app.dependency_overrides.clear()


@pytest.mark.requisito("RF-012")
def test_post_reindex_qdrant_down_returns_503():
    client = _client()
    try:
        with patch(
            "services.bedrock.knowledge_base.reindex_knowledge_base",
            new=AsyncMock(side_effect=RuntimeError("qdrant unreachable")),
        ):
            resp = client.post("/bedrock/knowledge-base/reindex")
        assert resp.status_code == 503
        # cuerpo con detalle (RFC 9457 via el handler estándar de la app)
        assert "qdrant unreachable" in resp.text
    finally:
        client.close()
        app.dependency_overrides.clear()


@pytest.mark.requisito("RF-012")
def test_post_reindex_requires_auth():
    # sin override de get_current_user -> 401/403
    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    try:
        resp = client.post("/bedrock/knowledge-base/reindex")
        assert resp.status_code in (401, 403)
    finally:
        client.close()
        app.dependency_overrides.clear()
