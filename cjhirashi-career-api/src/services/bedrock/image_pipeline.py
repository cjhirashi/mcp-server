"""
Pipeline de imágenes del agente Visual — especificación por propósito
(agentes/proyectos/publicaciones) y post-proceso Pillow compartido por el
flujo de generación (Stable Image Core) y el de "guardar imagen ya
existente". Ver ADR-010.
"""
import io
import re
import uuid
from dataclasses import dataclass

from PIL import Image, ImageOps

from services.bedrock.errors import BedrockError

# ============================================================================
# Especificación por propósito — única fuente de verdad de tamaño/carpeta
# ============================================================================


@dataclass(frozen=True)
class PurposeSpec:
    width: int
    height: int
    category: str  # carpeta del bucket, p.ej. "agentes"


IMAGE_PURPOSES = {
    "agentes": PurposeSpec(width=500, height=500, category="agentes"),
    "proyectos": PurposeSpec(width=1920, height=1080, category="proyectos"),
    "publicaciones": PurposeSpec(width=1920, height=1080, category="publicaciones"),
}


def resolve_purpose(purpose: str) -> PurposeSpec:
    spec = IMAGE_PURPOSES.get((purpose or "").strip().lower())
    if spec is None:
        valid = ", ".join(IMAGE_PURPOSES)
        raise BedrockError(f"purpose inválido: '{purpose}' (válidos: {valid})")
    return spec


# ============================================================================
# aspect_ratio de generación — Stable Image Core
# ============================================================================
# Stable Image Core no acepta ancho/alto libres, solo un aspect_ratio de un
# set fijo. Se elige el más cercano a spec.width/height y el recorte a la
# medida exacta lo hace finalize_png() después.
_STABILITY_RATIOS = {
    "16:9": 16 / 9, "21:9": 21 / 9, "1:1": 1.0, "2:3": 2 / 3, "3:2": 3 / 2,
    "4:5": 4 / 5, "5:4": 5 / 4, "9:16": 9 / 16, "9:21": 9 / 21,
}


def stability_aspect_ratio(spec: PurposeSpec) -> str:
    target = spec.width / spec.height
    return min(_STABILITY_RATIOS, key=lambda name: abs(_STABILITY_RATIOS[name] - target))


# ============================================================================
# Post-proceso: ajustar a la medida exacta y recomprimir PNG para web
# ============================================================================


def finalize_png(data: bytes, spec: PurposeSpec) -> bytes:
    """Ajusta cualquier imagen de entrada a exactamente `spec.width x
    spec.height` (recorte centrado, sin deformar) y la re-codifica como PNG
    optimizado para web. Usado tanto para el output de Titan como para una
    imagen ya existente que el solicitante pide guardar/optimizar."""
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    fitted = ImageOps.fit(image, (spec.width, spec.height), Image.LANCZOS)

    has_alpha = fitted.mode in ("RGBA", "LA") or (fitted.mode == "P" and "transparency" in fitted.info)
    fitted = fitted.convert("RGBA" if has_alpha else "RGB")

    buffer = io.BytesIO()
    fitted.save(buffer, format="PNG", optimize=True, compress_level=9)
    return buffer.getvalue()


# ============================================================================
# Nombrado
# ============================================================================


def slug_name(name: str | None, fallback: str) -> str:
    """Slug legible para el nombre de archivo (p.ej. 'Retrato Agente Visual'
    -> 'retrato-agente-visual'); recorta el prompt/nombre original si hace
    falta usarlo como fallback. La unicidad la añade storage_service (sufijo
    uuid corto), esto solo aporta la parte humana del nombre."""
    base = (name or fallback or "imagen").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    slug = slug[:60].rstrip("-")
    return slug or f"imagen-{uuid.uuid4().hex[:8]}"
