"""Unit tests for the `generate_image` tool orchestration (tools.py). No real
Bedrock/MinIO/DB - everything mocked (Constitution Art. 5)."""
import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from services.bedrock import image_client, tools
from services.bedrock.errors import BedrockError


def _tiny_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buf, format="PNG")
    return buf.getvalue()


def _db_mock():
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.mark.requisito("RF-007")
async def test_invalid_purpose_rejected_before_anything(monkeypatch):
    gen_mock = AsyncMock()
    upload_mock = MagicMock()
    monkeypatch.setattr(image_client, "generate_image_bytes", gen_mock)
    monkeypatch.setattr("services.storage_service.upload_file", upload_mock)
    db = _db_mock()

    with pytest.raises(BedrockError):
        await tools.execute_tool(
            db, "usr-1", "generate_image",
            {"prompt": "a cube", "purpose": "not-a-real-purpose"}, "sess-1",
        )

    gen_mock.assert_not_called()
    upload_mock.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.requisito("RF-006")
async def test_empty_prompt_rejected_before_bedrock(monkeypatch):
    gen_mock = AsyncMock()
    monkeypatch.setattr(image_client, "generate_image_bytes", gen_mock)
    db = _db_mock()

    with pytest.raises(BedrockError):
        await tools.execute_tool(
            db, "usr-1", "generate_image",
            {"prompt": "   ", "purpose": "agentes"}, "sess-1",
        )

    gen_mock.assert_not_called()


@pytest.mark.requisito("RF-010")
async def test_no_file_upload_row_when_minio_fails(monkeypatch):
    monkeypatch.setattr(image_client, "generate_image_bytes", AsyncMock(return_value=_tiny_png_bytes()))
    monkeypatch.setattr("services.storage_service.upload_file", MagicMock(side_effect=Exception("boom")))
    db = _db_mock()

    with pytest.raises(Exception, match="boom"):
        await tools.execute_tool(
            db, "usr-1", "generate_image",
            {"prompt": "a cube", "purpose": "agentes"}, "sess-1",
        )

    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.requisito("RF-005")
async def test_success_returns_expected_shape(monkeypatch):
    monkeypatch.setattr(image_client, "generate_image_bytes", AsyncMock(return_value=_tiny_png_bytes()))
    monkeypatch.setattr("services.storage_service.upload_file", MagicMock(return_value="public/agentes/x.png"))
    monkeypatch.setattr(
        "services.storage_service.get_public_url",
        MagicMock(return_value="https://files.cjhirashi.com/cjhirashi-career/public/agentes/x.png"),
    )
    db = _db_mock()

    result = await tools.execute_tool(
        db, "usr-1", "generate_image",
        {"prompt": "a cube", "purpose": "agentes"}, "sess-1",
    )

    assert result == {
        "image_url": "https://files.cjhirashi.com/cjhirashi-career/public/agentes/x.png",
        "filename": "public/agentes/x.png",
        "purpose": "agentes",
    }
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
