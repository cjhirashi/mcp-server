"""Unit tests for the Bedrock image client (Stable Image Core). No real AWS calls
(Constitution Art. 5) - boto3 is fully mocked."""
import base64
import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from config import settings
from services.bedrock import image_client
from services.bedrock.errors import BedrockError


def _fake_response(images):
    body = json.dumps({"images": images, "seeds": [1], "finish_reasons": [None]}).encode()

    class _Body:
        def read(self):
            return body

    return {"body": _Body()}


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    image_client._bedrock_client = None
    yield
    image_client._bedrock_client = None


@pytest.mark.asyncio
@pytest.mark.requisito("RF-001")
async def test_request_uses_configured_model_and_region(monkeypatch):
    b64 = base64.b64encode(b"fake-png-bytes").decode()
    mock_boto_client = MagicMock()
    mock_boto_client.invoke_model.return_value = _fake_response([b64])
    client_factory = MagicMock(return_value=mock_boto_client)
    monkeypatch.setattr(image_client.boto3, "client", client_factory)

    result = await image_client.generate_image_bytes("a red cube", aspect_ratio="1:1")

    assert result == b"fake-png-bytes"
    client_factory.assert_called_once_with(
        "bedrock-runtime",
        region_name=settings.BEDROCK_IMAGE_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    _, kwargs = mock_boto_client.invoke_model.call_args
    assert kwargs["modelId"] == settings.BEDROCK_IMAGE_MODEL_ID
    body = json.loads(kwargs["body"])
    assert body == {"prompt": "a red cube", "aspect_ratio": "1:1", "output_format": "png"}


@pytest.mark.asyncio
@pytest.mark.requisito("RF-009")
async def test_error_message_includes_model_and_region(monkeypatch):
    mock_boto_client = MagicMock()
    mock_boto_client.invoke_model.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "This model version has reached the end of its life."}},
        "InvokeModel",
    )
    monkeypatch.setattr(image_client.boto3, "client", MagicMock(return_value=mock_boto_client))

    with pytest.raises(BedrockError) as exc_info:
        await image_client.generate_image_bytes("a red cube", aspect_ratio="1:1")

    message = str(exc_info.value)
    assert settings.BEDROCK_IMAGE_MODEL_ID in message
    assert settings.BEDROCK_IMAGE_REGION in message
