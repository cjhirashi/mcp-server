"""
Generación de imágenes — Bedrock Stability Stable Image Core.

Titan Image Generator (v1/v2) llegó a fin de vida y Nova Canvas está sin
acceso habilitado para esta cuenta en us-east-1 (Legacy) — ver
.harness/memory/state.md. Stable Image Core solo está disponible en
us-west-2, de ahí BEDROCK_IMAGE_REGION separado de BEDROCK_REGION (que sigue
sirviendo Converse/embeddings en us-east-1).

Sube bytes a MinIO vía tools.generate_image. Ver ADR-010.
"""
import asyncio
import base64
import json
import logging

import boto3

from config import settings
from services.bedrock.errors import BedrockError
from services.error_reporting import report_error

logger = logging.getLogger(__name__)

_bedrock_client = None


# ============================================================================
# Cliente de generación de imágenes
# ============================================================================

def _get_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=settings.BEDROCK_IMAGE_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return _bedrock_client


# ============================================================================
# Generación de imagen
# ============================================================================

async def generate_image_bytes(prompt: str, aspect_ratio: str = "1:1") -> bytes:
    """Invoca Stable Image Core y devuelve PNG bytes.

    `aspect_ratio` es uno de los valores fijos que acepta el modelo (1:1,
    16:9, 21:9, 2:3, 3:2, 4:5, 5:4, 9:16, 9:21) — el recorte a la medida
    exacta del purpose lo hace después image_pipeline.finalize_png.
    """

    def _invoke():
        body = json.dumps({
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "output_format": "png",
        })
        return _get_client().invoke_model(
            modelId=settings.BEDROCK_IMAGE_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )

    try:
        response = await asyncio.to_thread(_invoke)
        payload = json.loads(response["body"].read())
        b64 = payload["images"][0]
        return base64.b64decode(b64)
    except Exception as e:
        logger.exception("Image generation failed")
        report_error(
            str(e) or "Image generation failed", "bedrock:image_client",
            error_type=type(e).__name__, exc=e, severity="error",
        )
        raise BedrockError(
            f"Image generation failed (model={settings.BEDROCK_IMAGE_MODEL_ID}, "
            f"region={settings.BEDROCK_IMAGE_REGION}): {e}"
        ) from e
