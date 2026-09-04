"""Unit tests for GET /system/readiness (RF-008). Calls the route handler
directly - no ASGI/TestClient, so no app lifespan (no real DB/MinIO needed)."""
import json
from unittest.mock import MagicMock

import pytest

import app as app_module
from services import storage_service


@pytest.mark.requisito("RF-008")
async def test_ready_when_minio_ok(monkeypatch):
    monkeypatch.setattr(storage_service, "check_connection", MagicMock(return_value=True))

    response = await app_module.readiness_check()

    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "ready", "checks": {"minio": True}}


@pytest.mark.requisito("RF-008")
async def test_not_ready_when_minio_fails(monkeypatch):
    monkeypatch.setattr(storage_service, "check_connection", MagicMock(return_value=False))

    response = await app_module.readiness_check()

    assert response.status_code == 503
    assert json.loads(response.body) == {"status": "not_ready", "checks": {"minio": False}}
